"""
Tests du service métier de l'interface web (webapp/service.py)
Lancer : pytest tests/test_service.py -v
"""

import json
import os
import threading

import numpy as np
import pandas as pd
import pytest

from generate_data import generer_annee
from webapp import service
from webapp.service import (
    CacheRapports,
    ErreurDonnees,
    RapportEnCache,
    ajouter_anomalies,
    collecter_logs,
    diagnostic_qualite,
    ecrire_fichiers_envoyes,
    executer_pipeline,
    formater_nombre,
    generer_rapport,
    nom_fichier_assaini,
    nombre_fichiers,
    periode_depuis_donnees,
    preparer_donnees_demo,
    slug_periode,
    valeur_json,
    verifier_entetes,
    verifier_modalites,
)

ENTETE = ",".join(service.EXPECTED_COLUMNS)


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


def _entree(nom: str = "x") -> RapportEnCache:
    return RapportEnCache(pdf=b"%PDF", csv=b"a", nom_pdf=f"{nom}.pdf", nom_csv=f"{nom}.csv")


class Horloge:
    """Horloge manipulable pour tester l'expiration du cache."""

    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


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


class TestPreparerDonneesDemo:

    def test_sans_anomalies_donnees_identiques_a_la_generation(self, tmp_path):
        preparer_donnees_demo(str(tmp_path / "a"), anomalies=False)
        generer_annee(str(tmp_path / "b"), 2024, seed=42)
        nom = sorted(os.listdir(tmp_path / "a"))[0]
        assert pd.read_csv(tmp_path / "a" / nom).equals(pd.read_csv(tmp_path / "b" / nom))


class TestFichiersEnvoyes:

    @pytest.mark.parametrize("nom, attendu", [
        ("ventes.csv",              "00_ventes.csv"),
        ("VENTES.CSV",              "00_VENTES.csv"),
        ("../../etc/passwd.csv",    "00_passwd.csv"),
        ("..\\..\\windows\\x.csv",  "00_x.csv"),
        ("/abs/chemin/mars 24.csv", "00_mars_24.csv"),
        ("..csv",                   "00_csv.csv"),
        ("...",                     "00_fichier.csv"),
        ("",                        "00_fichier.csv"),
        ("décembre.csv",            "00_d_cembre.csv"),
    ])
    def test_nom_assaini(self, nom, attendu):
        assert nom_fichier_assaini(nom, 0) == attendu

    def test_ecriture_reste_dans_le_dossier(self, tmp_path):
        dossier = tmp_path / "entrees"
        dossier.mkdir()
        chemins = ecrire_fichiers_envoyes(str(dossier), [("../../evil.csv", b"a"), ("/tmp/b.csv", b"b")])
        assert [os.path.dirname(c) for c in chemins] == [os.path.realpath(dossier)] * 2
        assert sorted(os.listdir(dossier)) == ["00_evil.csv", "01_b.csv"]
        assert not (tmp_path / "evil.csv").exists()


# ============================================================
# QUALITÉ ET PÉRIODE
# ============================================================

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
# FORMATAGE
# ============================================================

class TestFormatage:

    @pytest.mark.parametrize("periode, attendu", [
        ("Janvier - Décembre 2024", "janvier_decembre_2024"),
        ("  Été 2024 !! ",          "ete_2024"),
        ("",                        "rapport"),
        ("€€€",                     "rapport"),
    ])
    def test_slug_periode(self, periode, attendu):
        assert slug_periode(periode) == attendu

    def test_nombre_de_fichiers(self):
        assert [nombre_fichiers(k) for k in (0, 1, 2, 1180)] == ["0 fichiers", "1 fichier", "2 fichiers",
                                                                  "1\u202f180 fichiers"]

    def test_separateur_de_milliers_espace_fine(self):
        assert formater_nombre(1180) == "1 180"
        assert formater_nombre(999) == "999"

    @pytest.mark.parametrize("valeur, attendu", [
        (np.int64(3), 3),
        (np.float64(2.345), 2.35),
        (float("nan"), None),
        (np.float64("inf"), None),
        (pd.NaT, None),
        (None, None),
        (pd.Timestamp("2024-01-03 10:00"), "2024-01-03"),
        (np.bool_(True), True),
        ("texte", "texte"),
    ])
    def test_valeur_json(self, valeur, attendu):
        resultat = valeur_json(valeur)
        assert resultat == attendu
        assert type(resultat) is type(attendu)


# ============================================================
# GARDE-FOUS SUR LES FICHIERS ENVOYÉS
# ============================================================

class TestVerifierEntetes:

    def test_fichier_valide(self):
        verifier_entetes([("ventes.csv", open(service.EXEMPLE_CSV, "rb").read())])

    def test_bom_lignes_vides_et_fins_de_ligne_windows_acceptes(self):
        verifier_entetes([("a.csv", b"\xef\xbb\xbf\r\n\n" + ENTETE.encode() + b"\r\n2024-01-01\r\n")])

    def test_en_tete_seul_sans_saut_de_ligne(self):
        verifier_entetes([("a.csv", ENTETE.encode())])

    def test_trop_de_colonnes(self):
        entete = ENTETE + "".join(f",x{i}" for i in range(service.MAX_COLONNES - 8))  # 51 colonnes
        with pytest.raises(ErreurDonnees, match=r"trop de colonnes \(51, maximum 50\)"):
            verifier_entetes([("large.csv", entete.encode() + b"\n1,2\n")])

    def test_60000_colonnes_refusees(self):
        with pytest.raises(ErreurDonnees, match="large.csv"):
            verifier_entetes([("large.csv", (b"a," * 60000)[:-1] + b"\n")])

    def test_colonnes_attendues_plus_quelques_autres_acceptees(self):
        verifier_entetes([("a.csv", (ENTETE + ",commentaire,source").encode() + b"\n")])

    def test_en_tete_trop_long_sans_saut_de_ligne(self):
        with pytest.raises(ErreurDonnees, match="trop longue"):
            verifier_entetes([("a.csv", b"x" * 1_000_000)])

    def test_colonnes_manquantes_nomme_le_fichier(self):
        bon = (ENTETE + "\n").encode()
        with pytest.raises(ErreurDonnees, match=r"Colonnes manquantes dans « b\.csv » : statut\."):
            verifier_entetes([("a.csv", bon), ("dossier/b.csv", bon.replace(b",statut", b""))])

    def test_encodage_non_utf8(self):
        with pytest.raises(ErreurDonnees, match="UTF-8"):
            verifier_entetes([("a.csv", ENTETE.replace("region", "r\xe9gion").encode("latin-1") + b"\n")])

    def test_rapide_meme_sur_un_gros_fichier(self):
        import time
        debut = time.perf_counter()
        with pytest.raises(ErreurDonnees):
            verifier_entetes([("a.csv", b"a," * 10_000_000)])
        assert time.perf_counter() - debut < 0.5

    def test_verifie_avant_le_verrou_et_pandas(self, monkeypatch):
        def interdit(*_args, **_kwargs):
            raise AssertionError("ne doit pas être appelé")
        monkeypatch.setattr(service, "ecrire_fichiers_envoyes", interdit)
        evenements = []
        generer_rapport("fichiers", "", evenements.append, fichiers=[("a.csv", b"a," * 60000)])
        assert [e["type"] for e in evenements] == ["erreur"]


class TestVerifierModalites:

    def test_sous_les_limites(self, df_propre):
        verifier_modalites(df_propre)

    @pytest.mark.parametrize("colonne, libelle", [("vendeur", "vendeurs"), ("region", "régions"),
                                                  ("categorie", "catégories")])
    def test_trop_de_valeurs_distinctes(self, df_propre, colonne, libelle):
        maximum = service.LIMITES_MODALITES[colonne][0]
        df = pd.concat([df_propre] * (maximum // len(df_propre) + 2), ignore_index=True)
        df[colonne] = [f"X{i}" for i in range(len(df))]
        with pytest.raises(ErreurDonnees, match=f"Trop de {libelle} .*colonne « {colonne} »"):
            verifier_modalites(df)

    def test_pipeline_refuse_avant_transform(self, tmp_path, df_propre, monkeypatch):
        """300 vendeurs × 300 régions : la heatmap prendrait plus d'une minute, verrou pris."""
        def interdit(*_):
            raise AssertionError("transform() ne doit pas être appelé")
        monkeypatch.setattr(service, "transform", interdit)
        df = pd.concat([df_propre] * 8, ignore_index=True).head(300)
        df["vendeur"] = [f"V{i}" for i in range(300)]
        df["region"] = [f"R{i}" for i in range(300)]
        df.to_csv(tmp_path / "x.csv", index=False)
        with pytest.raises(ErreurDonnees, match="Trop de vendeurs"):
            executer_pipeline(str(tmp_path), "", lambda *_: None, cache=CacheRapports())


# ============================================================
# JOURNAL
# ============================================================

class TestCollecteLogs:

    def test_capture_les_logs_du_pipeline_du_thread_courant(self):
        import logging
        logger = logging.getLogger("src.test_journal")
        with collecter_logs() as journal:
            logger.info("visible")
            autre = threading.Thread(target=lambda: logger.info("autre thread"))
            autre.start()
            autre.join()
        logger.info("après")
        assert len(journal) == 1
        assert journal[0].endswith("[INFO] visible")


# ============================================================
# CACHE DES RAPPORTS
# ============================================================

class TestCacheRapports:

    def test_ajout_et_lecture(self):
        cache = CacheRapports()
        cache.ajouter("a", _entree("a"))
        assert cache.obtenir("a").nom_pdf == "a.pdf"
        assert cache.obtenir("inconnu") is None

    def test_capacite_maximale(self):
        cache = CacheRapports(capacite=3)
        for cle in "abcd":
            cache.ajouter(cle, _entree(cle))
        assert len(cache) == 3
        assert cache.obtenir("a") is None
        assert cache.obtenir("d") is not None

    def test_expiration(self):
        horloge = Horloge()
        cache = CacheRapports(duree_vie=3600, horloge=horloge)
        cache.ajouter("a", _entree())
        horloge.t = 3599
        assert cache.obtenir("a") is not None
        horloge.t = 3600
        assert cache.obtenir("a") is None

    def test_valeurs_par_defaut_du_contrat(self):
        assert service.CACHE_RAPPORTS.capacite == 32
        assert service.CACHE_RAPPORTS.duree_vie == 3600

    def test_acces_concurrents(self):
        cache = CacheRapports(capacite=32)

        def remplir(prefixe):
            for i in range(200):
                cache.ajouter(f"{prefixe}{i}", _entree())
                cache.obtenir(f"{prefixe}{i // 2}")

        threads = [threading.Thread(target=remplir, args=(p,)) for p in "abcdefgh"]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(cache) == 32


# ============================================================
# PIPELINE COMPLET
# ============================================================

class TestExecuterPipeline:

    def test_rapport_complet_et_evenements(self, tmp_path):
        preparer_donnees_demo(str(tmp_path), anomalies=True)
        evenements, cache = [], CacheRapports()
        rapport = executer_pipeline(str(tmp_path), "", evenements.append, cache=cache)

        assert [(e["etape"], e["statut"]) for e in evenements] == [
            (etape, statut) for etape in service.ETAPES for statut in ("en_cours", "termine")]
        assert all("detail" in e for e in evenements if e["statut"] == "termine")
        assert rapport["periode"] == "Janvier - Décembre 2024"
        assert rapport["nb_lignes_propres"] < rapport["nb_lignes_brutes"]
        assert rapport["journal"]
        json.dumps(rapport, allow_nan=False)  # 100 % JSON natif

        entree = cache.obtenir(rapport["id"])
        assert entree.pdf.startswith(b"%PDF")
        assert len(entree.pdf) == rapport["pdf"]["taille"]
        assert entree.csv.startswith(b"\xef\xbb\xbf")
        assert entree.nom_pdf == "rapport_ventes_janvier_decembre_2024.pdf"

    def test_colonnes_manquantes(self, tmp_path):
        pd.DataFrame({"date": ["2024-01-01"]}).to_csv(tmp_path / "x.csv", index=False)
        with pytest.raises(ErreurDonnees, match="Colonnes manquantes"):
            executer_pipeline(str(tmp_path), "", lambda *_: None, cache=CacheRapports())

    def test_aucune_ligne_exploitable(self, tmp_path, df_propre):
        df_propre.assign(date="pas une date").to_csv(tmp_path / "x.csv", index=False)
        with pytest.raises(ErreurDonnees, match="Aucune ligne exploitable"):
            executer_pipeline(str(tmp_path), "", lambda *_: None, cache=CacheRapports())


    def test_details_des_etapes_libelles_du_contrat(self, tmp_path, df_propre):
        """Pluriel fixe partout (« 0 retirées », « 1 lignes »), sauf « 1 fichier »."""
        df_propre.head(1).to_csv(tmp_path / "x.csv", index=False)
        evenements = []
        executer_pipeline(str(tmp_path), "", evenements.append, cache=CacheRapports())
        details = {e["etape"]: e["detail"] for e in evenements if e["statut"] == "termine"}
        assert details["extraction"] == "1 lignes · 1 fichier"
        assert details["nettoyage"] == "1 lignes valides · 0 retirées"
        assert details["transformation"] == "8 indicateurs · 6 agrégations"
        assert details["visualisation"] == "5 graphiques"
        assert details["rapport"].startswith("PDF de 6 pages · ")

    @pytest.mark.parametrize("modification", [
        {"statut": "Annulé"},
        {"statut": "Retourné"},
        {"quantite": "abc", "prix_unitaire": "n/a"},
    ])
    def test_aucune_vente_comptabilisee(self, tmp_path, df_propre, modification):
        df_propre.assign(**modification).to_csv(tmp_path / "x.csv", index=False)
        with pytest.raises(ErreurDonnees, match="Aucune vente comptabilisée"):
            executer_pipeline(str(tmp_path), "", lambda *_: None, cache=CacheRapports())

    def test_figures_fermees_apres_une_erreur(self, tmp_path, df_propre, monkeypatch):
        import matplotlib.pyplot as plt

        def graphiques_en_echec(*_args, **_kwargs):
            plt.subplots()
            raise RuntimeError("échec au milieu des graphiques")
        monkeypatch.setattr(service, "generate_all_charts", graphiques_en_echec)
        df_propre.to_csv(tmp_path / "x.csv", index=False)
        plt.close("all")
        with pytest.raises(RuntimeError):
            executer_pipeline(str(tmp_path), "", lambda *_: None, cache=CacheRapports())
        assert plt.get_fignums() == []


class TestGenererRapport:

    def test_erreur_de_donnees_devient_un_evenement(self):
        evenements = []
        assert generer_rapport("fichiers", "", evenements.append, fichiers=[("x.csv", b"a,b\n1,2\n")],
                               cache=CacheRapports()) is None
        assert evenements[-1]["type"] == "erreur"
        assert "Colonnes manquantes" in evenements[-1]["message"]

    def test_erreur_inattendue_message_generique(self, monkeypatch):
        def plantage(*_args, **_kwargs):
            raise RuntimeError("détail technique interne")
        monkeypatch.setattr(service, "executer_pipeline", plantage)
        evenements = []
        generer_rapport("fichiers", "", evenements.append, fichiers=[("x.csv", ENTETE.encode())])
        assert evenements == [{"type": "erreur", "message": service.MESSAGE_ERREUR_INATTENDUE}]
