"""
Tests de l'interface web de démonstration (app.py)
Lancer : pytest tests/test_app.py -v
"""

import os

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402

from app import (  # noqa: E402
    ajouter_anomalies,
    diagnostic_qualite,
    executer_pipeline,
    periode_depuis_donnees,
    preparer_donnees_demo,
)
from generate_data import generer_annee  # noqa: E402

APP_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def df_propre():
    """Export ERP propre : 40 lignes valides."""
    return pd.DataFrame({
        "date":          pd.date_range("2024-01-01", periods=40).strftime("%Y-%m-%d"),
        "vendeur":       ["Alice", "Bob"] * 20,
        "region":        ["IDF", "PACA"] * 20,
        "produit":       ["Laptop", "Souris"] * 20,
        "categorie":     ["Informatique", "Peripheriques"] * 20,
        "quantite":      [2] * 40,
        "prix_unitaire": [100.0] * 40,
        "remise":        [0.10, 0.0] * 20,
        "statut":        ["Livré", "En cours"] * 20,
    })


# ============================================================
# DONNÉES D'ENTRÉE
# ============================================================

class TestGenererAnnee:

    def test_cree_12_fichiers(self, tmp_path):
        chemins = generer_annee(str(tmp_path), 2024)
        assert len(chemins) == 12
        assert all(os.path.exists(c) for c in chemins)

    def test_reproductible(self, tmp_path):
        a = generer_annee(str(tmp_path / "a"), 2024, seed=7)
        b = generer_annee(str(tmp_path / "b"), 2024, seed=7)
        assert pd.read_csv(a[0]).equals(pd.read_csv(b[0]))


class TestAjouterAnomalies:

    def test_ajoute_des_doublons(self, df_propre):
        df = ajouter_anomalies(df_propre, np.random.RandomState(0))
        assert len(df) > len(df_propre)

    def test_anomalies_detectees(self, df_propre):
        df = ajouter_anomalies(df_propre, np.random.RandomState(0))
        diag = diagnostic_qualite(df).set_index("Anomalie détectée")["Lignes concernées"]
        assert diag["Doublons exacts"] > 0
        assert diag["Remises saisies en % (ex : 10 au lieu de 0,10)"] > 0
        assert diag["Statuts mal orthographiés"] > 0

    def test_donnees_propres_sans_anomalie(self, df_propre):
        assert diagnostic_qualite(df_propre)["Lignes concernées"].sum() == 0


class TestPeriodeDepuisDonnees:

    def test_un_seul_mois(self):
        df = pd.DataFrame({"date": pd.to_datetime(["2024-03-01", "2024-03-28"])})
        assert periode_depuis_donnees(df) == "Mars 2024"

    def test_meme_annee(self):
        df = pd.DataFrame({"date": pd.to_datetime(["2024-01-03", "2024-12-20"])})
        assert periode_depuis_donnees(df) == "Janvier - Décembre 2024"

    def test_deux_annees(self):
        df = pd.DataFrame({"date": pd.to_datetime(["2023-11-03", "2024-02-20"])})
        assert periode_depuis_donnees(df) == "Novembre 2023 - Février 2024"


# ============================================================
# PIPELINE COMPLET
# ============================================================

class TestExecuterPipeline:

    def test_produit_pdf_et_graphiques(self, tmp_path):
        preparer_donnees_demo(str(tmp_path), anomalies=True)
        run = executer_pipeline(str(tmp_path), "", lambda *_: None)
        assert run["pdf"].startswith(b"%PDF")
        assert len(run["charts"]) == 5
        assert run["periode"] == "Janvier - Décembre 2024"
        assert run["nb_propre"] < run["nb_brut"]
        assert run["logs"]

    def test_colonnes_manquantes(self, tmp_path):
        pd.DataFrame({"date": ["2024-01-01"]}).to_csv(tmp_path / "x.csv", index=False)
        with pytest.raises(ValueError, match="Colonnes manquantes"):
            executer_pipeline(str(tmp_path), "", lambda *_: None)


# ============================================================
# INTERFACE
# ============================================================

class TestInterface:

    def test_accueil_sans_erreur(self):
        at = AppTest.from_file(APP_PATH, default_timeout=60).run()
        assert not at.exception
        assert any("Lancer la démo" in b.label for b in at.button)

    def test_demo_en_un_clic(self):
        at = AppTest.from_file(APP_PATH, default_timeout=120).run()
        next(b for b in at.button if "Lancer la démo" in b.label).click().run()
        assert not at.exception
        assert not at.error
        assert "Janvier - Décembre 2024" in at.success[0].value
