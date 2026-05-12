import os

# ============================================================
# CHEMINS
# ============================================================

# Racine du projet (chemin absolu, peu importe d'où on lance)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Polices Unicode pour la génération PDF
FONT_REGULAR = os.path.join(BASE_DIR, "DejaVuSans.ttf")
FONT_BOLD    = os.path.join(BASE_DIR, "DejaVuSans-Bold.ttf")
FONT_ITALIC  = os.path.join(BASE_DIR, "DejaVuSans-Oblique.ttf")

# Dossiers de données
RAW_DATA_DIR      = os.path.join(BASE_DIR, "data", "raw")
PROCESSED_DATA_DIR = os.path.join(BASE_DIR, "data", "processed")

# Dossier de sortie des rapports PDF
OUTPUT_DIR        = os.path.join(BASE_DIR, "output", "rapports")

# Dossier temporaire pour les graphiques PNG
CHARTS_DIR        = os.path.join(BASE_DIR, "output", "charts")

# ============================================================
# PARAMÈTRES DES DONNÉES
# ============================================================

# Colonnes attendues dans les CSV bruts
EXPECTED_COLUMNS = [
    "date",
    "vendeur",
    "region",
    "produit",
    "categorie",
    "quantite",
    "prix_unitaire",
    "remise",
    "statut"
]

# Statuts valides (les autres seront filtrés)
VALID_STATUTS = ["Livré", "En cours"]

# Statuts à exclure du calcul du CA
EXCLUDED_STATUTS = ["Annulé", "Retourné"]

# ============================================================
# PARAMÈTRES DU RAPPORT
# ============================================================

RAPPORT_TITRE    = "Rapport de Performance Commerciale"
RAPPORT_AUTEUR   = "Service Commercial"
RAPPORT_COULEUR_PRINCIPALE = "#2E86AB"  # Bleu corporate

# Nombre de top vendeurs à afficher dans le rapport
TOP_VENDEURS_N = 10

# ============================================================
# CRÉATION AUTOMATIQUE DES DOSSIERS AU DÉMARRAGE
# ============================================================
LOGS_DIR = os.path.join(BASE_DIR, "output", "logs")
for _dir in [RAW_DATA_DIR, PROCESSED_DATA_DIR, OUTPUT_DIR, CHARTS_DIR, LOGS_DIR]:
    os.makedirs(_dir, exist_ok=True)