"""
Reporter : génération du rapport PDF final
"""

import os
import logging
from datetime import datetime
from fpdf import FPDF, XPos, YPos
from config import (
    OUTPUT_DIR,
    RAPPORT_TITRE,
    RAPPORT_AUTEUR,
    RAPPORT_COULEUR_PRINCIPALE,
    FONT_REGULAR,
    FONT_BOLD,
    FONT_ITALIC,
)

logger = logging.getLogger(__name__)

# ============================================================
# COULEURS (RGB)
# ============================================================

def _hex_to_rgb(hex_color: str) -> tuple:
    """Convertit une couleur hex en tuple RGB."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


COULEUR_PRINCIPALE = _hex_to_rgb(RAPPORT_COULEUR_PRINCIPALE)
COULEUR_ACCENT     = _hex_to_rgb("#F18F01")
COULEUR_GRIS_CLAIR = (245, 245, 245)
COULEUR_GRIS_TEXTE = (80, 80, 80)
COULEUR_BLANC      = (255, 255, 255)
COULEUR_NOIR       = (30, 30, 30)



# ============================================================
# CLASSE PDF PERSONNALISÉE
# ============================================================

class RapportPDF(FPDF):
    """
    Classe FPDF personnalisée avec header/footer automatiques
    et méthodes utilitaires pour le rapport commercial.
    """

    def __init__(self, titre: str, periode: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.titre   = titre
        self.periode = periode
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(left=15, top=15, right=15)

        # Police Unicode — supporte accents, euro, caractères spéciaux
        self.add_font("DejaVu", style="",  fname=FONT_REGULAR)
        self.add_font("DejaVu", style="B", fname=FONT_BOLD)
        self.add_font("DejaVu", style="I", fname=FONT_ITALIC)

    # ----------------------------------------------------------
    # HEADER
    # ----------------------------------------------------------
    def header(self):
        self.set_fill_color(*COULEUR_PRINCIPALE)
        self.rect(0, 0, 210, 12, style="F")

        self.set_font("DejaVu", "B", 10)
        self.set_text_color(*COULEUR_BLANC)
        self.set_xy(15, 2)
        self.cell(0, 8, self.titre, align="L")

        self.set_xy(0, 2)
        self.cell(195, 8, self.periode, align="R")
        self.set_text_color(*COULEUR_NOIR)
        self.ln(10)

    # ----------------------------------------------------------
    # FOOTER
    # ----------------------------------------------------------
    def footer(self):
        self.set_y(-12)
        self.set_font("DejaVu", "I", 8)
        self.set_text_color(*COULEUR_GRIS_TEXTE)

        self.set_draw_color(*COULEUR_PRINCIPALE)
        self.set_line_width(0.3)
        self.line(15, self.get_y(), 195, self.get_y())
        self.ln(1)

        # Tiret simple à la place du em dash
        self.cell(0, 5, f"{RAPPORT_AUTEUR}  -  Confidentiel", align="L")
        self.cell(0, 5, f"Page {self.page_no()}", align="R")
        self.set_text_color(*COULEUR_NOIR)

    # ----------------------------------------------------------
    # UTILITAIRES
    # ----------------------------------------------------------

    def titre_section(self, texte: str):
        """Titre de section avec bande colorée."""
        self.ln(4)
        self.set_fill_color(*COULEUR_PRINCIPALE)
        self.set_text_color(*COULEUR_BLANC)
        self.set_font("DejaVu", "B", 12)
        self.cell(0, 9, f"  {texte}", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*COULEUR_NOIR)
        self.ln(3)

    def sous_titre(self, texte: str):
        """Sous-titre discret."""
        self.set_font("DejaVu", "B", 10)
        self.set_text_color(*COULEUR_PRINCIPALE)
        self.cell(0, 7, texte, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*COULEUR_NOIR)

    def texte(self, contenu: str, taille: int = 10):
        """Paragraphe de texte standard."""
        self.set_font("DejaVu", "", taille)
        self.set_text_color(*COULEUR_GRIS_TEXTE)
        self.multi_cell(0, 6, contenu)
        self.set_text_color(*COULEUR_NOIR)

    def separateur(self):
        """Ligne horizontale légère."""
        self.ln(2)
        self.set_draw_color(*COULEUR_PRINCIPALE)
        self.set_line_width(0.2)
        self.line(15, self.get_y(), 195, self.get_y())
        self.ln(4)


# ============================================================
# PAGE 1 — PAGE DE GARDE
# ============================================================

def _page_garde(pdf: RapportPDF, kpis: dict, periode: str):
    pdf.add_page()

    pdf.set_fill_color(*COULEUR_PRINCIPALE)
    pdf.rect(0, 25, 210, 55, style="F")

    pdf.set_xy(0, 35)
    pdf.set_font("DejaVu", "B", 24)
    pdf.set_text_color(*COULEUR_BLANC)
    pdf.cell(0, 12, RAPPORT_TITRE, align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("DejaVu", "", 14)
    pdf.cell(0, 10, periode, align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("DejaVu", "I", 10)
    pdf.cell(
        0, 8,
        f"Genere automatiquement le {datetime.now().strftime('%d/%m/%Y a %H:%M')}",
        align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT
    )

    pdf.set_text_color(*COULEUR_NOIR)
    pdf.ln(25)

    # ---- 4 KPI cards ----
    pdf.sous_titre("Indicateurs Cles de Performance")
    pdf.ln(3)

    cards = [
        ("CA Total",        f"{kpis['ca_total']:,.2f} EUR"),
        ("Commandes",       f"{kpis['nb_commandes']}"),
        ("Panier Moyen",    f"{kpis['panier_moyen']:,.2f} EUR"),
        ("Taux Annulation", f"{kpis['taux_annulation']} %"),
    ]

    x_start = 15
    card_w  = 42
    card_h  = 28
    gap     = 4   # 4×42 + 3×4 = 180 mm = pleine largeur utile

    for i, (label, valeur) in enumerate(cards):
        x = x_start + i * (card_w + gap)
        y = pdf.get_y()

        pdf.set_fill_color(*COULEUR_GRIS_CLAIR)
        pdf.rect(x, y, card_w, card_h, style="F")

        pdf.set_fill_color(*COULEUR_PRINCIPALE)
        pdf.rect(x, y, card_w, 3, style="F")

        pdf.set_xy(x, y + 5)
        pdf.set_font("DejaVu", "", 8)
        pdf.set_text_color(*COULEUR_GRIS_TEXTE)
        pdf.cell(card_w, 5, label, align="C")

        pdf.set_xy(x, y + 12)
        pdf.set_font("DejaVu", "B", 11)
        pdf.set_text_color(*COULEUR_PRINCIPALE)
        pdf.cell(card_w, 8, valeur, align="C")

    pdf.set_text_color(*COULEUR_NOIR)
    pdf.ln(card_h + 8)

    # ---- Ligne secondaire : 4 métriques sur pleine largeur ----
    pdf.separateur()
    cards2 = [
        ("Vendeurs actifs",   str(kpis["nb_vendeurs"])),
        ("Produits vendus",   str(kpis["nb_produits"])),
        ("Remises accordees", f"{kpis['remise_totale']:,.2f} EUR"),
        ("Annulations",       str(kpis["nb_annulations"])),
    ]

    card_w2 = 45   # 4 × 45 = 180 mm = pleine largeur utile
    y_val   = pdf.get_y()

    for i, (label, valeur) in enumerate(cards2):
        pdf.set_xy(x_start + i * card_w2, y_val)
        pdf.set_font("DejaVu", "B", 12)
        pdf.set_text_color(*COULEUR_PRINCIPALE)
        pdf.cell(card_w2, 8, valeur, align="C")

    for i, (label, valeur) in enumerate(cards2):
        pdf.set_xy(x_start + i * card_w2, y_val + 8)
        pdf.set_font("DejaVu", "", 8)
        pdf.set_text_color(*COULEUR_GRIS_TEXTE)
        pdf.cell(card_w2, 5, label, align="C")

    pdf.set_xy(x_start, y_val + 13)
    pdf.set_text_color(*COULEUR_NOIR)


# ============================================================
# PAGE 2 — TOP VENDEURS
# ============================================================

def _page_vendeurs(pdf: RapportPDF, chemins_charts: dict, df_vendeurs):
    pdf.add_page()
    pdf.titre_section("Analyse des Performances Vendeurs")

    pdf.image(chemins_charts["top_vendeurs"], x=15, w=175)
    pdf.ln(4)

    pdf.sous_titre("Detail par Vendeur")
    pdf.ln(2)

    col_w   = [80, 45, 45]
    headers = ["Vendeur", "CA Total (EUR)", "Rang"]

    pdf.set_fill_color(*COULEUR_PRINCIPALE)
    pdf.set_text_color(*COULEUR_BLANC)
    pdf.set_font("DejaVu", "B", 9)
    for h, w in zip(headers, col_w):
        pdf.cell(w, 7, h, border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("DejaVu", "", 9)
    for idx, row in df_vendeurs.iterrows():
        fill = idx % 2 == 0
        pdf.set_fill_color(*COULEUR_GRIS_CLAIR if fill else COULEUR_BLANC)
        pdf.set_text_color(*COULEUR_NOIR)
        pdf.cell(col_w[0], 6, str(row["vendeur"]),
                 border=1, fill=fill, align="L")
        pdf.cell(col_w[1], 6, f"{row['ca_total']:,.2f}",
                 border=1, fill=fill, align="R")
        pdf.cell(col_w[2], 6, f"#{idx + 1}",
                 border=1, fill=fill, align="C")
        pdf.ln()

    pdf.set_text_color(*COULEUR_NOIR)


# ============================================================
# PAGE 3 — ÉVOLUTION MENSUELLE
# ============================================================

def _page_evolution(pdf: RapportPDF, chemins_charts: dict, df_mois):
    pdf.add_page()
    pdf.titre_section("Evolution Mensuelle du Chiffre d'Affaires")

    pdf.image(chemins_charts["evolution_mensuelle"], x=15, w=175)
    pdf.ln(4)

    pdf.sous_titre("Recapitulatif Mensuel")
    pdf.ln(2)

    col_w   = [50, 40, 40, 40]
    headers = ["Mois", "CA (EUR)", "Vs mois prec.", "Cumul (EUR)"]

    pdf.set_fill_color(*COULEUR_PRINCIPALE)
    pdf.set_text_color(*COULEUR_BLANC)
    pdf.set_font("DejaVu", "B", 9)
    for h, w in zip(headers, col_w):
        pdf.cell(w, 7, h, border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("DejaVu", "", 9)
    cumul        = 0
    ca_precedent = None

    for idx, row in df_mois.iterrows():
        fill  = idx % 2 == 0
        ca    = row["ca_total"]
        cumul += ca

        pdf.set_fill_color(*COULEUR_GRIS_CLAIR if fill else COULEUR_BLANC)

        if ca_precedent is not None and ca_precedent > 0:
            variation     = ((ca - ca_precedent) / ca_precedent) * 100
            variation_str = f"{'+' if variation >= 0 else ''}{variation:.1f}%"
        else:
            variation_str = "-"

        pdf.set_text_color(*COULEUR_NOIR)
        pdf.cell(col_w[0], 6, str(row["mois_nom"]).capitalize(),
                 border=1, fill=fill, align="L")
        pdf.cell(col_w[1], 6, f"{ca:,.2f}",
                 border=1, fill=fill, align="R")

        if variation_str != "-":
            pdf.set_text_color(
                *(34, 139, 34) if "+" in variation_str else (200, 0, 0)
            )
        pdf.cell(col_w[2], 6, variation_str,
                 border=1, fill=fill, align="C")

        pdf.set_text_color(*COULEUR_NOIR)
        pdf.cell(col_w[3], 6, f"{cumul:,.2f}",
                 border=1, fill=fill, align="R")
        pdf.ln()

        ca_precedent = ca

    pdf.set_text_color(*COULEUR_NOIR)


# ============================================================
# PAGE 4 — ANALYSE PAR CATÉGORIE
# ============================================================

def _page_categories(pdf: RapportPDF, chemins_charts: dict, df_categorie):
    pdf.add_page()
    pdf.titre_section("Repartition par Categorie de Produits")

    pdf.image(chemins_charts["repartition_categorie"], x=15, w=175)
    pdf.ln(4)

    pdf.sous_titre("Detail par Categorie")
    pdf.ln(2)

    ca_total_global = df_categorie["ca_total"].sum()
    col_w   = [60, 50, 50]
    headers = ["Categorie", "CA (EUR)", "Part (%)"]

    pdf.set_fill_color(*COULEUR_PRINCIPALE)
    pdf.set_text_color(*COULEUR_BLANC)
    pdf.set_font("DejaVu", "B", 9)
    for h, w in zip(headers, col_w):
        pdf.cell(w, 7, h, border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("DejaVu", "", 9)
    for idx, row in df_categorie.iterrows():
        fill = idx % 2 == 0
        pdf.set_fill_color(*COULEUR_GRIS_CLAIR if fill else COULEUR_BLANC)
        pdf.set_text_color(*COULEUR_NOIR)
        part = (row["ca_total"] / ca_total_global * 100) if ca_total_global else 0
        pdf.cell(col_w[0], 6, str(row["categorie"]),
                 border=1, fill=fill, align="L")
        pdf.cell(col_w[1], 6, f"{row['ca_total']:,.2f}",
                 border=1, fill=fill, align="R")
        pdf.cell(col_w[2], 6, f"{part:.1f}%",
                 border=1, fill=fill, align="C")
        pdf.ln()

    pdf.set_text_color(*COULEUR_NOIR)


# ============================================================
# PAGE 5 — HEATMAP VENDEUR × RÉGION
# ============================================================

def _page_heatmap(pdf: RapportPDF, chemins_charts: dict, df_region=None):
    pdf.add_page()
    pdf.titre_section("Performance Vendeurs par Region")

    pdf.texte(
        "La heatmap ci-dessous represente le chiffre d'affaires "
        "genere par chaque vendeur dans chaque region. "
        "Les cases plus foncees indiquent un CA plus eleve."
    )
    pdf.ln(3)
    pdf.image(chemins_charts["heatmap"], x=15, w=175)

    if df_region is not None and len(df_region) > 0:
        pdf.ln(4)
        pdf.sous_titre("Recapitulatif par Region")
        pdf.ln(2)

        ca_total_global = df_region["ca_total"].sum()
        col_w   = [70, 55, 45]
        headers = ["Region", "CA (EUR)", "Part (%)"]

        pdf.set_fill_color(*COULEUR_PRINCIPALE)
        pdf.set_text_color(*COULEUR_BLANC)
        pdf.set_font("DejaVu", "B", 9)
        for h, w in zip(headers, col_w):
            pdf.cell(w, 7, h, border=1, fill=True, align="C")
        pdf.ln()

        pdf.set_font("DejaVu", "", 9)
        for idx, row in df_region.iterrows():
            fill = idx % 2 == 0
            part = (row["ca_total"] / ca_total_global * 100) if ca_total_global else 0
            pdf.set_fill_color(*COULEUR_GRIS_CLAIR if fill else COULEUR_BLANC)
            pdf.set_text_color(*COULEUR_NOIR)
            pdf.cell(col_w[0], 6, str(row["region"]),         border=1, fill=fill, align="L")
            pdf.cell(col_w[1], 6, f"{row['ca_total']:,.2f}",  border=1, fill=fill, align="R")
            pdf.cell(col_w[2], 6, f"{part:.1f}%",             border=1, fill=fill, align="C")
            pdf.ln()

        pdf.set_text_color(*COULEUR_NOIR)


# ============================================================
# PAGE 6 — TOP PRODUITS
# ============================================================

def _page_top_produits(pdf: RapportPDF, chemins_charts: dict, df_produits):
    pdf.add_page()
    pdf.titre_section("Top Produits par Chiffre d'Affaires")

    pdf.image(chemins_charts["top_produits"], x=15, w=175)
    pdf.ln(4)

    pdf.sous_titre("Detail par Produit")
    pdf.ln(2)

    col_w   = [95, 55, 20]
    headers = ["Produit", "CA Total (EUR)", "Rang"]

    pdf.set_fill_color(*COULEUR_PRINCIPALE)
    pdf.set_text_color(*COULEUR_BLANC)
    pdf.set_font("DejaVu", "B", 9)
    for h, w in zip(headers, col_w):
        pdf.cell(w, 7, h, border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("DejaVu", "", 9)
    for rank, (_, row) in enumerate(df_produits.iterrows(), start=1):
        fill = rank % 2 == 0
        pdf.set_fill_color(*COULEUR_GRIS_CLAIR if fill else COULEUR_BLANC)
        pdf.set_text_color(*COULEUR_NOIR)
        pdf.cell(col_w[0], 6, str(row["produit"]),        border=1, fill=fill, align="L")
        pdf.cell(col_w[1], 6, f"{row['ca_total']:,.2f}",  border=1, fill=fill, align="R")
        pdf.cell(col_w[2], 6, f"#{rank}",                 border=1, fill=fill, align="C")
        pdf.ln()

    pdf.set_text_color(*COULEUR_NOIR)


# ============================================================
# POINT D'ENTRÉE PRINCIPAL
# ============================================================

def generate_report(resultats: dict, chemins_charts: dict,
                    periode: str = None) -> str:
    """
    Genere le rapport PDF complet.

    Args:
        resultats      : dict retourne par transformer.transform()
        chemins_charts : dict retourne par visualizer.generate_all_charts()
        periode        : ex "Janvier - Decembre 2024"

    Returns:
        str : chemin vers le fichier PDF genere
    """
    logger.info("=== ETAPE 5 : GENERATION DU RAPPORT PDF ===")

    if periode is None:
        periode = datetime.now().strftime("%B %Y").capitalize()

    pdf = RapportPDF(titre=RAPPORT_TITRE, periode=periode)

    _page_garde(pdf, resultats["kpis"], periode)
    _page_vendeurs(pdf, chemins_charts, resultats["par_vendeur"])
    _page_evolution(pdf, chemins_charts, resultats["par_mois"])
    _page_categories(pdf, chemins_charts, resultats["par_categorie"])
    _page_heatmap(pdf, chemins_charts, resultats["par_region"])
    _page_top_produits(pdf, chemins_charts, resultats["top_produits"])

    nom_fichier = f"rapport_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    chemin_pdf  = os.path.join(OUTPUT_DIR, nom_fichier)
    pdf.output(chemin_pdf)

    logger.info(f"Rapport PDF genere : {chemin_pdf}")
    return chemin_pdf