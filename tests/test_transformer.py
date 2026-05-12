"""
Tests unitaires pour src/transformer.py
Lancer : pytest tests/test_transformer.py -v
"""

import pytest
import pandas as pd
from src.transformer import (
    calculate_ca,
    get_kpis_globaux,
    get_ca_par_vendeur,
    get_ca_par_mois,
    get_ca_par_categorie,
    get_heatmap_vendeur_region,
    get_top_produits,
    transform,
)
from src.cleaner import clean


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def df_clean():
    """DataFrame nettoyé prêt pour la transformation."""
    raw = pd.DataFrame({
        "date":          ["2024-01-10", "2024-01-20", "2024-02-05",
                          "2024-02-15", "2024-03-01"],
        "vendeur":       ["Alice", "Bob", "Alice", "Claire", "Bob"],
        "region":        ["IDF", "PACA", "IDF", "PACA", "IDF"],
        "produit":       ["Laptop", "Souris", "Ecran", "Laptop", "Clavier"],
        "categorie":     ["Informatique", "Peripheriques", "Informatique",
                          "Informatique", "Peripheriques"],
        "quantite":      [2, 10, 1, 3, 5],
        "prix_unitaire": [1000.0, 20.0, 400.0, 1000.0, 80.0],
        "remise":        [0.10, 0.0, 0.05, 0.0, 0.10],
        "statut":        ["Livré", "Livré", "Annulé", "Livré", "Livré"]
    })
    return clean(raw)


@pytest.fixture
def df_avec_ca(df_clean):
    """DataFrame avec colonnes CA calculées."""
    return calculate_ca(df_clean.copy())


# ============================================================
# TESTS — calculate_ca
# ============================================================

class TestCalculateCa:

    def test_colonne_ca_brut_creee(self, df_clean):
        result = calculate_ca(df_clean.copy())
        assert "ca_brut" in result.columns

    def test_colonne_ca_net_creee(self, df_clean):
        result = calculate_ca(df_clean.copy())
        assert "ca_net" in result.columns

    def test_colonne_ca_comptabilise_creee(self, df_clean):
        result = calculate_ca(df_clean.copy())
        assert "ca_comptabilise" in result.columns

    def test_ca_brut_calcul_correct(self, df_clean):
        result = calculate_ca(df_clean.copy())
        # Ligne 0 : 2 × 1000 = 2000
        assert result.loc[0, "ca_brut"] == pytest.approx(2000.0)

    def test_ca_net_calcul_correct(self, df_clean):
        result = calculate_ca(df_clean.copy())
        # Ligne 0 : 2000 × (1 - 0.10) = 1800
        assert result.loc[0, "ca_net"] == pytest.approx(1800.0)

    def test_ca_annule_non_comptabilise(self, df_avec_ca):
        annules = df_avec_ca[df_avec_ca["statut"] == "Annulé"]
        assert (annules["ca_comptabilise"] == 0.0).all()

    def test_ca_livre_comptabilise(self, df_avec_ca):
        livres = df_avec_ca[df_avec_ca["statut"] == "Livré"]
        assert (livres["ca_comptabilise"] > 0).all()

    def test_remise_euros_calcul_correct(self, df_avec_ca):
        # Ligne 0 : remise = 2000 - 1800 = 200
        assert df_avec_ca.loc[0, "remise_euros"] == pytest.approx(200.0)


# ============================================================
# TESTS — get_kpis_globaux
# ============================================================

class TestGetKpisGlobaux:

    def test_retourne_dict(self, df_avec_ca):
        result = get_kpis_globaux(df_avec_ca)
        assert isinstance(result, dict)

    def test_cles_presentes(self, df_avec_ca):
        result = get_kpis_globaux(df_avec_ca)
        cles_attendues = [
            "ca_total", "nb_commandes", "panier_moyen",
            "nb_annulations", "taux_annulation",
            "remise_totale", "nb_vendeurs", "nb_produits"
        ]
        for cle in cles_attendues:
            assert cle in result

    def test_ca_total_positif(self, df_avec_ca):
        result = get_kpis_globaux(df_avec_ca)
        assert result["ca_total"] > 0

    def test_taux_annulation_entre_0_et_100(self, df_avec_ca):
        result = get_kpis_globaux(df_avec_ca)
        assert 0 <= result["taux_annulation"] <= 100

    def test_panier_moyen_positif(self, df_avec_ca):
        result = get_kpis_globaux(df_avec_ca)
        assert result["panier_moyen"] > 0

    def test_nb_vendeurs_correct(self, df_avec_ca):
        result = get_kpis_globaux(df_avec_ca)
        # Alice, Bob, Claire = 3 vendeurs
        assert result["nb_vendeurs"] == 3

    def test_annulations_comptees_correctement(self, df_avec_ca):
        result = get_kpis_globaux(df_avec_ca)
        # 1 ligne Annulé dans le fixture
        assert result["nb_annulations"] == 1


# ============================================================
# TESTS — get_ca_par_vendeur
# ============================================================

class TestGetCaParVendeur:

    def test_retourne_dataframe(self, df_avec_ca):
        result = get_ca_par_vendeur(df_avec_ca)
        assert isinstance(result, pd.DataFrame)

    def test_colonnes_presentes(self, df_avec_ca):
        result = get_ca_par_vendeur(df_avec_ca)
        assert "vendeur" in result.columns
        assert "ca_total" in result.columns

    def test_trie_par_ca_decroissant(self, df_avec_ca):
        result = get_ca_par_vendeur(df_avec_ca)
        ca_values = list(result["ca_total"])
        assert ca_values == sorted(ca_values, reverse=True)

    def test_ca_non_negatif(self, df_avec_ca):
        result = get_ca_par_vendeur(df_avec_ca)
        assert (result["ca_total"] >= 0).all()


# ============================================================
# TESTS — get_ca_par_mois
# ============================================================

class TestGetCaParMois:

    def test_retourne_dataframe(self, df_avec_ca):
        result = get_ca_par_mois(df_avec_ca)
        assert isinstance(result, pd.DataFrame)

    def test_colonnes_presentes(self, df_avec_ca):
        result = get_ca_par_mois(df_avec_ca)
        for col in ["annee", "mois", "mois_nom", "ca_total"]:
            assert col in result.columns

    def test_trie_chronologiquement(self, df_avec_ca):
        result = get_ca_par_mois(df_avec_ca)
        mois = list(result["mois"])
        assert mois == sorted(mois)

    def test_nb_mois_correct(self, df_avec_ca):
        result = get_ca_par_mois(df_avec_ca)
        # Données sur jan, fev, mar = 3 mois
        assert len(result) == 3


# ============================================================
# TESTS — get_ca_par_categorie
# ============================================================

class TestGetCaParCategorie:

    def test_retourne_dataframe(self, df_avec_ca):
        result = get_ca_par_categorie(df_avec_ca)
        assert isinstance(result, pd.DataFrame)

    def test_colonnes_presentes(self, df_avec_ca):
        result = get_ca_par_categorie(df_avec_ca)
        assert "categorie" in result.columns
        assert "ca_total" in result.columns

    def test_trie_par_ca_decroissant(self, df_avec_ca):
        result = get_ca_par_categorie(df_avec_ca)
        ca_values = list(result["ca_total"])
        assert ca_values == sorted(ca_values, reverse=True)

    def test_nb_categories_correct(self, df_avec_ca):
        result = get_ca_par_categorie(df_avec_ca)
        # Informatique, Peripheriques = 2 catégories
        assert len(result) == 2

    def test_ca_non_negatif(self, df_avec_ca):
        result = get_ca_par_categorie(df_avec_ca)
        assert (result["ca_total"] >= 0).all()


# ============================================================
# TESTS — get_heatmap_vendeur_region
# ============================================================

class TestGetHeatmapVendeurRegion:

    def test_retourne_dataframe(self, df_avec_ca):
        result = get_heatmap_vendeur_region(df_avec_ca)
        assert isinstance(result, pd.DataFrame)

    def test_index_sont_les_vendeurs(self, df_avec_ca):
        result = get_heatmap_vendeur_region(df_avec_ca)
        for vendeur in ["Alice", "Bob", "Claire"]:
            assert vendeur in result.index

    def test_colonnes_sont_les_regions(self, df_avec_ca):
        result = get_heatmap_vendeur_region(df_avec_ca)
        for region in ["IDF", "PACA"]:
            assert region in result.columns

    def test_valeurs_non_negatives(self, df_avec_ca):
        result = get_heatmap_vendeur_region(df_avec_ca)
        assert (result >= 0).all().all()

    def test_cellules_vides_remplies_par_zero(self, df_avec_ca):
        result = get_heatmap_vendeur_region(df_avec_ca)
        # Claire n'a vendu qu'en PACA → IDF doit être 0
        assert result.loc["Claire", "IDF"] == 0.0


# ============================================================
# TESTS — get_top_produits
# ============================================================

class TestGetTopProduits:

    def test_retourne_dataframe(self, df_avec_ca):
        result = get_top_produits(df_avec_ca)
        assert isinstance(result, pd.DataFrame)

    def test_colonnes_presentes(self, df_avec_ca):
        result = get_top_produits(df_avec_ca)
        assert "produit" in result.columns
        assert "ca_total" in result.columns

    def test_limite_au_top_n(self, df_avec_ca):
        result = get_top_produits(df_avec_ca, n=2)
        assert len(result) <= 2

    def test_trie_par_ca_decroissant(self, df_avec_ca):
        result = get_top_produits(df_avec_ca)
        ca_values = list(result["ca_total"])
        assert ca_values == sorted(ca_values, reverse=True)


# ============================================================
# TEST INTÉGRATION — transform() complet
# ============================================================

class TestTransformIntegration:

    def test_retourne_dict(self, df_clean):
        result = transform(df_clean.copy())
        assert isinstance(result, dict)

    def test_cles_presentes(self, df_clean):
        result = transform(df_clean.copy())
        cles_attendues = [
            "df", "kpis", "par_vendeur", "par_mois",
            "par_categorie", "par_region", "heatmap", "top_produits",
        ]
        for cle in cles_attendues:
            assert cle in result

    def test_df_contient_colonnes_ca(self, df_clean):
        result = transform(df_clean.copy())
        for col in ["ca_brut", "ca_net", "ca_comptabilise", "remise_euros"]:
            assert col in result["df"].columns

    def test_kpis_ca_coherent_avec_par_vendeur(self, df_clean):
        result = transform(df_clean.copy())
        ca_kpi = result["kpis"]["ca_total"]
        ca_vendeurs = result["par_vendeur"]["ca_total"].sum()
        assert ca_kpi == pytest.approx(ca_vendeurs, rel=1e-3)
