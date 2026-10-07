"""
service.py — Logique métier de l'interface web (aucune dépendance HTTP)

Prépare les données d'entrée (démo ou fichiers envoyés), exécute les
5 étapes du pipeline en émettant un événement par étape, construit l'objet
« rapport » 100 % JSON décrit dans le contrat d'API, et garde le PDF et le
CSV produits dans un cache mémoire pour les téléchargements.
"""

import codecs
import contextlib
import csv
import io
import logging
import math
import os
import re
import tempfile
import threading
import time
import unicodedata
import uuid
import warnings
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Iterable, Optional

import numpy as np
import pandas as pd

from config import BASE_DIR, EXPECTED_COLUMNS
from generate_data import generer_annee
from src.cleaner import MOIS_FR, clean
from src.extractor import extract
from src.reporter import generate_report
from src.transformer import transform
from src.visualizer import generate_all_charts

import matplotlib.pyplot as plt  # après src.visualizer, qui choisit le backend « Agg »

logger = logging.getLogger(__name__)

EXEMPLE_CSV = os.path.join(BASE_DIR, "examples", "ventes_exemple_janvier_2024.csv")
EXEMPLE_PDF = os.path.join(BASE_DIR, "examples", "rapport_exemple_2024.pdf")

# Colonnes exposées dans l'aperçu JSON et dans le CSV téléchargeable
COLONNES_DONNEES = EXPECTED_COLUMNS + ["ca_net", "ca_comptabilise"]
NB_LIGNES_APERCU = 100

ETAPES = ("extraction", "nettoyage", "transformation", "visualisation", "rapport")

MESSAGE_ERREUR_INATTENDUE = "Une erreur inattendue est survenue pendant la génération du rapport."
MESSAGE_CSV_ILLISIBLE = ("Aucun fichier n'a pu être lu. Vérifiez qu'il s'agit bien de fichiers CSV "
                         "séparés par des virgules et encodés en UTF-8.")
MESSAGE_AUCUNE_LIGNE = ("Aucune ligne exploitable après nettoyage. Vérifiez la colonne « date » "
                        "(format attendu : AAAA-MM-JJ).")
MESSAGE_AUCUNE_VENTE = ("Aucune vente comptabilisée (toutes les commandes sont annulées ou retournées) : "
                        "impossible de produire les graphiques.")

# Garde-fous sur la forme des fichiers envoyés, vérifiés AVANT pandas et le
# verrou du pipeline : pandas renomme les colonnes en double en temps
# quadratique (60 000 colonnes « a,a,… » = plusieurs dizaines de secondes).
MAX_COLONNES       = 50
LONGUEUR_MAX_ENTETE = 4096  # octets

# Nombre maximal de valeurs distinctes par colonne après nettoyage : la heatmap
# vendeurs × régions (tableau croisé + une annotation par case) coûte en temps
# et en mémoire le produit des deux. Les produits ne comptent pas (top 10 seulement).
LIMITES_MODALITES = {
    "vendeur":   (200, "vendeurs distincts"),
    "region":    (50,  "régions distinctes"),
    "categorie": (50,  "catégories distinctes"),
}

# matplotlib (pyplot) n'est pas thread-safe et generate_data utilise les graines
# globales de numpy/random : toutes les exécutions sont sérialisées par ce verrou.
# Réentrant, pour que la préparation des données et le pipeline puissent le
# prendre l'un après l'autre dans le même thread.
VERROU_PIPELINE = threading.RLock()

# Loggers dont les messages alimentent le journal affiché à l'utilisateur
LOGGER_PIPELINE = "src"

Emetteur = Callable[[dict], None]


class ErreurDonnees(Exception):
    """Erreur due aux données envoyées ; le message est destiné à l'utilisateur."""


# ============================================================
# PRÉPARATION DES DONNÉES D'ENTRÉE
# ============================================================

def ajouter_anomalies(df: pd.DataFrame, rng: np.random.RandomState) -> pd.DataFrame:
    """
    Dégrade volontairement un export propre pour reproduire les défauts
    typiques d'un export ERP : doublons, trous, remises en %, statuts mal
    orthographiés, quantités négatives.
    """
    df = df.copy()
    n = len(df)

    def _tirage(proportion: float, minimum: int = 1) -> np.ndarray:
        taille = min(n, max(minimum, int(n * proportion)))
        return rng.choice(df.index, size=taille, replace=False)

    # Remises saisies en pourcentage (10 au lieu de 0.10)
    avec_remise = df.index[df["remise"] > 0]
    if len(avec_remise):
        idx = rng.choice(avec_remise, size=max(1, len(avec_remise) // 3), replace=False)
        df.loc[idx, "remise"] = (df.loc[idx, "remise"] * 100).round(0)

    # Statuts non harmonisés
    variantes = {"Livré": ["livre", "LIVRÉ", " livré "], "En cours": ["en cours", "EnCours"],
                 "Annulé": ["annule", "ANNULÉ"], "Retourné": ["retourne"]}
    for i in _tirage(0.20):
        choix = variantes.get(df.at[i, "statut"])
        if choix:
            df.at[i, "statut"] = choix[rng.randint(len(choix))]

    # Valeurs manquantes et impossibles
    df["prix_unitaire"] = df["prix_unitaire"].astype(object)
    df.loc[_tirage(0.01), "vendeur"]       = np.nan
    df.loc[_tirage(0.01), "prix_unitaire"] = np.nan
    df.loc[_tirage(0.005), "quantite"]     = -df["quantite"]
    df.loc[_tirage(0.003), "date"]         = np.nan

    # Doublons exacts
    doublons = df.loc[_tirage(0.02)]
    return pd.concat([df, doublons]).sample(frac=1, random_state=rng).reset_index(drop=True)


def preparer_donnees_demo(dossier: str, anomalies: bool) -> None:
    """Génère 12 mois de ventes fictives (2024) dans `dossier`."""
    with VERROU_PIPELINE:  # generer_annee réinitialise les graines globales
        rng = np.random.RandomState(42)
        for chemin in generer_annee(dossier, 2024, seed=42):
            if anomalies:
                df = pd.read_csv(chemin, encoding="utf-8-sig")
                ajouter_anomalies(df, rng).to_csv(chemin, index=False, encoding="utf-8-sig")


def nom_fichier_assaini(nom: str, index: int) -> str:
    """
    Construit un nom de fichier sûr à partir du nom envoyé par le navigateur :
    aucun dossier (ni / ni \\), caractères ASCII simples, extension .csv en
    minuscules, préfixe numérique pour garder l'ordre et éviter les collisions.
    """
    base = os.path.basename((nom or "").replace("\\", "/"))
    racine = os.path.splitext(base)[0]
    racine = re.sub(r"[^\w-]", "_", racine, flags=re.ASCII).strip("._")[:80]
    return f"{index:02d}_{racine or 'fichier'}.csv"


def _nom_affiche(nom: str) -> str:
    return os.path.basename((nom or "").replace("\\", "/")) or "sans nom"


def _ligne_entete(contenu: bytes, nom: str) -> str:
    """
    Première ligne non vide du fichier, décodée en UTF-8 (BOM accepté), sans
    jamais lire plus de LONGUEUR_MAX_ENTETE octets du fichier.
    """
    debut = contenu[:LONGUEUR_MAX_ENTETE]
    lignes = debut.removeprefix(codecs.BOM_UTF8).split(b"\n")
    if len(contenu) > LONGUEUR_MAX_ENTETE:
        lignes.pop()  # la dernière ligne est peut-être coupée
    entete = next((ligne for ligne in lignes if ligne.strip()), None)
    if entete is None:
        if len(contenu) > LONGUEUR_MAX_ENTETE:
            raise ErreurDonnees(
                f"« {_nom_affiche(nom)} » : la ligne d'en-tête est trop longue. Vérifiez qu'il "
                "s'agit bien d'un CSV de ventes séparé par des virgules.")
        entete = b""
    try:
        return entete.decode("utf-8").rstrip("\r")
    except UnicodeDecodeError as e:
        raise ErreurDonnees(f"« {_nom_affiche(nom)} » n'a pas pu être lu : le fichier doit être "
                            "un CSV encodé en UTF-8.") from e


def verifier_entetes(fichiers: Iterable[tuple[str, bytes]]) -> None:
    """
    Contrôle la ligne d'en-tête de chaque fichier envoyé, sans pandas :
    longueur, nombre de colonnes et colonnes attendues.

    Raises:
        ErreurDonnees : message destiné à l'utilisateur
    """
    for nom, contenu in fichiers:
        colonnes = next(csv.reader(io.StringIO(_ligne_entete(contenu, nom))), [])
        if len(colonnes) > MAX_COLONNES:
            raise ErreurDonnees(
                f"« {_nom_affiche(nom)} » contient trop de colonnes ({formater_nombre(len(colonnes))}, "
                f"maximum {MAX_COLONNES}). Colonnes attendues : {', '.join(EXPECTED_COLUMNS)}.")
        manquantes = [c for c in EXPECTED_COLUMNS if c not in colonnes]
        if manquantes:
            raise ErreurDonnees(
                f"Colonnes manquantes dans « {_nom_affiche(nom)} » : {', '.join(manquantes)}. "
                f"Colonnes attendues : {', '.join(EXPECTED_COLUMNS)} "
                "(CSV séparé par des virgules, encodé en UTF-8).")


def ecrire_fichiers_envoyes(dossier: str, fichiers: Iterable[tuple[str, bytes]]) -> list:
    """Écrit les couples (nom, contenu) dans `dossier` sous un nom assaini. Retourne les chemins."""
    racine = os.path.realpath(dossier)
    chemins = []
    for i, (nom, contenu) in enumerate(fichiers):
        chemin = os.path.realpath(os.path.join(racine, nom_fichier_assaini(nom, i)))
        if os.path.dirname(chemin) != racine:  # garde-fou : jamais en dehors du dossier
            raise ErreurDonnees("Nom de fichier invalide.")
        with open(chemin, "wb") as f:
            f.write(contenu)
        chemins.append(chemin)
    return chemins


# ============================================================
# ANALYSE DE LA QUALITÉ DES DONNÉES BRUTES
# ============================================================

def _dates_illisibles(dates: pd.Series) -> int:
    with warnings.catch_warnings():  # formats hétérogènes : pandas prévient qu'il parse au cas par cas
        warnings.simplefilter("ignore", UserWarning)
        return int(pd.to_datetime(dates, errors="coerce").isna().sum())


def diagnostic_qualite(df_brut: pd.DataFrame) -> pd.DataFrame:
    """Compte les anomalies présentes dans les données brutes, avant nettoyage."""
    statuts_ok = {"Livré", "En cours", "Annulé", "Retourné"}
    remise     = pd.to_numeric(df_brut["remise"], errors="coerce")
    quantite   = pd.to_numeric(df_brut["quantite"], errors="coerce")
    prix       = pd.to_numeric(df_brut["prix_unitaire"], errors="coerce")
    texte      = ["vendeur", "region", "produit", "categorie", "statut"]

    lignes = [
        ("Doublons exacts", int(df_brut.duplicated(subset=EXPECTED_COLUMNS).sum()),
         "Supprimés"),
        ("Dates manquantes ou illisibles", _dates_illisibles(df_brut["date"]),
         "Lignes supprimées (non récupérables)"),
        ("Champs texte vides", int(df_brut[texte].isna().sum().sum()),
         "Remplacés par « Inconnu »"),
        ("Montants manquants",
         int(df_brut[["quantite", "prix_unitaire", "remise"]].isna().sum().sum()),
         "Remplacés par la médiane"),
        ("Remises saisies en % (ex : 10 au lieu de 0,10)", int((remise > 1).sum()),
         "Divisées par 100"),
        ("Quantités ou prix négatifs", int(((quantite < 0) | (prix < 0)).sum()),
         "Ramenés à 0"),
        ("Statuts mal orthographiés",
         int((~df_brut["statut"].isin(statuts_ok) & df_brut["statut"].notna()).sum()),
         "Harmonisés (livre, LIVRÉ… → Livré)"),
    ]
    return pd.DataFrame(lignes, columns=["Anomalie détectée", "Lignes concernées", "Correction appliquée"])


def periode_depuis_donnees(df: pd.DataFrame) -> str:
    """Déduit un libellé de période lisible à partir des dates des ventes."""
    debut, fin = df["date"].min(), df["date"].max()
    if pd.isna(debut):
        return "Période inconnue"
    if (debut.year, debut.month) == (fin.year, fin.month):
        return f"{MOIS_FR[debut.month]} {debut.year}"
    if debut.year == fin.year:
        return f"{MOIS_FR[debut.month]} - {MOIS_FR[fin.month]} {debut.year}"
    return f"{MOIS_FR[debut.month]} {debut.year} - {MOIS_FR[fin.month]} {fin.year}"


# ============================================================
# FORMATAGE
# ============================================================

def slug_periode(periode: str) -> str:
    """« Janvier - Décembre 2024 » → « janvier_decembre_2024 » (« rapport » si vide)."""
    ascii_ = unicodedata.normalize("NFKD", periode or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", ascii_.lower()).strip("_") or "rapport"


def formater_nombre(n: int) -> str:
    """1180 → « 1 180 » (espace fine insécable U+202F comme séparateur de milliers)."""
    return f"{int(n):,}".replace(",", " ")


def accorder(n: int, singulier: str, pluriel: str) -> str:
    """Nombre + nom accordé selon la règle française : singulier pour 0 et 1 (« 0 retirée », « 1 ligne »)."""
    return f"{formater_nombre(n)} {singulier if abs(n) < 2 else pluriel}"


def nombre_fichiers(k: int) -> str:
    """« 0 fichier », « 1 fichier », « 12 fichiers »."""
    return accorder(k, "fichier", "fichiers")


def valeur_json(valeur, decimales: int = 2):
    """Convertit une valeur pandas/numpy en type JSON natif (NaN → None, date → AAAA-MM-JJ)."""
    if valeur is None:
        return None
    if isinstance(valeur, (str, bool)):
        return valeur
    if isinstance(valeur, np.bool_):
        return bool(valeur)
    if isinstance(valeur, (int, np.integer)):
        return int(valeur)
    if isinstance(valeur, (float, np.floating)):
        valeur = float(valeur)
        return round(valeur, decimales) if math.isfinite(valeur) else None
    if pd.isna(valeur):
        return None
    if isinstance(valeur, (pd.Timestamp, datetime, date)):
        return valeur.strftime("%Y-%m-%d")
    return str(valeur)


def compter_pages_pdf(pdf: bytes) -> int:
    """Nombre d'objets /Type /Page (fpdf2 n'utilise pas de flux d'objets compressés)."""
    return len(re.findall(rb"/Type\s*/Page(?![A-Za-z])", pdf))


# ============================================================
# JOURNAL D'EXÉCUTION
# ============================================================

class CollecteurLogs(logging.Handler):
    """Garde en mémoire les logs du pipeline émis par le thread courant."""

    def __init__(self):
        super().__init__(logging.INFO)
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
        self.lignes = []
        self._thread = threading.get_ident()

    def emit(self, record):
        if record.thread == self._thread:
            self.lignes.append(self.format(record))


@contextlib.contextmanager
def collecter_logs(nom_logger: str = LOGGER_PIPELINE):
    """Branche un CollecteurLogs sur le logger du pipeline le temps du bloc ; rend la liste des lignes."""
    collecteur = CollecteurLogs()
    cible = logging.getLogger(nom_logger)
    niveau_initial = cible.level
    cible.addHandler(collecteur)
    cible.setLevel(logging.INFO)
    try:
        yield collecteur.lignes
    finally:
        cible.removeHandler(collecteur)
        cible.setLevel(niveau_initial)


# ============================================================
# CACHE DES RAPPORTS
# ============================================================

@dataclass(frozen=True)
class RapportEnCache:
    """Fichiers d'un rapport généré, servis par les routes de téléchargement."""
    pdf: bytes
    csv: bytes
    nom_pdf: str
    nom_csv: str


class CacheRapports:
    """Cache mémoire thread-safe : `capacite` entrées max, chacune valable `duree_vie` secondes."""

    def __init__(self, capacite: int = 32, duree_vie: float = 3600.0,
                 horloge: Callable[[], float] = time.monotonic):
        self.capacite  = capacite
        self.duree_vie = duree_vie
        self._horloge  = horloge
        self._entrees: "OrderedDict[str, tuple[float, RapportEnCache]]" = OrderedDict()
        self._verrou   = threading.Lock()

    def _purger(self) -> None:
        maintenant = self._horloge()
        for cle in [c for c, (expiration, _) in self._entrees.items() if expiration <= maintenant]:
            del self._entrees[cle]

    def ajouter(self, identifiant: str, entree: RapportEnCache) -> None:
        with self._verrou:
            self._purger()
            self._entrees[identifiant] = (self._horloge() + self.duree_vie, entree)
            self._entrees.move_to_end(identifiant)
            while len(self._entrees) > self.capacite:
                self._entrees.popitem(last=False)  # le plus ancien part en premier

    def obtenir(self, identifiant: str) -> Optional[RapportEnCache]:
        with self._verrou:
            self._purger()
            element = self._entrees.get(identifiant)
            return element[1] if element else None

    def __len__(self) -> int:
        with self._verrou:
            self._purger()
            return len(self._entrees)


CACHE_RAPPORTS = CacheRapports()


# ============================================================
# CONSTRUCTION DE L'OBJET « rapport » (JSON)
# ============================================================

def construire_qualite(diagnostic: pd.DataFrame) -> list:
    return [{"anomalie": a, "lignes": int(n), "correction": c}
            for a, n, c in diagnostic.itertuples(index=False)]


def _repartition(df: pd.DataFrame, colonne: str) -> list:
    """Liste {nom, ca, part} triée par CA décroissant ; part en % à 1 décimale."""
    total = float(df["ca_total"].sum())
    return [{"nom": str(nom), "ca": valeur_json(ca),
             "part": round(float(ca) / total * 100, 1) if total else 0.0}
            for nom, ca in zip(df[colonne], df["ca_total"])]


def _heatmap(pivot: pd.DataFrame) -> dict:
    """Lignes = vendeurs, colonnes = régions, toutes deux triées par CA total décroissant."""
    vendeurs = pivot.sum(axis=1).sort_values(ascending=False, kind="stable").index
    regions  = pivot.sum(axis=0).sort_values(ascending=False, kind="stable").index
    pivot = pivot.loc[vendeurs, regions]
    return {
        "vendeurs": [str(v) for v in pivot.index],
        "regions":  [str(r) for r in pivot.columns],
        "valeurs":  [[valeur_json(x) for x in ligne] for ligne in pivot.to_numpy().tolist()],
    }


def construire_series(resultats: dict) -> dict:
    return {
        "vendeurs": [{"nom": str(n), "ca": valeur_json(ca)}
                     for n, ca in zip(resultats["par_vendeur"]["vendeur"], resultats["par_vendeur"]["ca_total"])],
        "mois": [{"annee": int(a), "mois": int(m), "mois_nom": str(nom), "ca": valeur_json(ca)}
                 for a, m, nom, ca in resultats["par_mois"][["annee", "mois", "mois_nom", "ca_total"]]
                 .itertuples(index=False)],
        "categories": _repartition(resultats["par_categorie"], "categorie"),
        "regions":    _repartition(resultats["par_region"], "region"),
        "produits": [{"nom": str(n), "ca": valeur_json(ca)}
                     for n, ca in zip(resultats["top_produits"]["produit"], resultats["top_produits"]["ca_total"])],
        "heatmap": _heatmap(resultats["heatmap"]),
    }


def construire_apercu(df: pd.DataFrame, nb_lignes: int = NB_LIGNES_APERCU) -> dict:
    lignes = [[valeur_json(v) for v in ligne]
              for ligne in df[COLONNES_DONNEES].head(nb_lignes).itertuples(index=False)]
    return {"colonnes": list(COLONNES_DONNEES), "lignes": lignes}


def donnees_csv(df: pd.DataFrame) -> bytes:
    """Toutes les lignes nettoyées, mêmes colonnes que l'aperçu, en UTF-8 avec BOM (Excel)."""
    export = df[COLONNES_DONNEES].copy()
    export["date"] = pd.to_datetime(export["date"]).dt.strftime("%Y-%m-%d")
    return export.to_csv(index=False).encode("utf-8-sig")


# ============================================================
# EXÉCUTION DU PIPELINE
# ============================================================

def _message_extraction(erreur: Exception) -> str:
    """Traduit une erreur d'extraction en message utilisateur (jamais de trace technique)."""
    texte = str(erreur)
    if texte.startswith("Colonnes manquantes"):
        manquantes = re.findall(r"'([^']+)'", texte)
        return (f"Colonnes manquantes dans vos fichiers : {', '.join(manquantes)}. "
                f"Colonnes attendues : {', '.join(EXPECTED_COLUMNS)} "
                "(CSV séparé par des virgules, encodé en UTF-8).")
    return MESSAGE_CSV_ILLISIBLE


def _extraire(dossier_csv: str) -> pd.DataFrame:
    try:
        return extract(dossier_csv)
    except FileNotFoundError as e:
        raise ErreurDonnees("Aucun fichier CSV à traiter.") from e
    except (ValueError, pd.errors.ParserError) as e:
        raise ErreurDonnees(_message_extraction(e)) from e


def verifier_modalites(df: pd.DataFrame) -> None:
    """Refuse les données dont une colonne de regroupement a trop de valeurs distinctes."""
    for colonne, (maximum, libelle) in LIMITES_MODALITES.items():
        nombre = int(df[colonne].nunique())
        if nombre > maximum:
            raise ErreurDonnees(
                f"Trop de {libelle} ({formater_nombre(nombre)}, maximum {maximum}) : "
                f"vérifiez la colonne « {colonne} » de vos fichiers.")


def _etape(on_event: Emetteur, nom: str, statut: str, detail: Optional[str] = None) -> None:
    evenement = {"type": "etape", "etape": nom, "statut": statut}
    if detail is not None:
        evenement["detail"] = detail
    on_event(evenement)


def executer_pipeline(dossier_csv: str, periode: str, on_event: Emetteur,
                      cache: Optional[CacheRapports] = None) -> dict:
    """
    Exécute les 5 étapes du pipeline sur les CSV de `dossier_csv`, en émettant
    via `on_event` un événement « en_cours » puis « termine » par étape.
    Les graphiques et le PDF sont produits dans un dossier temporaire supprimé
    ensuite ; le PDF et le CSV sont gardés en mémoire dans `cache`.

    Returns:
        dict : l'objet « rapport » du contrat d'API (types JSON natifs)
    Raises:
        ErreurDonnees : données inexploitables (message destiné à l'utilisateur)
    """
    cache = CACHE_RAPPORTS if cache is None else cache

    with VERROU_PIPELINE, collecter_logs() as journal, \
            tempfile.TemporaryDirectory(prefix="rapport_") as sortie:
        debut = time.perf_counter()

        _etape(on_event, "extraction", "en_cours")
        df_brut = _extraire(dossier_csv)
        diagnostic = diagnostic_qualite(df_brut)
        nb_fichiers = int(df_brut["source_fichier"].nunique())
        _etape(on_event, "extraction", "termine",
               f"{accorder(len(df_brut), 'ligne', 'lignes')} · {nombre_fichiers(nb_fichiers)}")

        _etape(on_event, "nettoyage", "en_cours")
        df_propre = clean(df_brut.copy())
        if df_propre.empty:
            raise ErreurDonnees(MESSAGE_AUCUNE_LIGNE)
        verifier_modalites(df_propre)  # avant transform() : coût quadratique de la heatmap
        nb_retirees = len(df_brut) - len(df_propre)
        _etape(on_event, "nettoyage", "termine",
               f"{accorder(len(df_propre), 'ligne valide', 'lignes valides')} · {accorder(nb_retirees, 'retirée', 'retirées')}")

        _etape(on_event, "transformation", "en_cours")
        resultats = transform(df_propre)
        if not resultats["kpis"]["ca_total"] > 0:  # aussi faux pour NaN
            raise ErreurDonnees(MESSAGE_AUCUNE_VENTE)
        nb_agregations = len(resultats) - 2  # hors « df » et « kpis »
        _etape(on_event, "transformation", "termine",
               f"{len(resultats['kpis'])} indicateurs · {nb_agregations} agrégations")

        try:
            _etape(on_event, "visualisation", "en_cours")
            chemins_charts = generate_all_charts(resultats, charts_dir=sortie)
            _etape(on_event, "visualisation", "termine", f"{len(chemins_charts)} graphiques")

            _etape(on_event, "rapport", "en_cours")
            periode = (periode or "").strip() or periode_depuis_donnees(resultats["df"])
            chemin_pdf = generate_report(resultats, chemins_charts, periode=periode, output_dir=sortie)
            with open(chemin_pdf, "rb") as f:
                pdf = f.read()
        finally:
            # Une figure restée ouverte après une erreur n'est jamais libérée par pyplot
            # (sans risque pour les autres requêtes : on est sous VERROU_PIPELINE).
            plt.close("all")
        duree = time.perf_counter() - debut
        _etape(on_event, "rapport", "termine",
               f"PDF de {compter_pages_pdf(pdf)}\u00a0pages · {formater_nombre(max(1, round(len(pdf) / 1024)))} Ko")

    df = resultats["df"]
    identifiant = uuid.uuid4().hex
    slug = slug_periode(periode)
    entree = RapportEnCache(pdf=pdf, csv=donnees_csv(df),
                            nom_pdf=f"rapport_ventes_{slug}.pdf", nom_csv=f"ventes_nettoyees_{slug}.csv")
    cache.ajouter(identifiant, entree)

    return {
        "id":                identifiant,
        "periode":           periode,
        "duree":             round(duree, 2),
        "nb_fichiers":       nb_fichiers,
        "nb_lignes_brutes":  len(df_brut),
        "nb_lignes_propres": len(df_propre),
        "kpis":              {cle: valeur_json(v) for cle, v in resultats["kpis"].items()},
        "qualite":           construire_qualite(diagnostic),
        "series":            construire_series(resultats),
        "apercu":            construire_apercu(df),
        "nb_lignes_donnees": len(df),
        "journal":           list(journal),
        "pdf": {"url": f"/api/rapports/{identifiant}/pdf", "nom": entree.nom_pdf, "taille": len(pdf)},
        "csv": {"url": f"/api/rapports/{identifiant}/csv", "nom": entree.nom_csv},
    }


def generer_rapport(source: str, periode: str, on_event: Emetteur, anomalies: bool = True,
                    fichiers: Iterable[tuple[str, bytes]] = (),
                    cache: Optional[CacheRapports] = None) -> Optional[dict]:
    """
    Prépare les données (démo ou fichiers envoyés) dans un dossier temporaire,
    exécute le pipeline puis émet UN événement final : « resultat » ou « erreur ».
    Ne lève jamais d'exception : retourne le rapport, ou None en cas d'échec.
    """
    try:
        fichiers = list(fichiers)
        if source != "demo":
            verifier_entetes(fichiers)  # hors verrou : un fichier piégé ne bloque personne
        with VERROU_PIPELINE, tempfile.TemporaryDirectory(prefix="entrees_") as dossier_csv:
            if source == "demo":
                preparer_donnees_demo(dossier_csv, anomalies)
            else:
                ecrire_fichiers_envoyes(dossier_csv, fichiers)
            rapport = executer_pipeline(dossier_csv, periode, on_event, cache)
    except ErreurDonnees as e:
        logger.info("Rapport refusé : %s", e)
        on_event({"type": "erreur", "message": str(e)})
        return None
    except Exception:  # noqa: BLE001 — jamais de trace technique côté utilisateur
        logger.exception("Erreur inattendue pendant la génération du rapport")
        on_event({"type": "erreur", "message": MESSAGE_ERREUR_INATTENDUE})
        return None

    on_event({"type": "resultat", "rapport": rapport})
    return rapport
