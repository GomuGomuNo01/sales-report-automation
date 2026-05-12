"""
Script de génération de données de ventes fictives mais réalistes.
Lance ce script UNE SEULE FOIS pour peupler le dossier data/raw/
"""

import pandas as pd
import numpy as np
from faker import Faker
import os
import random
from config import RAW_DATA_DIR

fake = Faker("fr_FR")
np.random.seed(42)
random.seed(42)

# ============================================================
# PARAMÈTRES DE GÉNÉRATION
# ============================================================

VENDEURS = [
    "Alice Martin", "Bob Dupont", "Claire Bernard",
    "David Leroy", "Emma Petit", "François Moreau",
    "Grace Simon", "Hugo Laurent", "Inès Michel",
    "Julien Garcia"
]

REGIONS = [
    "Île-de-France", "PACA", "Auvergne-Rhône-Alpes",
    "Nouvelle-Aquitaine", "Occitanie", "Hauts-de-France"
]

PRODUITS = {
    "Informatique": [
        ("Laptop Pro 15", 1200),
        ("Laptop Ultrabook", 950),
        ("PC Fixe Bureau", 750),
        ("Mac Mini", 1100),
    ],
    "Périphériques": [
        ("Écran 4K 27\"", 450),
        ("Clavier mécanique", 120),
        ("Souris sans fil", 45),
        ("Webcam HD", 85),
        ("Casque audio", 150),
    ],
    "Logiciels": [
        ("Licence Office 365", 120),
        ("Antivirus Pro", 60),
        ("Adobe Creative Cloud", 600),
    ],
    "Réseau": [
        ("Switch 24 ports", 320),
        ("Routeur WiFi 6", 180),
        ("Câble RJ45 (lot)", 35),
    ]
}

STATUTS_POIDS = ["Livré", "Livré", "Livré", "En cours", "Annulé", "Retourné"]


def generer_mois(annee: int, mois: int, nb_lignes: int) -> pd.DataFrame:
    """Génère un DataFrame de ventes pour un mois donné."""
    rows = []

    for _ in range(nb_lignes):
        # Catégorie et produit aléatoires
        categorie = random.choice(list(PRODUITS.keys()))
        produit, prix_base = random.choice(PRODUITS[categorie])

        # Légère variation du prix (+/- 10%)
        prix_unitaire = round(prix_base * random.uniform(0.90, 1.10), 2)

        # Quantité selon la catégorie
        if categorie == "Périphériques":
            quantite = random.randint(1, 20)
        elif categorie == "Logiciels":
            quantite = random.randint(1, 50)
        else:
            quantite = random.randint(1, 5)

        # Remise (0%, 5%, 10%, 15%)
        remise = random.choice([0, 0, 0, 0.05, 0.05, 0.10, 0.15])

        # Date aléatoire dans le mois
        jour = random.randint(1, 28)
        date = f"{annee}-{mois:02d}-{jour:02d}"

        rows.append({
            "date": date,
            "vendeur": random.choice(VENDEURS),
            "region": random.choice(REGIONS),
            "produit": produit,
            "categorie": categorie,
            "quantite": quantite,
            "prix_unitaire": prix_unitaire,
            "remise": remise,
            "statut": random.choice(STATUTS_POIDS)
        })

    return pd.DataFrame(rows)


def main():
    print("Génération des données de ventes...")

    # Générer 12 mois de données (2024)
    for mois in range(1, 13):
        # Volume variable selon le mois (pic en fin d'année)
        if mois in [11, 12]:
            nb_lignes = random.randint(120, 150)  # Pic Black Friday / Noël
        elif mois in [6, 7, 8]:
            nb_lignes = random.randint(60, 80)    # Creux estival
        else:
            nb_lignes = random.randint(85, 110)   # Mois normal

        df = generer_mois(2024, mois, nb_lignes)

        # Nom du fichier
        nom_mois = {
            1: "janvier", 2: "fevrier", 3: "mars", 4: "avril",
            5: "mai", 6: "juin", 7: "juillet", 8: "aout",
            9: "septembre", 10: "octobre", 11: "novembre", 12: "decembre"
        }[mois]

        chemin = os.path.join(RAW_DATA_DIR, f"ventes_{nom_mois}_2024.csv")
        df.to_csv(chemin, index=False, encoding="utf-8-sig")
        print(f"  ✓ {chemin} ({len(df)} lignes)")

    print(f"\nDonnées générées avec succès dans : {RAW_DATA_DIR}")
    print(f"Total : 12 fichiers CSV / ~1200 lignes de ventes")


if __name__ == "__main__":
    main()