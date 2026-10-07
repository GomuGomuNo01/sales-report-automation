"""
app.py — Interface web de démonstration (Streamlit)

Permet à n'importe qui (recruteur, RH, curieux) de tester le pipeline
depuis son navigateur : aucune installation, aucune ligne de commande.

Lancement local : streamlit run app.py
"""

import io
import logging
import os
import re
import tempfile
import threading
import time

import numpy as np
import pandas as pd
import streamlit as st

from config import BASE_DIR, EXPECTED_COLUMNS, RAPPORT_TITRE
from generate_data import generer_annee
from src.cleaner import MOIS_FR, clean
from src.extractor import extract
from src.transformer import transform
from src.visualizer import generate_all_charts
from src.reporter import generate_report

GITHUB_URL   = "https://github.com/GomuGomuNo01/sales-report-automation"
EXEMPLE_CSV  = os.path.join(BASE_DIR, "examples", "ventes_exemple_janvier_2024.csv")
EXEMPLE_PDF  = os.path.join(BASE_DIR, "examples", "rapport_exemple_2024.pdf")

# matplotlib (pyplot) n'est pas thread-safe et Streamlit sert chaque visiteur
# dans un thread : on sérialise les exécutions du pipeline.
_PIPELINE_LOCK = threading.Lock()

CHARTS_LIBELLES = {
    "top_vendeurs":          "Top vendeurs",
    "evolution_mensuelle":   "Évolution mensuelle",
    "repartition_categorie": "Catégories",
    "heatmap":               "Vendeurs × régions",
    "top_produits":          "Top produits",
}


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
    rng = np.random.RandomState(42)
    for chemin in generer_annee(dossier, 2024, seed=42):
        if anomalies:
            df = pd.read_csv(chemin, encoding="utf-8-sig")
            ajouter_anomalies(df, rng).to_csv(chemin, index=False, encoding="utf-8-sig")


def preparer_fichiers_utilisateur(dossier: str, fichiers) -> None:
    """Copie les CSV envoyés par le visiteur dans `dossier`."""
    for i, fichier in enumerate(fichiers):
        nom = re.sub(r"[^\w.-]", "_", os.path.basename(fichier.name)) or f"fichier_{i}.csv"
        if not nom.lower().endswith(".csv"):
            nom += ".csv"
        with open(os.path.join(dossier, f"{i:02d}_{nom}"), "wb") as f:
            f.write(fichier.getvalue())


# ============================================================
# ANALYSE DE LA QUALITÉ DES DONNÉES BRUTES
# ============================================================

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
        ("Dates manquantes ou illisibles",
         int(pd.to_datetime(df_brut["date"], errors="coerce").isna().sum()),
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
# EXÉCUTION DU PIPELINE
# ============================================================

class _CollecteurLogs(logging.Handler):
    """Garde en mémoire les logs du pipeline pour les afficher dans l'interface."""

    def __init__(self):
        super().__init__(logging.INFO)
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
        self.lignes = []

    def emit(self, record):
        self.lignes.append(self.format(record))


def executer_pipeline(dossier_csv: str, periode: str, progression) -> dict:
    """
    Exécute les 5 étapes du pipeline sur les CSV de `dossier_csv`.
    Les graphiques et le PDF sont produits dans un dossier temporaire
    propre à l'exécution, puis chargés en mémoire.
    """
    collecteur = _CollecteurLogs()
    racine = logging.getLogger()
    niveau_initial = racine.level

    with _PIPELINE_LOCK, tempfile.TemporaryDirectory() as sortie:
        racine.addHandler(collecteur)
        racine.setLevel(logging.INFO)
        try:
            debut = time.perf_counter()

            progression(0.05, "① Extraction des fichiers CSV…")
            df_brut = extract(dossier_csv)
            diagnostic = diagnostic_qualite(df_brut)

            progression(0.25, "② Nettoyage des données…")
            df_propre = clean(df_brut.copy())
            if df_propre.empty:
                raise ValueError("Aucune ligne exploitable après nettoyage (dates toutes invalides ?).")

            progression(0.45, "③ Calcul des KPIs et agrégations…")
            resultats = transform(df_propre)

            progression(0.60, "④ Génération des graphiques…")
            chemins_charts = generate_all_charts(resultats, charts_dir=sortie)

            progression(0.85, "⑤ Mise en page du rapport PDF…")
            periode = periode.strip() or periode_depuis_donnees(resultats["df"])
            chemin_pdf = generate_report(resultats, chemins_charts, periode=periode, output_dir=sortie)

            duree = time.perf_counter() - debut
            charts = {cle: open(chemin, "rb").read() for cle, chemin in chemins_charts.items()}
            with open(chemin_pdf, "rb") as f:
                pdf = f.read()
        finally:
            racine.removeHandler(collecteur)
            racine.setLevel(niveau_initial)

    progression(1.0, "Terminé ✅")
    return {
        "duree":        duree,
        "periode":      periode,
        "nb_fichiers":  df_brut["source_fichier"].nunique(),
        "nb_brut":      len(df_brut),
        "nb_propre":    len(df_propre),
        "diagnostic":   diagnostic,
        "apercu_brut":  df_brut.head(200),
        "resultats":    resultats,
        "charts":       charts,
        "pdf":          pdf,
        "logs":         collecteur.lignes,
    }


# ============================================================
# AFFICHAGE
# ============================================================

def _euros(valeur: float) -> str:
    return f"{valeur:,.0f} €".replace(",", " ")


def afficher_accueil() -> bool:
    """Affiche la page d'accueil. Retourne True si le visiteur lance la démo en un clic."""
    lancer = st.button("🚀 Lancer la démo (données d'exemple)", type="primary")
    st.caption("Un clic suffit. Pour utiliser vos propres fichiers CSV ou changer la période, "
               "ouvrez le panneau de gauche.")

    c1, c2, c3 = st.columns(3)
    c1.markdown("#### 1. Les données\nDes exports de ventes bruts, comme ceux d'un ERP : "
                "plusieurs fichiers CSV, avec doublons, trous et fautes de saisie.")
    c2.markdown("#### 2. Le pipeline\nExtraction → nettoyage → calcul des KPIs → graphiques → PDF. "
                "Le même code que la version en ligne de commande.")
    c3.markdown("#### 3. Le résultat\nUn rapport PDF de 6 pages prêt pour la réunion de direction, "
                "téléchargeable immédiatement.")

    if os.path.exists(EXEMPLE_PDF):
        st.divider()
        st.markdown("Pressé(e) ? Voici un rapport déjà généré :")
        with open(EXEMPLE_PDF, "rb") as f:
            st.download_button("📄 Télécharger un exemple de rapport", f.read(),
                               file_name="rapport_exemple_2024.pdf", mime="application/pdf")

    return lancer


def afficher_resultats(run: dict) -> None:
    res  = run["resultats"]
    kpis = res["kpis"]

    st.success(f"Rapport « {run['periode']} » généré en **{run['duree']:.1f} secondes** "
               f"à partir de {run['nb_brut']:,} lignes brutes réparties dans "
               f"{run['nb_fichiers']} fichier(s).".replace(",", " "))

    slug = re.sub(r"[^\w]+", "_", run["periode"].lower()).strip("_") or "rapport"
    st.download_button("⬇️ Télécharger le rapport PDF (6 pages)", run["pdf"],
                       file_name=f"rapport_ventes_{slug}.pdf", mime="application/pdf",
                       type="primary", width="stretch")

    # ---- Le pipeline étape par étape ----
    st.subheader("Ce que le pipeline vient de faire")
    e1, e2, e3, e4, e5 = st.columns(5)
    nb = lambda x: f"{x:,}".replace(",", "\u202f")  # noqa: E731
    etapes = [
        ("① Extraction",     nb(run["nb_brut"]),   f"lignes · {run['nb_fichiers']} fichier(s)"),
        ("② Nettoyage",      nb(run["nb_propre"]), f"lignes · {run['nb_brut'] - run['nb_propre']} invalides retirées"),
        ("③ Transformation", "8",                  "KPIs · 6 agrégations"),
        ("④ Visualisation",  "5",                  "graphiques PNG"),
        ("⑤ Rapport",        "6",                  f"pages PDF · {len(run['pdf']) // 1024} Ko"),
    ]
    for col, (label, valeur, detail) in zip(st.columns(5), etapes):
        col.metric(label, valeur, detail, delta_color="off", delta_arrow="off")

    onglets = st.tabs(["📊 Tableau de bord", "🧹 Qualité des données", "🗂️ Données", "📜 Journal", "⚙️ Comment ça marche"])

    # ---- Tableau de bord ----
    with onglets[0]:
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Chiffre d'affaires net", _euros(kpis["ca_total"]))
        k2.metric("Commandes actives", f"{kpis['nb_commandes']:,}".replace(",", " "))
        k3.metric("Panier moyen", _euros(kpis["panier_moyen"]))
        k4.metric("Taux d'annulation / retour", f"{kpis['taux_annulation']:.1f} %")
        k5, k6, k7, _ = st.columns(4)
        k5.metric("Remises accordées", _euros(kpis["remise_totale"]))
        k6.metric("Vendeurs", kpis["nb_vendeurs"])
        k7.metric("Produits", kpis["nb_produits"])

        st.divider()
        graphiques = list(run["charts"].items())
        for i in range(0, len(graphiques), 2):
            colonnes = st.columns(2)
            for col, (cle, image) in zip(colonnes, graphiques[i:i + 2]):
                col.markdown(f"**{CHARTS_LIBELLES.get(cle, cle)}**")
                col.image(image, width="stretch")

    # ---- Qualité des données ----
    with onglets[1]:
        st.markdown("Les exports ERP sont rarement propres. Voici les anomalies trouvées "
                    "**dans les fichiers bruts** et ce que l'étape de nettoyage en a fait :")
        diag = run["diagnostic"]
        st.dataframe(diag, hide_index=True, width="stretch")
        total = int(diag["Lignes concernées"].sum())
        if total == 0:
            st.caption("Aucune anomalie : ces données étaient déjà propres. "
                       "Astuce : cochez « Ajouter des anomalies » dans le panneau de gauche pour voir le nettoyage à l'œuvre.")
        with st.expander("Voir un extrait des données brutes (avant nettoyage)"):
            st.dataframe(run["apercu_brut"], width="stretch")

    # ---- Données ----
    with onglets[2]:
        df = res["df"]
        colonnes = EXPECTED_COLUMNS + ["ca_brut", "remise_euros", "ca_net", "ca_comptabilise"]
        st.markdown(f"**{len(df)} lignes** nettoyées et enrichies (CA brut, remise en €, CA net).")
        st.dataframe(df[colonnes], width="stretch", height=380)
        tampon = io.StringIO()
        df[colonnes].to_csv(tampon, index=False)
        st.download_button("⬇️ Télécharger les données nettoyées (CSV)",
                           tampon.getvalue().encode("utf-8-sig"),
                           file_name="ventes_nettoyees.csv", mime="text/csv")

        c1, c2 = st.columns(2)
        c1.markdown("**CA par région**")
        c1.dataframe(res["par_region"], hide_index=True, width="stretch")
        c2.markdown("**CA par catégorie**")
        c2.dataframe(res["par_categorie"], hide_index=True, width="stretch")

    # ---- Journal ----
    with onglets[3]:
        st.markdown("Les logs réellement produits par le pipeline pendant cette exécution :")
        st.code("\n".join(run["logs"]) or "(aucun log)", language="log")

    # ---- Comment ça marche ----
    with onglets[4]:
        st.markdown(f"""
Le pipeline est découpé en **5 modules Python indépendants**, chacun avec une seule responsabilité :

| Étape | Module | Rôle |
|---|---|---|
| ① Extraction | `src/extractor.py` | Charge et fusionne tous les CSV, vérifie les colonnes |
| ② Nettoyage | `src/cleaner.py` | Doublons, valeurs manquantes, types, remises, statuts |
| ③ Transformation | `src/transformer.py` | CA brut / net, KPIs, agrégations par vendeur, mois, région… |
| ④ Visualisation | `src/visualizer.py` | 5 graphiques matplotlib / seaborn |
| ⑤ Rapport | `src/reporter.py` | PDF A4 de 6 pages avec fpdf2 |

Cette interface (`app.py`) ne réimplémente rien : elle appelle exactement les mêmes fonctions
que la commande `python main.py`. Le code est couvert par plus de 50 tests automatisés (pytest).

👉 [Voir le code source sur GitHub]({GITHUB_URL})
""")


# ============================================================
# PAGE
# ============================================================

def main() -> None:
    st.set_page_config(page_title="Sales Report Automation — Démo", page_icon="📊", layout="wide")

    st.title("📊 Sales Report Automation")
    st.markdown("**Des exports de ventes bruts au rapport PDF professionnel, en quelques secondes.** "
                "Ce qui prenait 5 heures à la main (Excel, calculs, graphiques, mise en page) "
                "est ici entièrement automatisé.")

    # ---- Panneau latéral : paramètres ----
    with st.sidebar:
        st.header("1. Les données")
        source = st.radio("Source", ["Données de démonstration", "Mes propres fichiers CSV"],
                          label_visibility="collapsed")

        fichiers, anomalies = [], False
        if source == "Données de démonstration":
            st.caption("12 fichiers mensuels fictifs (année 2024), ~1 200 ventes.")
            anomalies = st.checkbox("Ajouter des anomalies typiques d'un export ERP", value=True,
                                    help="Doublons, valeurs manquantes, remises saisies en %, statuts mal "
                                         "orthographiés, quantités négatives… pour voir le nettoyage à l'œuvre.")
        else:
            fichiers = st.file_uploader("Fichiers CSV (un ou plusieurs)", type="csv",
                                        accept_multiple_files=True)
            st.caption("Colonnes attendues : " + ", ".join(f"`{c}`" for c in EXPECTED_COLUMNS))
            if os.path.exists(EXEMPLE_CSV):
                with open(EXEMPLE_CSV, "rb") as f:
                    st.download_button("Télécharger un CSV modèle", f.read(),
                                       file_name="modele_ventes.csv", mime="text/csv")

        st.header("2. Le rapport")
        periode = st.text_input("Période affichée", placeholder="Détectée automatiquement",
                                help="Ex : « Janvier - Juin 2024 ». Laissez vide pour la déduire des dates.")
        lancer = st.button("🚀 Générer le rapport", type="primary", width="stretch",
                           disabled=(source != "Données de démonstration" and not fichiers))

        st.divider()
        st.caption(f"{RAPPORT_TITRE} · [Code source]({GITHUB_URL})")

    # ---- Accueil ----
    zone_accueil = st.empty()
    if "run" not in st.session_state:
        with zone_accueil.container():
            if afficher_accueil():
                lancer, source, fichiers, anomalies = True, "Données de démonstration", [], True

    # ---- Exécution ----
    if lancer:
        zone_accueil.empty()
        barre = st.progress(0.0, text="Préparation des données…")
        try:
            with tempfile.TemporaryDirectory() as dossier_csv:
                if source == "Données de démonstration":
                    preparer_donnees_demo(dossier_csv, anomalies)
                else:
                    preparer_fichiers_utilisateur(dossier_csv, fichiers)
                st.session_state["run"] = executer_pipeline(
                    dossier_csv, periode, lambda p, t: barre.progress(p, text=t))
        except (ValueError, FileNotFoundError, pd.errors.ParserError) as e:
            st.session_state.pop("run", None)
            st.error(f"**Impossible de traiter ces fichiers :** {e}")
            st.markdown("Vérifiez que vos fichiers sont des CSV séparés par des virgules, encodés en UTF-8, "
                        "avec les colonnes : " + ", ".join(f"`{c}`" for c in EXPECTED_COLUMNS) + ".")
        except Exception as e:  # noqa: BLE001 — on ne veut jamais d'écran d'erreur brut pour un visiteur
            st.session_state.pop("run", None)
            logging.getLogger(__name__).exception("Erreur inattendue dans l'interface")
            st.error(f"Erreur inattendue : {e}")
        finally:
            barre.empty()

    if "run" in st.session_state:
        afficher_resultats(st.session_state["run"])


if __name__ == "__main__":
    main()
