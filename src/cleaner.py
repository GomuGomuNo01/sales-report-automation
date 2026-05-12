"""
Cleaner : nettoyage et standardisation des données brutes
"""

import logging
import pandas as pd
from config import EXPECTED_COLUMNS

logger = logging.getLogger(__name__)

# Noms de mois en français — indépendant de la locale système
MOIS_FR = {
    1: "Janvier",   2: "Février",  3: "Mars",      4: "Avril",
    5: "Mai",       6: "Juin",     7: "Juillet",   8: "Août",
    9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre",
}


def remove_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Supprime les lignes entièrement dupliquées."""
    nb_avant = len(df)
    df = df.drop_duplicates(
        subset=[c for c in EXPECTED_COLUMNS],  # Ignore colonne source_fichier
        keep="first"
    )
    nb_supprimes = nb_avant - len(df)
    if nb_supprimes > 0:
        logger.warning(f"  {nb_supprimes} doublon(s) supprimé(s)")
    else:
        logger.info("  Aucun doublon détecté")
    return df


def handle_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    """
    Gère les valeurs manquantes colonne par colonne.
    - Numériques : remplacement par la médiane
    - Texte : remplacement par 'Inconnu'
    - Dates : suppression de la ligne
    """
    nb_avant = len(df)

    # Supprimer les lignes sans date (non récupérables)
    df = df.dropna(subset=["date"])

    # Colonnes texte → 'Inconnu'
    for col in ["vendeur", "region", "produit", "categorie", "statut"]:
        nb_nan = df[col].isna().sum()
        if nb_nan > 0:
            df[col] = df[col].fillna("Inconnu")
            logger.warning(f"  {nb_nan} valeur(s) manquante(s) dans '{col}' → 'Inconnu'")

    # Colonnes numériques → médiane
    for col in ["quantite", "prix_unitaire", "remise"]:
        nb_nan = df[col].isna().sum()
        if nb_nan > 0:
            mediane = df[col].median()
            df[col] = df[col].fillna(mediane)
            logger.warning(f"  {nb_nan} valeur(s) manquante(s) dans '{col}' → médiane ({mediane})")

    nb_supprimes = nb_avant - len(df)
    if nb_supprimes > 0:
        logger.warning(f"  {nb_supprimes} ligne(s) supprimée(s) (date manquante)")

    return df


def fix_data_types(df: pd.DataFrame) -> pd.DataFrame:
    """
    Corrige les types de chaque colonne.
    - date         → datetime
    - quantite     → int
    - prix_unitaire → float
    - remise       → float
    - Texte        → str strip (supprime espaces inutiles)
    """
    # Dates
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])  # Supprime les dates non parsables

    # Numériques
    df["quantite"]      = pd.to_numeric(df["quantite"], errors="coerce").fillna(0).astype(int)
    df["prix_unitaire"] = pd.to_numeric(df["prix_unitaire"], errors="coerce").fillna(0.0).astype(float)
    df["remise"]        = pd.to_numeric(df["remise"], errors="coerce").fillna(0.0).astype(float)

    # Texte : strip + title case pour harmoniser
    for col in ["vendeur", "region", "produit", "categorie", "statut"]:
        df[col] = df[col].astype(str).str.strip()

    logger.info("  Correction des types : OK")
    return df


def fix_remise(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalise la remise :
    - Si valeur > 1 (ex: 10 au lieu de 0.10) → divise par 100
    - Clamp entre 0 et 1
    """
    df["remise"] = df["remise"].apply(
        lambda x: x / 100 if x > 1 else x
    )
    df["remise"] = df["remise"].clip(0, 1)
    logger.info("  Normalisation des remises : OK")
    return df


def fix_negative_values(df: pd.DataFrame) -> pd.DataFrame:
    """Remplace les quantités et prix négatifs par 0."""
    df.loc[df["quantite"] < 0, "quantite"]           = 0
    df.loc[df["prix_unitaire"] < 0, "prix_unitaire"] = 0.0
    logger.info("  Vérification valeurs négatives : OK")
    return df


def standardize_statut(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardise les valeurs de la colonne statut
    en gérant les variantes orthographiques.
    """
    mapping = {
        "livre":    "Livré",
        "livré":    "Livré",
        "en cours": "En cours",
        "encours":  "En cours",
        "annule":   "Annulé",
        "annulé":   "Annulé",
        "retourne": "Retourné",
        "retourné": "Retourné",
    }
    df["statut"] = (
        df["statut"]
        .str.lower()
        .str.strip()
        .map(mapping)
        .fillna("Inconnu")
    )
    logger.info("  Standardisation des statuts : OK")
    return df


def add_time_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ajoute des colonnes temporelles dérivées de la date
    pour faciliter les agrégations ensuite.
    """
    df["annee"]     = df["date"].dt.year
    df["mois"]      = df["date"].dt.month
    df["mois_nom"]  = df["mois"].map(MOIS_FR)
    df["semaine"]   = df["date"].dt.isocalendar().week.astype(int)
    df["trimestre"] = df["date"].dt.quarter
    logger.info("  Ajout colonnes temporelles : OK")
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """
    Point d'entrée principal du nettoyage.
    Applique toutes les étapes dans l'ordre.

    Returns:
        pd.DataFrame : données nettoyées et typées
    """
    logger.info("=== ÉTAPE 2 : NETTOYAGE ===")
    logger.info(f"  Entrée : {len(df)} lignes")

    df = remove_duplicates(df)
    df = handle_missing_values(df)
    df = fix_data_types(df)
    df = fix_remise(df)
    df = fix_negative_values(df)
    df = standardize_statut(df)
    df = add_time_columns(df)
    df = df.reset_index(drop=True)

    logger.info(f"  Sortie : {len(df)} lignes propres")
    return df