"""
Transformer : calculs métier et agrégations pour le rapport
"""

import logging
import numpy as np
import pandas as pd
from config import EXCLUDED_STATUTS, TOP_VENDEURS_N

logger = logging.getLogger(__name__)


def calculate_ca(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcule le chiffre d'affaires réel par ligne.
    Formule : CA = quantité × prix_unitaire × (1 - remise)
    Les commandes annulées/retournées sont exclues du CA.
    """
    # CA brut sur toutes les lignes
    df["ca_brut"] = df["quantite"] * df["prix_unitaire"]

    # CA net (après remise)
    df["ca_net"] = df["ca_brut"] * (1 - df["remise"])
    df["ca_net"] = df["ca_net"].round(2)

    # Montant de la remise en euros
    df["remise_euros"] = (df["ca_brut"] - df["ca_net"]).round(2)

    # Exclure les commandes annulées/retournées du CA comptabilisé
    df["ca_comptabilise"] = np.where(
        df["statut"].isin(EXCLUDED_STATUTS), 0.0, df["ca_net"]
    )

    logger.info("  Calcul CA brut / net / comptabilisé : OK")
    return df


def get_kpis_globaux(df: pd.DataFrame) -> dict:
    """
    Calcule les KPIs globaux pour la page résumé du rapport.

    Returns:
        dict avec les métriques clés
    """
    df_actif = df[~df["statut"].isin(EXCLUDED_STATUTS)]

    ca_total        = df["ca_comptabilise"].sum()
    nb_commandes    = len(df_actif)
    panier_moyen    = (ca_total / nb_commandes) if nb_commandes > 0 else 0
    nb_annulations  = len(df[df["statut"].isin(EXCLUDED_STATUTS)])
    taux_annulation = (nb_annulations / len(df) * 100) if len(df) > 0 else 0
    remise_totale   = df["remise_euros"].sum()

    kpis = {
        "ca_total":          round(ca_total, 2),
        "nb_commandes":      nb_commandes,
        "panier_moyen":      round(panier_moyen, 2),
        "nb_annulations":    nb_annulations,
        "taux_annulation":   round(taux_annulation, 2),
        "remise_totale":     round(remise_totale, 2),
        "nb_vendeurs":       df["vendeur"].nunique(),
        "nb_produits":       df["produit"].nunique(),
    }

    logger.info(f"  KPIs globaux calculés — CA total : {ca_total:,.2f} €")
    return kpis


def get_ca_par_vendeur(df: pd.DataFrame) -> pd.DataFrame:
    """Top N vendeurs par CA comptabilisé."""
    result = (
        df.groupby("vendeur")["ca_comptabilise"]
        .sum()
        .round(2)
        .sort_values(ascending=False)
        .head(TOP_VENDEURS_N)
        .reset_index()
        .rename(columns={"ca_comptabilise": "ca_total"})
    )
    logger.info(f"  CA par vendeur calculé — Top {TOP_VENDEURS_N}")
    return result


def get_ca_par_mois(df: pd.DataFrame) -> pd.DataFrame:
    """Évolution du CA mois par mois, trié chronologiquement."""
    result = (
        df.groupby(["annee", "mois", "mois_nom"])["ca_comptabilise"]
        .sum()
        .round(2)
        .reset_index()
        .sort_values(["annee", "mois"])
        .rename(columns={"ca_comptabilise": "ca_total"})
    )
    logger.info("  CA par mois calculé : OK")
    return result


def get_ca_par_categorie(df: pd.DataFrame) -> pd.DataFrame:
    """Répartition du CA par catégorie produit."""
    result = (
        df.groupby("categorie")["ca_comptabilise"]
        .sum()
        .round(2)
        .reset_index()
        .sort_values("ca_comptabilise", ascending=False)
        .rename(columns={"ca_comptabilise": "ca_total"})
    )
    logger.info("  CA par catégorie calculé : OK")
    return result


def get_ca_par_region(df: pd.DataFrame) -> pd.DataFrame:
    """CA total par région."""
    result = (
        df.groupby("region")["ca_comptabilise"]
        .sum()
        .round(2)
        .reset_index()
        .sort_values("ca_comptabilise", ascending=False)
        .rename(columns={"ca_comptabilise": "ca_total"})
    )
    logger.info("  CA par région calculé : OK")
    return result


def get_heatmap_vendeur_region(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tableau croisé vendeur × région pour la heatmap.
    Valeurs = CA comptabilisé.
    """
    result = df.pivot_table(
        values="ca_comptabilise",
        index="vendeur",
        columns="region",
        aggfunc="sum",
        fill_value=0
    ).round(2)
    logger.info("  Heatmap vendeur × région calculée : OK")
    return result


def get_top_produits(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Top N produits par CA."""
    result = (
        df.groupby("produit")["ca_comptabilise"]
        .sum()
        .round(2)
        .sort_values(ascending=False)
        .head(n)
        .reset_index()
        .rename(columns={"ca_comptabilise": "ca_total"})
    )
    logger.info(f"  Top {n} produits calculé : OK")
    return result


def transform(df: pd.DataFrame) -> dict:
    """
    Point d'entrée principal de la transformation.
    Retourne un dictionnaire avec toutes les données
    nécessaires au rapport.

    Returns:
        dict contenant :
            - df           : DataFrame enrichi avec colonnes CA
            - kpis         : métriques globales
            - par_vendeur  : CA par vendeur
            - par_mois     : évolution mensuelle
            - par_categorie: répartition par catégorie
            - par_region   : CA par région
            - heatmap      : croisé vendeur × région
            - top_produits : top 10 produits
    """
    logger.info("=== ÉTAPE 3 : TRANSFORMATION ===")

    df = calculate_ca(df)

    resultats = {
        "df":            df,
        "kpis":          get_kpis_globaux(df),
        "par_vendeur":   get_ca_par_vendeur(df),
        "par_mois":      get_ca_par_mois(df),
        "par_categorie": get_ca_par_categorie(df),
        "par_region":    get_ca_par_region(df),
        "heatmap":       get_heatmap_vendeur_region(df),
        "top_produits":  get_top_produits(df),
    }

    logger.info("=== TRANSFORMATION TERMINÉE ===")
    return resultats