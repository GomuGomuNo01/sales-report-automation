"""
Extractor : lecture et fusion de tous les fichiers CSV du dossier raw/
"""

import os
import glob
import logging
import pandas as pd
from config import RAW_DATA_DIR, EXPECTED_COLUMNS

logger = logging.getLogger(__name__)


def load_csv_files(directory: str = RAW_DATA_DIR) -> pd.DataFrame:
    """
    Lit tous les fichiers CSV présents dans le dossier raw/
    et les fusionne en un seul DataFrame.

    Returns:
        pd.DataFrame : données brutes fusionnées
    Raises:
        FileNotFoundError : si aucun fichier CSV n'est trouvé
    """
    pattern = os.path.join(directory, "*.csv")
    fichiers = sorted(glob.glob(pattern))

    if not fichiers:
        raise FileNotFoundError(
            f"Aucun fichier CSV trouvé dans : {directory}"
        )

    logger.info(f"{len(fichiers)} fichier(s) CSV détecté(s)")

    dataframes = []

    for chemin in fichiers:
        nom_fichier = os.path.basename(chemin)
        try:
            df = pd.read_csv(chemin, encoding="utf-8-sig")
            df["source_fichier"] = nom_fichier  # Traçabilité
            dataframes.append(df)
            logger.info(f"  ✓ {nom_fichier} — {len(df)} lignes")
        except Exception as e:
            logger.warning(f"  ✗ Impossible de lire {nom_fichier} : {e}")

    if not dataframes:
        raise ValueError("Aucun fichier CSV n'a pu être lu correctement.")

    df_fusion = pd.concat(dataframes, ignore_index=True)
    logger.info(f"Fusion terminée : {len(df_fusion)} lignes au total")

    return df_fusion


def validate_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Vérifie que toutes les colonnes attendues sont présentes.
    Lève une erreur claire si une colonne est manquante.
    """
    colonnes_manquantes = [
        col for col in EXPECTED_COLUMNS if col not in df.columns
    ]

    if colonnes_manquantes:
        raise ValueError(
            f"Colonnes manquantes dans les données : {colonnes_manquantes}"
        )

    logger.info("Validation des colonnes : OK")
    return df


def extract(directory: str = RAW_DATA_DIR) -> pd.DataFrame:
    """
    Point d'entrée principal de l'extraction.
    Charge, fusionne et valide les colonnes.

    Returns:
        pd.DataFrame : données brutes prêtes pour le nettoyage
    """
    logger.info("=== ÉTAPE 1 : EXTRACTION ===")
    df = load_csv_files(directory)
    df = validate_columns(df)
    return df