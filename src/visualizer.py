"""
Visualizer : génération des 4 graphiques du rapport commercial
"""

import os
import logging
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
from config import CHARTS_DIR, RAPPORT_COULEUR_PRINCIPALE

matplotlib.use("Agg")  # Mode non-interactif (pas d'affichage fenêtre)

logger = logging.getLogger(__name__)

# ============================================================
# STYLE GLOBAL
# ============================================================

COULEUR_PRINCIPALE  = RAPPORT_COULEUR_PRINCIPALE   # Bleu corporate
COULEUR_SECONDAIRE  = "#E8F4F8"                     # Bleu très clair (fond)
COULEUR_ACCENT      = "#F18F01"                     # Orange (highlight)
PALETTE_CATEGORIELLE = "Blues_r"

plt.rcParams.update({
    "figure.facecolor":  "white",
    "axes.facecolor":    COULEUR_SECONDAIRE,
    "axes.grid":         True,
    "grid.alpha":        0.4,
    "grid.linestyle":    "--",
    "font.family":       "DejaVu Sans",
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "axes.titlesize":    14,
    "axes.titleweight":  "bold",
    "axes.labelsize":    11,
    "xtick.labelsize":   9,
    "ytick.labelsize":   9,
})


def _formatter_euros(x, _):
    """Formate les valeurs en k€ ou M€ sur les axes."""
    if x >= 1_000_000:
        return f"{x/1_000_000:.1f}M€"
    elif x >= 1_000:
        return f"{x/1_000:.0f}k€"
    return f"{x:.0f}€"


def _sauvegarder(fig: plt.Figure, nom_fichier: str,
                 charts_dir: str = CHARTS_DIR) -> str:
    """Sauvegarde la figure en PNG dans charts_dir et retourne le chemin."""
    os.makedirs(charts_dir, exist_ok=True)
    chemin = os.path.join(charts_dir, nom_fichier)
    fig.savefig(chemin, dpi=150, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    logger.info(f"  ✓ Graphique sauvegardé : {nom_fichier}")
    return chemin


# ============================================================
# GRAPHIQUE 1 — Bar chart : Top vendeurs par CA
# ============================================================

def chart_top_vendeurs(df_vendeurs: pd.DataFrame,
                       charts_dir: str = CHARTS_DIR) -> str:
    """
    Bar chart horizontal — Top N vendeurs par CA.
    df_vendeurs : colonnes [vendeur, ca_total]
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    # Trier par CA croissant pour lire de haut en bas
    df_sorted = df_vendeurs.sort_values("ca_total", ascending=True)

    bars = ax.barh(
        df_sorted["vendeur"],
        df_sorted["ca_total"],
        color=COULEUR_PRINCIPALE,
        edgecolor="white",
        height=0.6
    )

    # Mettre en évidence le meilleur vendeur
    bars[-1].set_color(COULEUR_ACCENT)

    # Valeurs au bout de chaque barre
    for bar in bars:
        largeur = bar.get_width()
        ax.text(
            largeur + largeur * 0.01,
            bar.get_y() + bar.get_height() / 2,
            _formatter_euros(largeur, None),
            va="center", ha="left",
            fontsize=9, fontweight="bold"
        )

    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_formatter_euros))
    ax.set_xlabel("Chiffre d'affaires")
    ax.set_title("Top Vendeurs par Chiffre d'Affaires")
    ax.set_xlim(0, df_sorted["ca_total"].max() * 1.18)
    fig.tight_layout()

    return _sauvegarder(fig, "01_top_vendeurs.png", charts_dir)


# ============================================================
# GRAPHIQUE 2 — Line chart : Évolution mensuelle du CA
# ============================================================

def chart_evolution_mensuelle(df_mois: pd.DataFrame,
                              charts_dir: str = CHARTS_DIR) -> str:
    """
    Line chart — Évolution du CA mois par mois.
    df_mois : colonnes [mois, mois_nom, ca_total]
    """
    fig, ax = plt.subplots(figsize=(12, 5))

    ax.plot(
        df_mois["mois_nom"],
        df_mois["ca_total"],
        color=COULEUR_PRINCIPALE,
        linewidth=2.5,
        marker="o",
        markersize=8,
        markerfacecolor=COULEUR_ACCENT,
        markeredgecolor="white",
        markeredgewidth=2,
        zorder=3
    )

    # Remplissage sous la courbe
    ax.fill_between(
        df_mois["mois_nom"],
        df_mois["ca_total"],
        alpha=0.15,
        color=COULEUR_PRINCIPALE
    )

    # Valeurs sur chaque point
    for _, row in df_mois.iterrows():
        ax.annotate(
            _formatter_euros(row["ca_total"], None),
            xy=(row["mois_nom"], row["ca_total"]),
            xytext=(0, 12),
            textcoords="offset points",
            ha="center", fontsize=8, fontweight="bold",
            color=COULEUR_PRINCIPALE
        )

    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_formatter_euros))
    ax.set_xlabel("Mois")
    ax.set_ylabel("Chiffre d'affaires")
    ax.set_title("Évolution Mensuelle du Chiffre d'Affaires")
    plt.xticks(rotation=30, ha="right")
    fig.tight_layout()

    return _sauvegarder(fig, "02_evolution_mensuelle.png", charts_dir)


# ============================================================
# GRAPHIQUE 3 — Pie chart : Répartition par catégorie
# ============================================================

def chart_repartition_categorie(df_categorie: pd.DataFrame,
                                charts_dir: str = CHARTS_DIR) -> str:
    """
    Pie chart — Répartition du CA par catégorie produit.
    df_categorie : colonnes [categorie, ca_total]
    """
    fig, (ax_pie, ax_bar) = plt.subplots(
        1, 2, figsize=(13, 6),
        gridspec_kw={"width_ratios": [1.2, 1]}
    )

    # --- Camembert ---
    couleurs = sns.color_palette("Blues_r", len(df_categorie))
    explode  = [0.05] * len(df_categorie)
    explode[0] = 0.12   # Mettre en avant la 1ère catégorie

    wedges, texts, autotexts = ax_pie.pie(
        df_categorie["ca_total"],
        labels=df_categorie["categorie"],
        autopct="%1.1f%%",
        colors=couleurs,
        explode=explode,
        startangle=90,
        wedgeprops={"edgecolor": "white", "linewidth": 2}
    )

    for autotext in autotexts:
        autotext.set_fontsize(9)
        autotext.set_fontweight("bold")

    ax_pie.set_title("Répartition par Catégorie")
    ax_pie.set_facecolor("white")

    # --- Bar chart associé ---
    df_sorted = df_categorie.sort_values("ca_total")
    ax_bar.barh(
        df_sorted["categorie"],
        df_sorted["ca_total"],
        color=couleurs[::-1],
        edgecolor="white",
        height=0.5
    )

    for bar in ax_bar.patches:
        ax_bar.text(
            bar.get_width() + bar.get_width() * 0.02,
            bar.get_y() + bar.get_height() / 2,
            _formatter_euros(bar.get_width(), None),
            va="center", ha="left", fontsize=9
        )

    ax_bar.xaxis.set_major_formatter(mticker.FuncFormatter(_formatter_euros))
    ax_bar.set_title("CA par Catégorie (détail)")
    ax_bar.set_xlim(0, df_sorted["ca_total"].max() * 1.22)
    ax_bar.set_facecolor(COULEUR_SECONDAIRE)

    fig.suptitle("Analyse par Catégorie de Produits",
                 fontsize=15, fontweight="bold", y=1.01)
    fig.tight_layout()

    return _sauvegarder(fig, "03_repartition_categorie.png", charts_dir)


# ============================================================
# GRAPHIQUE 4 — Heatmap : Performance vendeur × région
# ============================================================

def chart_heatmap_vendeur_region(df_heatmap: pd.DataFrame,
                                 charts_dir: str = CHARTS_DIR) -> str:
    """
    Heatmap — CA par vendeur et par région.
    df_heatmap : pivot table vendeur × région
    """
    fig, ax = plt.subplots(figsize=(12, 7))

    sns.heatmap(
        df_heatmap,
        ax=ax,
        cmap="Blues",
        annot=True,
        fmt=".0f",
        linewidths=0.5,
        linecolor="white",
        cbar_kws={"label": "CA (€)", "shrink": 0.8},
        annot_kws={"size": 9}
    )

    ax.set_title("Performance Vendeurs par Région (CA en €)")
    ax.set_xlabel("Région")
    ax.set_ylabel("Vendeur")
    plt.xticks(rotation=30, ha="right")
    plt.yticks(rotation=0)

    # Colorbar en euros
    cbar = ax.collections[0].colorbar
    cbar.ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(_formatter_euros)
    )

    fig.tight_layout()

    return _sauvegarder(fig, "04_heatmap_vendeur_region.png", charts_dir)


# ============================================================
# GRAPHIQUE 5 — Bar chart : Top produits par CA
# ============================================================

def chart_top_produits(df_produits: pd.DataFrame,
                       charts_dir: str = CHARTS_DIR) -> str:
    """
    Bar chart horizontal — Top N produits par CA.
    df_produits : colonnes [produit, ca_total]
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    df_sorted = df_produits.sort_values("ca_total", ascending=True)
    colors = [
        COULEUR_ACCENT if i == len(df_sorted) - 1 else COULEUR_PRINCIPALE
        for i in range(len(df_sorted))
    ]

    bars = ax.barh(
        df_sorted["produit"],
        df_sorted["ca_total"],
        color=colors,
        edgecolor="white",
        height=0.6
    )

    for bar in bars:
        largeur = bar.get_width()
        ax.text(
            largeur + largeur * 0.01,
            bar.get_y() + bar.get_height() / 2,
            _formatter_euros(largeur, None),
            va="center", ha="left",
            fontsize=9, fontweight="bold"
        )

    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_formatter_euros))
    ax.set_xlabel("Chiffre d'affaires")
    ax.set_title("Top Produits par Chiffre d'Affaires")
    ax.set_xlim(0, df_sorted["ca_total"].max() * 1.18)
    fig.tight_layout()

    return _sauvegarder(fig, "05_top_produits.png", charts_dir)


# ============================================================
# POINT D'ENTRÉE PRINCIPAL
# ============================================================

def generate_all_charts(resultats: dict, charts_dir: str = CHARTS_DIR) -> dict:
    """
    Génère les 5 graphiques à partir du dict de résultats
    retourné par transformer.transform().

    Args:
        resultats  : dict retourné par transformer.transform()
        charts_dir : dossier de sortie des PNG (défaut : output/charts)

    Returns:
        dict avec les chemins vers chaque fichier PNG
    """
    logger.info("=== ÉTAPE 4 : VISUALISATION ===")

    chemins = {
        "top_vendeurs":          chart_top_vendeurs(resultats["par_vendeur"], charts_dir),
        "evolution_mensuelle":   chart_evolution_mensuelle(resultats["par_mois"], charts_dir),
        "repartition_categorie": chart_repartition_categorie(resultats["par_categorie"], charts_dir),
        "heatmap":               chart_heatmap_vendeur_region(resultats["heatmap"], charts_dir),
        "top_produits":          chart_top_produits(resultats["top_produits"], charts_dir),
    }

    logger.info(f"5 graphiques générés ({os.path.basename(charts_dir.rstrip(os.sep)) or charts_dir})")
    return chemins