"""
Tests des routes HTTP de l'interface web (webapp/api.py)
Lancer : pytest tests/test_webapp.py -v

Les routes et middlewares sont montés dans une application Starlette
simple, avec en dessous le GZip interne de Streamlit, comme le fait st.App.
"""

import asyncio
import csv
import io
import json
import os
import re
import threading

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import StreamingResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from webapp import api, service

try:  # GZip qu'ajoute st.App sous nos middlewares (module interne de Streamlit)
    from streamlit.web.server.starlette.starlette_gzip_middleware import SelectiveGZipMiddleware
    MIDDLEWARES_STREAMLIT = [Middleware(SelectiveGZipMiddleware, minimum_size=1000)]
except ImportError:  # pragma: no cover
    MIDDLEWARES_STREAMLIT = []

CLES_RAPPORT = {"id", "periode", "duree", "nb_fichiers", "nb_lignes_brutes", "nb_lignes_propres", "kpis",
                "qualite", "series", "apercu", "nb_lignes_donnees", "journal", "pdf", "csv"}
CLES_KPIS = {"ca_total", "nb_commandes", "panier_moyen", "nb_annulations", "taux_annulation",
             "remise_totale", "nb_vendeurs", "nb_produits"}
COLONNES_APERCU = ["date", "vendeur", "region", "produit", "categorie", "quantite", "prix_unitaire",
                   "remise", "statut", "ca_net", "ca_comptabilise"]
CSV_VALIDE = open(service.EXEMPLE_CSV, "rb").read()


# ============================================================
# OUTILS
# ============================================================

def construire_appli(routes_en_plus=()) -> Starlette:
    return Starlette(routes=list(routes_en_plus) + api.creer_routes(),
                     middleware=api.creer_middlewares() + MIDDLEWARES_STREAMLIT)


def lire_ndjson(reponse) -> list:
    assert reponse.text.endswith("\n")
    return [json.loads(ligne) for ligne in reponse.text.splitlines()]


def est_entier(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def est_nombre(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


@pytest.fixture(scope="module")
def client():
    return TestClient(construire_appli())


@pytest.fixture(scope="module")
def demo(client):
    """Une génération de démo (avec anomalies), partagée par plusieurs tests."""
    reponse = client.post("/api/rapports", data={"source": "demo"}, headers={"Accept-Encoding": "gzip"})
    return reponse, lire_ndjson(reponse)


def _premier_fichier_asset():
    for racine, _, fichiers in os.walk(api.DOSSIER_ASSETS):
        for nom in sorted(fichiers):
            return os.path.relpath(os.path.join(racine, nom), api.DOSSIER_ASSETS).replace(os.sep, "/")
    return None


# ============================================================
# PAGES ET FICHIERS STATIQUES
# ============================================================

class TestPagesStatiques:

    def test_index(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        assert "<html" in r.text.lower()
        assert r.headers["cache-control"] == "no-cache"
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"

    def test_asset_absent_404(self, client):
        r = client.get("/assets/inexistant-123.js")
        assert r.status_code == 404
        assert "max-age" not in r.headers.get("cache-control", "")

    def test_asset_present_cache_long(self, client):
        r = client.get("/assets/fonts/InterVariable-latin.woff2")
        assert r.status_code == 200
        assert r.headers["cache-control"] == "public, max-age=604800"
        assert r.headers["x-content-type-options"] == "nosniff"

    @pytest.mark.parametrize("chemin", ["/assets/js/main.js", "/assets/css/tokens.css"])
    def test_code_revalide_a_chaque_visite(self, client, chemin):
        r = client.get(chemin)
        assert r.status_code == 200
        assert r.headers["cache-control"] == "no-cache"
        assert r.headers.get("etag")

    def test_modele_csv(self, client):
        r = client.get("/api/modele.csv")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert r.headers["content-disposition"] == 'attachment; filename="modele_ventes.csv"'
        assert r.content == CSV_VALIDE

    def test_exemple_pdf_inline(self, client):
        r = client.get("/exemples/rapport_exemple_2024.pdf")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.headers["content-disposition"].startswith("inline")
        assert r.content.startswith(b"%PDF")

    def test_api_inconnue_404_json(self, client):
        r = client.get("/api/inexistant")
        assert r.status_code == 404
        assert "erreur" in r.json()


class TestCompression:

    def test_reponse_texte_compressee(self, client):
        r = client.get("/api/modele.csv", headers={"Accept-Encoding": "gzip"})
        assert r.headers["content-encoding"] == "gzip"
        assert r.headers["vary"] == "Accept-Encoding"  # posé une seule fois
        assert r.content == CSV_VALIDE  # httpx décompresse

    def test_petite_reponse_non_compressee(self, client):
        r = client.get("/api/rapports/" + "0" * 32 + "/pdf", headers={"Accept-Encoding": "gzip"})
        assert "content-encoding" not in r.headers

    def test_flux_ndjson_jamais_compresse(self, demo):
        reponse, _ = demo
        assert "content-encoding" not in reponse.headers

    def test_flux_emis_au_fur_et_a_mesure(self):
        """
        La tâche émet une ligne puis attend que cette ligne soit arrivée côté
        serveur ASGI avant de continuer : si un middleware tamponnait le flux,
        la ligne n'arriverait qu'à la fin et la tâche resterait bloquée.
        """
        premiere_ligne_recue = threading.Event()
        debloquee = []

        def tache(emettre):
            emettre({"type": "etape", "etape": "extraction", "statut": "en_cours"})
            debloquee.append(premiere_ligne_recue.wait(timeout=5))
            emettre({"type": "resultat", "rapport": {}})

        async def flux(request):
            return StreamingResponse(api.flux_evenements(tache), media_type=api.MEDIA_NDJSON,
                                     headers=api.ENTETES_FLUX)

        appli = construire_appli([Route("/api/test-flux", flux, methods=["POST"])])
        messages = []

        async def recevoir():
            if not messages:
                return {"type": "http.request", "body": b"", "more_body": False}
            await asyncio.sleep(3600)  # le client reste connecté

        async def envoyer(message):
            messages.append(message)
            if message["type"] == "http.response.body" and message.get("body"):
                premiere_ligne_recue.set()

        scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}, "http_version": "1.1",
                 "method": "POST", "scheme": "http", "path": "/api/test-flux", "raw_path": b"/api/test-flux",
                 "root_path": "", "query_string": b"", "client": ("127.0.0.1", 1), "server": ("test", 80),
                 "headers": [(b"host", b"test"), (b"accept-encoding", b"gzip")]}
        asyncio.run(asyncio.wait_for(appli(scope, recevoir, envoyer), timeout=10))

        assert debloquee == [True]
        corps = [m["body"] for m in messages if m["type"] == "http.response.body" and m.get("body")]
        assert corps[0] == b'{"type":"etape","etape":"extraction","statut":"en_cours"}\n'
        entetes = {k.decode().lower() for k, _ in messages[0]["headers"]}
        assert "content-encoding" not in entetes


# ============================================================
# GÉNÉRATION DE RAPPORT
# ============================================================

class TestGenerationDemo:

    def test_entetes_du_flux(self, demo):
        reponse, _ = demo
        assert reponse.status_code == 200
        assert reponse.headers["content-type"] == "application/x-ndjson"
        assert reponse.headers["cache-control"] == "no-store"
        assert reponse.headers["x-accel-buffering"] == "no"

    def test_etapes_dans_l_ordre(self, demo):
        _, lignes = demo
        etapes = [l for l in lignes if l["type"] == "etape"]
        assert [(e["etape"], e["statut"]) for e in etapes] == [
            (nom, statut) for nom in ("extraction", "nettoyage", "transformation", "visualisation", "rapport")
            for statut in ("en_cours", "termine")]
        assert all("detail" not in e for e in etapes if e["statut"] == "en_cours")
        details = {e["etape"]: e["detail"] for e in etapes if e["statut"] == "termine"}
        assert details["extraction"] == "1 180 lignes · 12 fichiers"
        assert re.fullmatch(r"[\d ]+ lignes valides · [\d ]+ retirées", details["nettoyage"])
        assert details["transformation"] == "8 indicateurs · 6 agrégations"
        assert details["visualisation"] == "5 graphiques"
        assert re.fullmatch(r"PDF de 6 pages · [\d ]+ Ko", details["rapport"])

    def test_resultat_conforme_au_contrat(self, demo):
        _, lignes = demo
        assert lignes[-1]["type"] == "resultat"
        assert sum(l["type"] == "resultat" for l in lignes) == 1
        r = lignes[-1]["rapport"]

        assert set(r) == CLES_RAPPORT
        assert re.fullmatch(r"[0-9a-f]{32}", r["id"])
        assert r["periode"] == "Janvier - Décembre 2024"
        assert isinstance(r["duree"], float) and r["duree"] == round(r["duree"], 2)
        for cle in ("nb_fichiers", "nb_lignes_brutes", "nb_lignes_propres", "nb_lignes_donnees"):
            assert est_entier(r[cle])
        assert r["nb_fichiers"] == 12
        assert r["nb_lignes_donnees"] == r["nb_lignes_propres"] < r["nb_lignes_brutes"]

        assert set(r["kpis"]) == CLES_KPIS
        assert all(est_entier(r["kpis"][k]) for k in ("nb_commandes", "nb_annulations", "nb_vendeurs", "nb_produits"))
        assert all(est_nombre(v) for v in r["kpis"].values())

        assert len(r["qualite"]) == 7
        assert r["qualite"][0] == {"anomalie": "Doublons exacts", "lignes": r["qualite"][0]["lignes"],
                                   "correction": "Supprimés"}
        assert all(est_entier(q["lignes"]) for q in r["qualite"])
        assert sum(q["lignes"] for q in r["qualite"]) > 0

        assert r["journal"] and all(isinstance(l, str) for l in r["journal"])
        assert r["pdf"] == {"url": f"/api/rapports/{r['id']}/pdf",
                            "nom": "rapport_ventes_janvier_decembre_2024.pdf", "taille": r["pdf"]["taille"]}
        assert est_entier(r["pdf"]["taille"])
        assert r["csv"] == {"url": f"/api/rapports/{r['id']}/csv",
                            "nom": "ventes_nettoyees_janvier_decembre_2024.csv"}

    def test_series(self, demo):
        s = demo[1][-1]["rapport"]["series"]
        assert set(s) == {"vendeurs", "mois", "categories", "regions", "produits", "heatmap"}

        for cle in ("vendeurs", "produits"):
            assert 0 < len(s[cle]) <= 10
            cas = [x["ca"] for x in s[cle]]
            assert cas == sorted(cas, reverse=True)
        assert [(m["annee"], m["mois"]) for m in s["mois"]] == [(2024, m) for m in range(1, 13)]
        assert s["mois"][0]["mois_nom"] == "Janvier"
        for cle in ("categories", "regions"):
            assert set(s[cle][0]) == {"nom", "ca", "part"}
            assert [x["ca"] for x in s[cle]] == sorted((x["ca"] for x in s[cle]), reverse=True)
            assert sum(x["part"] for x in s[cle]) == pytest.approx(100, abs=0.5)

        hm = s["heatmap"]
        assert len(hm["valeurs"]) == len(hm["vendeurs"])
        assert all(len(ligne) == len(hm["regions"]) for ligne in hm["valeurs"])
        totaux_lignes = [sum(ligne) for ligne in hm["valeurs"]]
        totaux_colonnes = [sum(col) for col in zip(*hm["valeurs"])]
        assert totaux_lignes == sorted(totaux_lignes, reverse=True)
        assert totaux_colonnes == sorted(totaux_colonnes, reverse=True)

    def test_apercu(self, demo):
        a = demo[1][-1]["rapport"]["apercu"]
        assert a["colonnes"] == COLONNES_APERCU
        assert len(a["lignes"]) == 100
        assert all(len(ligne) == len(COLONNES_APERCU) for ligne in a["lignes"])
        assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", ligne[0]) for ligne in a["lignes"])
        assert all(v is None or isinstance(v, (str, int, float)) for ligne in a["lignes"] for v in ligne)
        assert all(round(v, 2) == v for ligne in a["lignes"] for v in ligne if isinstance(v, float))

    def test_sans_anomalies(self, client):
        lignes = lire_ndjson(client.post("/api/rapports", data={"source": "demo", "anomalies": "false"}))
        r = lignes[-1]["rapport"]
        assert all(q["lignes"] == 0 for q in r["qualite"])
        assert r["nb_lignes_brutes"] == r["nb_lignes_propres"]

    def test_periode_personnalisee(self, client, monkeypatch):
        # Seule la période compte ici : le pipeline est remplacé par un double
        def faux_pipeline(dossier_csv, periode, on_event, cache=None):
            return {"periode": periode}
        monkeypatch.setattr(service, "executer_pipeline", faux_pipeline)
        lignes = lire_ndjson(client.post("/api/rapports", data={"source": "demo", "periode": "  T1 2024  "}))
        assert lignes == [{"type": "resultat", "rapport": {"periode": "T1 2024"}}]


class TestTelechargements:

    def test_pdf(self, client, demo):
        r_json = demo[1][-1]["rapport"]
        r = client.get(r_json["pdf"]["url"])
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.headers["content-disposition"] == f'attachment; filename="{r_json["pdf"]["nom"]}"'
        assert r.content.startswith(b"%PDF")
        assert len(r.content) == r_json["pdf"]["taille"]

    def test_csv(self, client, demo):
        r_json = demo[1][-1]["rapport"]
        r = client.get(r_json["csv"]["url"])
        assert r.status_code == 200
        assert r.headers["content-type"] == "text/csv; charset=utf-8"
        assert r.headers["content-disposition"] == f'attachment; filename="{r_json["csv"]["nom"]}"'
        assert r.content.startswith(b"\xef\xbb\xbf")
        lignes = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
        assert lignes[0] == COLONNES_APERCU
        assert len(lignes) - 1 == r_json["nb_lignes_donnees"]

    @pytest.mark.parametrize("identifiant", ["0" * 32, "inconnu", "A" * 32, "0" * 31 + "g", "0" * 33])
    @pytest.mark.parametrize("format_", ["pdf", "csv"])
    def test_identifiant_inconnu_ou_invalide(self, client, identifiant, format_):
        r = client.get(f"/api/rapports/{identifiant}/{format_}")
        assert r.status_code == 404
        assert r.json() == {"erreur": "Rapport introuvable ou expiré. Générez-le à nouveau."}


# ============================================================
# VALIDATION ET ERREURS
# ============================================================

def _fichier(nom: str, contenu: bytes = CSV_VALIDE):
    return ("fichiers", (nom, contenu, "text/csv"))


class TestValidation:

    def _erreurs(self, client, data, files=None) -> dict:
        r = client.post("/api/rapports", data=data, files=files)
        assert r.status_code == 422
        assert r.headers["content-type"] == "application/json"
        return r.json()["erreurs"]

    @pytest.mark.parametrize("data", [{}, {"source": "autre"}, {"source": ""}])
    def test_source_invalide(self, client, data):
        assert set(self._erreurs(client, data)) == {"source"}

    def test_periode_trop_longue(self, client):
        erreurs = self._erreurs(client, {"source": "demo", "periode": "x" * 61})
        assert set(erreurs) == {"periode"}

    def test_periode_60_caracteres_apres_strip_acceptee(self):
        assert api.valider_formulaire("demo", "  " + "x" * 60 + "  ", []) == {}

    def test_fichiers_manquants(self, client):
        assert set(self._erreurs(client, {"source": "fichiers"})) == {"fichiers"}

    def test_mauvaise_extension(self, client):
        erreurs = self._erreurs(client, {"source": "fichiers"}, [_fichier("ventes.txt")])
        assert "ventes.txt" in erreurs["fichiers"]

    def test_extension_insensible_a_la_casse(self):
        assert api.valider_formulaire("fichiers", "", [("VENTES.CSV", 10)]) == {}

    def test_fichier_vide(self, client):
        erreurs = self._erreurs(client, {"source": "fichiers"}, [_fichier("ok.csv"), _fichier("vide.csv", b"")])
        assert "vide.csv" in erreurs["fichiers"]

    def test_trop_de_fichiers(self, client):
        fichiers = [_fichier(f"f{i}.csv") for i in range(31)]
        erreurs = self._erreurs(client, {"source": "fichiers"}, fichiers)
        assert "30" in erreurs["fichiers"]

    def test_taille_totale(self, client, monkeypatch):
        monkeypatch.setattr(api, "TAILLE_MAX_TOTALE", 1000)
        erreurs = self._erreurs(client, {"source": "fichiers"}, [_fichier("a.csv"), _fichier("b.csv")])
        assert "20 Mo" in erreurs["fichiers"]

    def test_plus_de_100_fichiers(self, client):
        """Au-delà de max_files, Starlette lève une erreur 400 text/plain en anglais : elle doit devenir un 422."""
        fichiers = [_fichier(f"f{i}.csv", b"x") for i in range(101)]
        erreurs = self._erreurs(client, {"source": "fichiers"}, fichiers)
        assert erreurs == {"fichiers": "30 fichiers maximum par rapport."}

    @pytest.mark.parametrize("contenu, type_contenu", [
        (b"garbage", "multipart/form-data"),                                                 # sans boundary
        (b"&".join(b"f%d=1" % i for i in range(60)), "application/x-www-form-urlencoded"),  # trop de champs
        (b'--b\r\nContent-Disposition: form-data; name="periode"\r\n\r\n' + b"x" * (2 * 1024 * 1024)
         + b"\r\n--b--\r\n", "multipart/form-data; boundary=b"),                              # champ texte > 1 Mo
        (b"--b\r\nContent-Disposition: form-data\r\n\r\nx\r\n--b--\r\n",
         "multipart/form-data; boundary=b"),                                                 # partie sans nom
    ])
    def test_formulaire_illisible(self, client, contenu, type_contenu):
        r = client.post("/api/rapports", content=contenu, headers={"Content-Type": type_contenu})
        assert r.status_code == 422
        assert r.headers["content-type"] == "application/json"
        assert r.json() == {"erreurs": {"fichiers": "Le formulaire envoyé est illisible."}}

    def test_corps_sans_content_length_coupe_a_la_limite(self, monkeypatch):
        """
        Envoi « chunked » sans Content-Length : la lecture doit s'arrêter dès que
        la limite est dépassée, sans lire (ni écrire sur disque) tout le corps.
        """
        monkeypatch.setattr(api, "TAILLE_MAX_TOTALE", 1000)
        monkeypatch.setattr(api, "MARGE_MULTIPART", 1000)
        debut = (b'--b\r\nContent-Disposition: form-data; name="source"\r\n\r\nfichiers\r\n'
                 b'--b\r\nContent-Disposition: form-data; name="fichiers"; filename="a.csv"\r\n\r\n')
        morceaux = [debut] + [b"x" * 1000] * 1000  # ~1 Mo, bien au-delà des 2 000 octets permis
        lus, messages = [], []

        async def recevoir():
            if len(lus) < len(morceaux):
                lus.append(morceaux[len(lus)])
                return {"type": "http.request", "body": lus[-1], "more_body": True}
            return {"type": "http.request", "body": b"", "more_body": False}

        async def envoyer(message):
            messages.append(message)

        scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}, "http_version": "1.1",
                 "method": "POST", "scheme": "http", "path": "/api/rapports", "raw_path": b"/api/rapports",
                 "root_path": "", "query_string": b"", "client": ("127.0.0.1", 1), "server": ("test", 80),
                 "headers": [(b"host", b"test"), (b"transfer-encoding", b"chunked"),
                             (b"content-type", b"multipart/form-data; boundary=b")]}
        asyncio.run(asyncio.wait_for(construire_appli()(scope, recevoir, envoyer), timeout=10))

        assert messages[0]["status"] == 422
        corps = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        assert json.loads(corps) == {"erreurs": {"fichiers": "Les fichiers dépassent 20 Mo au total."}}
        assert len(lus) <= 4  # arrêt juste après la limite

    def test_messages_en_francais_et_courts(self, client):
        erreurs = self._erreurs(client, {"source": "fichiers", "periode": "x" * 61})
        assert set(erreurs) == {"periode", "fichiers"}
        assert all(isinstance(m, str) and 0 < len(m) <= 120 for m in erreurs.values())


class TestFichiersUtilisateur:

    def test_colonnes_invalides_ligne_erreur(self, client):
        r = client.post("/api/rapports", data={"source": "fichiers"},
                        files=[_fichier("mauvais.csv", b"colonne_a,colonne_b\n1,2\n")])
        assert r.status_code == 200
        lignes = lire_ndjson(r)
        assert lignes[-1]["type"] == "erreur"
        assert "resultat" not in {l["type"] for l in lignes}
        message = lignes[-1]["message"]
        assert "Colonnes manquantes" in message and "vendeur" in message
        assert "Traceback" not in message and "Error" not in message

    def test_details_des_etapes_conformes_au_contrat(self, client):
        """Libellés fixes du contrat : pluriel partout, sauf « 1 fichier »."""
        lignes = lire_ndjson(client.post("/api/rapports", data={"source": "fichiers"},
                                         files=[_fichier("ventes.csv")]))
        details = {l["etape"]: l["detail"] for l in lignes if l.get("statut") == "termine"}
        assert details["extraction"] == "25 lignes · 1 fichier"
        assert details["nettoyage"] == "25 lignes valides · 0 retirée"

    def test_en_tete_tres_large_refuse_sans_pandas(self, client, monkeypatch):
        """60 000 colonnes « a,a,… » : pandas y passerait des dizaines de secondes, verrou pris."""
        def extraction_interdite(*_):
            raise AssertionError("extract() ne doit pas être appelé")
        monkeypatch.setattr(service, "extract", extraction_interdite)
        lignes = lire_ndjson(client.post("/api/rapports", data={"source": "fichiers"},
                                         files=[_fichier("large.csv", (b"a," * 60000)[:-1] + b"\n")]))
        assert lignes == [{"type": "erreur", "message": lignes[-1]["message"]}]
        assert "large.csv" in lignes[-1]["message"]

    def test_traversee_de_chemin_neutralisee(self, client, monkeypatch):
        ecrits = []
        ecrire = service.ecrire_fichiers_envoyes

        def espion(dossier, fichiers):
            fichiers = list(fichiers)
            chemins = ecrire(dossier, fichiers)
            ecrits.append((dossier, [nom for nom, _ in fichiers], chemins))
            return chemins

        monkeypatch.setattr(service, "ecrire_fichiers_envoyes", espion)
        r = client.post("/api/rapports", data={"source": "fichiers"},
                        files=[_fichier("../../../ventes_janvier.csv")])
        lignes = lire_ndjson(r)
        assert lignes[-1]["type"] == "resultat", lignes[-1]

        (dossier, noms_recus, chemins), = ecrits
        assert ".." in noms_recus[0]  # le nom dangereux est bien arrivé jusqu'au service
        assert [os.path.dirname(c) for c in chemins] == [os.path.realpath(dossier)]
        assert os.path.basename(chemins[0]) == "00_ventes_janvier.csv"
        rapport = lignes[-1]["rapport"]
        assert rapport["nb_fichiers"] == 1
        assert rapport["periode"] == "Janvier 2024"


class TestApplication:

    def test_st_app_construit_avec_nos_routes(self):
        import streamlit as st
        import app
        assert isinstance(app.app, st.App)
        assert os.path.isfile(app.PAGE_DE_REPLI)

    @pytest.mark.parametrize("requete", [
        {"data": {"source": "fichiers"},
         "files": [("fichiers", (f"f{i}.csv", b"x", "text/csv")) for i in range(101)]},
        {"content": b"garbage", "headers": {"Content-Type": "multipart/form-data"}},
    ])
    def test_erreurs_multipart_en_422_via_st_app(self, requete):
        """Sous st.App, Starlette convertit les erreurs multipart en 400 text/plain : on doit répondre 422 JSON."""
        import app
        r = TestClient(app.app).post("/api/rapports", **requete)
        assert r.status_code == 422
        assert set(r.json()["erreurs"]) == {"fichiers"}

    def test_page_de_repli(self):
        from streamlit.testing.v1 import AppTest
        import app
        at = AppTest.from_file(app.PAGE_DE_REPLI, default_timeout=30).run()
        assert not at.exception
        assert at.title[0].value == "Page introuvable"
        assert any('href="/"' in m.value for m in at.markdown)
