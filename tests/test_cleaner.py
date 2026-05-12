"""
Tests unitaires pour src/cleaner.py
Lancer : pytest tests/test_cleaner.py -v
"""

import pytest
import pandas as pd
import numpy as np
from src.cleaner import (
    remove_duplicates,
    handle_missing_values,
    fix_data_types,
    fix_remise,
    fix_negative_values,
    standardize_statut,
    add_time_columns,
    clean
)


# ============================================================
# FIXTURES — données de test réutilisables
# ============================================================

@pytest.fixture
def df_valide():
    """DataFrame propre et valide — cas nominal."""
    return pd.DataFrame({
        "date":          ["2024-01-15", "2024-02-20", "2024-03-10"],
        "vendeur":       ["Alice Martin", "Bob Dupont", "Claire Bernard"],
        "region":        ["Ile-de-France", "PACA", "Occitanie"],
        "produit":       ["Laptop Pro", "Souris", "Ecran 4K"],
        "categorie":     ["Informatique", "Peripheriques", "Informatique"],
        "quantite":      [2, 10, 1],
        "prix_unitaire": [1200.0, 25.0, 450.0],
        "remise":        [0.05, 0.0, 0.10],
        "statut":        ["Livré", "Livré", "En cours"]
    })


@pytest.fixture
def df_avec_doublons():
    """DataFrame avec une ligne dupliquée."""
    return pd.DataFrame({
        "date":          ["2024-01-15", "2024-01-15", "2024-03-10"],
        "vendeur":       ["Alice Martin", "Alice Martin", "Bob Dupont"],
        "region":        ["Ile-de-France", "Ile-de-France", "PACA"],
        "produit":       ["Laptop Pro", "Laptop Pro", "Souris"],
        "categorie":     ["Informatique", "Informatique", "Peripheriques"],
        "quantite":      [2, 2, 10],
        "prix_unitaire": [1200.0, 1200.0, 25.0],
        "remise":        [0.05, 0.05, 0.0],
        "statut":        ["Livré", "Livré", "Livré"]
    })


@pytest.fixture
def df_avec_nan():
    """DataFrame avec valeurs manquantes."""
    return pd.DataFrame({
        "date":          ["2024-01-15", None, "2024-03-10"],
        "vendeur":       ["Alice Martin", None, "Bob Dupont"],
        "region":        ["Ile-de-France", "PACA", None],
        "produit":       ["Laptop Pro", "Souris", "Ecran"],
        "categorie":     ["Informatique", "Peripheriques", "Informatique"],
        "quantite":      [2, None, 1],
        "prix_unitaire": [1200.0, 25.0, None],
        "remise":        [0.05, None, 0.10],
        "statut":        ["Livré", "Livré", "En cours"]
    })


@pytest.fixture
def df_remises_diverses():
    """DataFrame avec remises en format décimal et pourcentage."""
    return pd.DataFrame({
        "date":          ["2024-01-15"] * 4,
        "vendeur":       ["Alice"] * 4,
        "region":        ["Ile-de-France"] * 4,
        "produit":       ["Laptop"] * 4,
        "categorie":     ["Informatique"] * 4,
        "quantite":      [1, 1, 1, 1],
        "prix_unitaire": [1000.0] * 4,
        "remise":        [0.10, 10.0, 0.0, 1.5],  # Formats mixtes + hors-plage
        "statut":        ["Livré"] * 4
    })


# ============================================================
# TESTS — remove_duplicates
# ============================================================

class TestRemoveDuplicates:

    def test_supprime_les_doublons(self, df_avec_doublons):
        result = remove_duplicates(df_avec_doublons)
        assert len(result) == 2

    def test_sans_doublon_aucune_suppression(self, df_valide):
        result = remove_duplicates(df_valide)
        assert len(result) == 3

    def test_retourne_un_dataframe(self, df_valide):
        result = remove_duplicates(df_valide)
        assert isinstance(result, pd.DataFrame)


# ============================================================
# TESTS — handle_missing_values
# ============================================================

class TestHandleMissingValues:

    def test_supprime_lignes_sans_date(self, df_avec_nan):
        result = handle_missing_values(df_avec_nan.copy())
        assert result["date"].isna().sum() == 0

    def test_remplace_vendeur_nan_par_inconnu(self, df_avec_nan):
        result = handle_missing_values(df_avec_nan.copy())
        assert "Inconnu" in result["vendeur"].values

    def test_remplace_region_nan_par_inconnu(self, df_avec_nan):
        result = handle_missing_values(df_avec_nan.copy())
        assert "Inconnu" in result["region"].values

    def test_remplace_quantite_nan_par_mediane(self, df_avec_nan):
        result = handle_missing_values(df_avec_nan.copy())
        assert result["quantite"].isna().sum() == 0

    def test_remplace_prix_nan_par_mediane(self, df_avec_nan):
        result = handle_missing_values(df_avec_nan.copy())
        assert result["prix_unitaire"].isna().sum() == 0

    def test_df_sans_nan_inchange(self, df_valide):
        result = handle_missing_values(df_valide.copy())
        assert len(result) == len(df_valide)


# ============================================================
# TESTS — fix_data_types
# ============================================================

class TestFixDataTypes:

    def test_date_convertie_en_datetime(self, df_valide):
        result = fix_data_types(df_valide.copy())
        assert pd.api.types.is_datetime64_any_dtype(result["date"])

    def test_quantite_en_int(self, df_valide):
        result = fix_data_types(df_valide.copy())
        assert result["quantite"].dtype == int

    def test_prix_unitaire_en_float(self, df_valide):
        result = fix_data_types(df_valide.copy())
        assert result["prix_unitaire"].dtype == float

    def test_remise_en_float(self, df_valide):
        result = fix_data_types(df_valide.copy())
        assert result["remise"].dtype == float

    def test_vendeur_en_str(self, df_valide):
        result = fix_data_types(df_valide.copy())
        assert result["vendeur"].dtype == object

    def test_supprime_dates_invalides(self):
        df = pd.DataFrame({
            "date":          ["2024-01-15", "date-invalide", "2024-03-10"],
            "vendeur":       ["Alice", "Bob", "Claire"],
            "region":        ["IDF", "PACA", "OCC"],
            "produit":       ["A", "B", "C"],
            "categorie":     ["X", "Y", "Z"],
            "quantite":      [1, 2, 3],
            "prix_unitaire": [100.0, 200.0, 300.0],
            "remise":        [0.0, 0.0, 0.0],
            "statut":        ["Livré", "Livré", "Livré"]
        })
        result = fix_data_types(df)
        assert len(result) == 2


# ============================================================
# TESTS — fix_remise
# ============================================================

class TestFixRemise:

    def test_remise_superieure_a_1_divisee_par_100(self, df_remises_diverses):
        result = fix_remise(df_remises_diverses.copy())
        # 10.0 → 0.10
        assert result.loc[1, "remise"] == pytest.approx(0.10, abs=0.001)

    def test_remise_valide_inchangee(self, df_remises_diverses):
        result = fix_remise(df_remises_diverses.copy())
        # 0.10 reste 0.10
        assert result.loc[0, "remise"] == pytest.approx(0.10, abs=0.001)

    def test_remise_clampee_entre_0_et_1(self, df_remises_diverses):
        result = fix_remise(df_remises_diverses.copy())
        assert (result["remise"] >= 0).all()
        assert (result["remise"] <= 1).all()

    def test_remise_zero_inchangee(self, df_remises_diverses):
        result = fix_remise(df_remises_diverses.copy())
        assert result.loc[2, "remise"] == 0.0


# ============================================================
# TESTS — fix_negative_values
# ============================================================

class TestFixNegativeValues:

    def test_quantite_negative_remplacee_par_zero(self):
        df = pd.DataFrame({
            "quantite":      [-5, 3, -1],
            "prix_unitaire": [100.0, 200.0, 300.0]
        })
        result = fix_negative_values(df)
        assert (result["quantite"] >= 0).all()

    def test_prix_negatif_remplace_par_zero(self):
        df = pd.DataFrame({
            "quantite":      [1, 2, 3],
            "prix_unitaire": [-50.0, 200.0, -10.0]
        })
        result = fix_negative_values(df)
        assert (result["prix_unitaire"] >= 0).all()

    def test_valeurs_positives_inchangees(self):
        df = pd.DataFrame({
            "quantite":      [1, 5, 10],
            "prix_unitaire": [100.0, 200.0, 300.0]
        })
        result = fix_negative_values(df)
        assert list(result["quantite"]) == [1, 5, 10]


# ============================================================
# TESTS — standardize_statut
# ============================================================

class TestStandardizeStatut:

    def test_livre_normalise(self):
        df = pd.DataFrame({"statut": ["livre", "Livré", "LIVRE"]})
        result = standardize_statut(df)
        assert (result["statut"] == "Livré").all()

    def test_annule_normalise(self):
        df = pd.DataFrame({"statut": ["annule", "Annulé", "ANNULE"]})
        result = standardize_statut(df)
        assert (result["statut"] == "Annulé").all()

    def test_statut_inconnu_pour_valeur_inconnue(self):
        df = pd.DataFrame({"statut": ["statut_bizarre", "???"]})
        result = standardize_statut(df)
        assert (result["statut"] == "Inconnu").all()

    def test_en_cours_normalise(self):
        df = pd.DataFrame({"statut": ["en cours", "encours", "En cours"]})
        result = standardize_statut(df)
        assert (result["statut"] == "En cours").all()


# ============================================================
# TESTS — add_time_columns
# ============================================================

class TestAddTimeColumns:

    def test_colonne_annee_ajoutee(self, df_valide):
        df = fix_data_types(df_valide.copy())
        result = add_time_columns(df)
        assert "annee" in result.columns

    def test_colonne_mois_ajoutee(self, df_valide):
        df = fix_data_types(df_valide.copy())
        result = add_time_columns(df)
        assert "mois" in result.columns

    def test_colonne_semaine_ajoutee(self, df_valide):
        df = fix_data_types(df_valide.copy())
        result = add_time_columns(df)
        assert "semaine" in result.columns

    def test_valeurs_mois_correctes(self, df_valide):
        df = fix_data_types(df_valide.copy())
        result = add_time_columns(df)
        assert list(result["mois"]) == [1, 2, 3]

    def test_valeurs_annee_correctes(self, df_valide):
        df = fix_data_types(df_valide.copy())
        result = add_time_columns(df)
        assert (result["annee"] == 2024).all()


# ============================================================
# TEST INTÉGRATION — clean() complet
# ============================================================

class TestCleanIntegration:

    def test_clean_retourne_dataframe(self, df_valide):
        result = clean(df_valide.copy())
        assert isinstance(result, pd.DataFrame)

    def test_clean_colonnes_temporelles_presentes(self, df_valide):
        result = clean(df_valide.copy())
        for col in ["annee", "mois", "mois_nom", "semaine", "trimestre"]:
            assert col in result.columns

    def test_clean_aucune_valeur_nan(self, df_avec_nan):
        result = clean(df_avec_nan.copy())
        cols_critiques = ["vendeur", "region", "quantite", "prix_unitaire", "remise"]
        for col in cols_critiques:
            assert result[col].isna().sum() == 0

    def test_clean_remise_entre_0_et_1(self, df_valide):
        result = clean(df_valide.copy())
        assert (result["remise"] >= 0).all()
        assert (result["remise"] <= 1).all()