"""
api.py — Routes HTTP de l'interface web (Starlette, servies par st.App)

Expose le frontend statique (webapp/static), l'API de génération de rapports
(flux NDJSON alimenté par un thread de travail), les téléchargements, et les
middlewares maison : compression GZip sélective et en-têtes HTTP.
"""

import asyncio
import json
import logging
import os
import re
import threading
from typing import Callable, Optional

from starlette.datastructures import MutableHeaders, UploadFile
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException
from starlette.middleware import Middleware
from starlette.middleware.gzip import DEFAULT_EXCLUDED_CONTENT_TYPES, GZipMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import BaseRoute, Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from webapp import service

logger = logging.getLogger(__name__)

DOSSIER_STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
INDEX_HTML     = os.path.join(DOSSIER_STATIC, "index.html")
DOSSIER_ASSETS = os.path.join(DOSSIER_STATIC, "assets")

# ============================================================
# PARAMÈTRES
# ============================================================

SOURCES              = ("demo", "fichiers")
MAX_FICHIERS         = 30
TAILLE_MAX_TOTALE    = 20 * 1024 * 1024        # 20 Mo
MARGE_MULTIPART      = 1024 * 1024             # en-têtes multipart et champs texte
LONGUEUR_MAX_PERIODE = 60

MEDIA_NDJSON       = "application/x-ndjson"
GZIP_TAILLE_MIN    = 1000
# En plus des exclusions par défaut de Starlette (images, polices woff, archives…) :
# le flux NDJSON (doit partir ligne par ligne) et les binaires déjà compressés.
EXCLUSIONS_GZIP    = (MEDIA_NDJSON, "application/pdf", "application/octet-stream", "font/*")
CACHE_ASSETS       = "public, max-age=604800"  # 7 jours : polices et images
# CSS et modules JS : revalidés à chaque visite (ETag, réponse 304 légère), pour qu'un
# déploiement ne mélange jamais d'anciens et de nouveaux modules sans versionner les URL
CACHE_CODE         = "no-cache"
EXTENSIONS_CODE    = (".css", ".js")
ENTETES_SECURITE   = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy":        "strict-origin-when-cross-origin",
}
ENTETES_FLUX = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}

RE_IDENTIFIANT        = re.compile(r"^[0-9a-f]{32}$")
MESSAGE_INTROUVABLE   = "Rapport introuvable ou expiré. Générez-le à nouveau."
MESSAGE_TROP_VOLUMINEUX = "Les fichiers dépassent 20 Mo au total."
MESSAGE_TROP_DE_FICHIERS = f"{MAX_FICHIERS} fichiers maximum par rapport."
MESSAGE_ILLISIBLE       = "Le formulaire envoyé est illisible."

# Préfixes servis par nos routes (le reste appartient à Streamlit)
PREFIXES_APPLI = ("/api/", "/assets/", "/exemples/")


def _est_route_appli(chemin: str) -> bool:
    return chemin == "/" or chemin == "/assets" or chemin.startswith(PREFIXES_APPLI)


# ============================================================
# VALIDATION DU FORMULAIRE
# ============================================================

def _valider_fichiers(fichiers: list) -> Optional[str]:
    """`fichiers` : liste de couples (nom, taille) ; nom = None pour un champ qui n'est pas un fichier."""
    if not fichiers:
        return "Ajoutez au moins un fichier CSV."
    if any(nom is None for nom, _ in fichiers):
        return "Le champ « fichiers » doit contenir des fichiers CSV."
    if len(fichiers) > MAX_FICHIERS:
        return f"{MAX_FICHIERS} fichiers maximum par rapport (vous en avez envoyé {len(fichiers)})."
    for nom, taille in fichiers:
        nom_affiche = os.path.basename(nom.replace("\\", "/")) or "sans nom"
        if not nom.lower().endswith(".csv"):
            return f"« {nom_affiche} » n'est pas un fichier .csv."
        if taille == 0:
            return f"Le fichier « {nom_affiche} » est vide."
    if sum(taille for _, taille in fichiers) > TAILLE_MAX_TOTALE:
        return MESSAGE_TROP_VOLUMINEUX
    return None


def valider_formulaire(source: str, periode: str, fichiers: list) -> dict:
    """Retourne {champ: message} (vide si tout est valide)."""
    erreurs = {}
    if source not in SOURCES:
        erreurs["source"] = "Choisissez une source de données : démonstration ou vos fichiers."
    if len(periode.strip()) > LONGUEUR_MAX_PERIODE:
        erreurs["periode"] = f"La période ne doit pas dépasser {LONGUEUR_MAX_PERIODE} caractères."
    if source == "fichiers":
        message = _valider_fichiers(fichiers)
        if message:
            erreurs["fichiers"] = message
    return erreurs


def _texte(valeur) -> str:
    return valeur if isinstance(valeur, str) else ""


def _lire_anomalies(valeur: str) -> bool:
    return valeur.strip().lower() not in ("false", "0", "off", "non")


def _descriptifs_fichiers(envoyes: list) -> list:
    """(nom, taille) de chaque élément du champ « fichiers » ; ignore les sélecteurs laissés vides."""
    descriptifs = []
    for element in envoyes:
        if not isinstance(element, UploadFile):
            descriptifs.append((None, 0))
        elif element.filename or element.size:
            descriptifs.append((element.filename or "", element.size or 0))
    return descriptifs


def _reponse_erreurs(erreurs: dict) -> JSONResponse:
    return JSONResponse({"erreurs": erreurs}, status_code=422)


def _taille_max_corps() -> int:
    return TAILLE_MAX_TOTALE + MARGE_MULTIPART


def _corps_trop_volumineux(request: Request) -> bool:
    try:
        return int(request.headers.get("content-length", "0")) > _taille_max_corps()
    except ValueError:
        return False


class CorpsTropVolumineux(Exception):
    """Le corps de la requête dépasse la taille maximale (levée pendant la lecture)."""


def recevoir_avec_limite(receive: Receive, limite: int) -> Receive:
    """
    Enveloppe `receive` : lève CorpsTropVolumineux dès que plus de `limite`
    octets de corps sont arrivés. Couvre les envois sans Content-Length
    (Transfer-Encoding: chunked), qui seraient sinon lus et écrits sur
    disque en entier avant d'être refusés.
    """
    recus = 0

    async def recevoir() -> Message:
        nonlocal recus
        message = await receive()
        if message["type"] == "http.request":
            recus += len(message.get("body", b""))
            if recus > limite:
                raise CorpsTropVolumineux()
        return message

    return recevoir


def _message_formulaire_illisible(detail: str) -> str:
    """Traduit une erreur du lecteur multipart de Starlette (en anglais) en message utilisateur."""
    return MESSAGE_TROP_DE_FICHIERS if "files" in detail.lower() else MESSAGE_ILLISIBLE


# ============================================================
# FLUX NDJSON (thread de travail → queue → réponse)
# ============================================================

def ligne_ndjson(evenement: dict) -> bytes:
    """Un objet JSON compact par ligne ; jamais de NaN (JSON invalide)."""
    try:
        texte = json.dumps(evenement, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError):
        logger.exception("Événement non sérialisable en JSON")
        texte = json.dumps({"type": "erreur", "message": service.MESSAGE_ERREUR_INATTENDUE},
                           ensure_ascii=False, separators=(",", ":"))
    return (texte + "\n").encode("utf-8")


def flux_evenements(tache: Callable[[service.Emetteur], object]):
    """
    Lance `tache(emettre)` dans un thread de travail et retourne un générateur
    asynchrone des lignes NDJSON, émises au fur et à mesure. Si le client se
    déconnecte, le thread va quand même au bout (le rapport reste en cache).
    """
    boucle = asyncio.get_running_loop()
    file_attente: asyncio.Queue = asyncio.Queue()
    fin = object()

    def emettre(evenement) -> None:
        try:
            boucle.call_soon_threadsafe(file_attente.put_nowait, evenement)
        except RuntimeError:  # boucle fermée (arrêt du serveur) : plus personne n'écoute
            pass

    def travailler() -> None:
        try:
            tache(emettre)
        finally:
            emettre(fin)

    threading.Thread(target=travailler, name="pipeline-rapport", daemon=True).start()

    async def lignes():
        while True:
            evenement = await file_attente.get()
            if evenement is fin:
                return
            yield ligne_ndjson(evenement)

    return lignes()


# ============================================================
# ENDPOINTS
# ============================================================

async def page_accueil(request: Request) -> Response:
    if not os.path.isfile(INDEX_HTML):
        return HTMLResponse("<!doctype html><html lang=\"fr\"><body>Interface indisponible.</body></html>",
                            status_code=503)
    return FileResponse(INDEX_HTML, media_type="text/html", headers={"Cache-Control": "no-cache"})


async def creer_rapport(request: Request) -> Response:
    if _corps_trop_volumineux(request):
        return _reponse_erreurs({"fichiers": MESSAGE_TROP_VOLUMINEUX})
    request = Request(request.scope, recevoir_avec_limite(request.receive, _taille_max_corps()))
    try:
        formulaire = await request.form(max_files=100, max_fields=50)
    except CorpsTropVolumineux:
        return _reponse_erreurs({"fichiers": MESSAGE_TROP_VOLUMINEUX})
    except MultiPartException as e:  # application ASGI sans clé « app » dans le scope
        return _reponse_erreurs({"fichiers": _message_formulaire_illisible(e.message)})
    except HTTPException as e:  # Starlette/st.App : MultiPartException convertie en 400 text/plain
        if e.status_code != 400:
            raise
        return _reponse_erreurs({"fichiers": _message_formulaire_illisible(str(e.detail))})

    source  = _texte(formulaire.get("source")).strip()
    periode = _texte(formulaire.get("periode"))
    envoyes = formulaire.getlist("fichiers")
    erreurs = valider_formulaire(source, periode, _descriptifs_fichiers(envoyes))
    if erreurs:
        return _reponse_erreurs(erreurs)

    anomalies = _lire_anomalies(_texte(formulaire.get("anomalies")))
    fichiers = []
    if source == "fichiers":
        fichiers = [(f.filename or "", await f.read()) for f in envoyes
                    if isinstance(f, UploadFile) and (f.filename or f.size)]

    flux = flux_evenements(lambda emettre: service.generer_rapport(
        source, periode.strip(), emettre, anomalies=anomalies, fichiers=fichiers))
    return StreamingResponse(flux, media_type=MEDIA_NDJSON, headers=ENTETES_FLUX)


def _rapport_en_cache(request: Request) -> Optional[service.RapportEnCache]:
    identifiant = request.path_params["identifiant"]
    if not RE_IDENTIFIANT.match(identifiant):
        return None
    return service.CACHE_RAPPORTS.obtenir(identifiant)


def _introuvable() -> JSONResponse:
    return JSONResponse({"erreur": MESSAGE_INTROUVABLE}, status_code=404)


def _piece_jointe(nom: str) -> dict:
    return {"Content-Disposition": f'attachment; filename="{nom}"', "Cache-Control": "no-store"}


async def telecharger_pdf(request: Request) -> Response:
    entree = _rapport_en_cache(request)
    if entree is None:
        return _introuvable()
    return Response(entree.pdf, media_type="application/pdf", headers=_piece_jointe(entree.nom_pdf))


async def telecharger_csv(request: Request) -> Response:
    entree = _rapport_en_cache(request)
    if entree is None:
        return _introuvable()
    return Response(entree.csv, media_type="text/csv; charset=utf-8", headers=_piece_jointe(entree.nom_csv))


async def modele_csv(request: Request) -> Response:
    return FileResponse(service.EXEMPLE_CSV, media_type="text/csv; charset=utf-8", filename="modele_ventes.csv")


async def exemple_pdf(request: Request) -> Response:
    return FileResponse(service.EXEMPLE_PDF, media_type="application/pdf",
                        filename="rapport_exemple_2024.pdf", content_disposition_type="inline")


async def api_introuvable(request: Request) -> Response:
    return JSONResponse({"erreur": "Ressource introuvable."}, status_code=404)


# ============================================================
# MIDDLEWARES
# ============================================================

class _SansAcceptEncoding:
    """
    Retire Accept-Encoding de la requête : les couches internes ne compressent
    plus rien. Retire aussi le « Vary: Accept-Encoding » qu'elles ajoutent quand
    même, pour que la couche GZip externe soit seule à le poser (pas de doublon).
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        entetes = [(k, v) for k, v in scope["headers"] if k.lower() != b"accept-encoding"]

        async def envoyer(message: Message) -> None:
            if message["type"] == "http.response.start":
                reponse = MutableHeaders(scope=message)
                if "vary" in reponse:
                    restants = [v.strip() for v in reponse["vary"].split(",")
                                if v.strip() and v.strip().lower() != "accept-encoding"]
                    del reponse["vary"]
                    if restants:
                        reponse["Vary"] = ", ".join(restants)
            await send(message)

        await self.app({**scope, "headers": entetes}, receive, envoyer)


class CompressionSelective:
    """
    GZip (≥ 1000 octets) pour les réponses texte de NOS routes, sauf le flux
    NDJSON, qui doit partir ligne par ligne.

    st.App ajoute sous nos middlewares son propre GZip, dont la liste
    d'exclusions ignore application/x-ndjson : il compresserait le flux.
    Pour nos routes, on décide donc ici et on masque Accept-Encoding aux
    couches internes. Les routes de Streamlit (/_stcore, /static…) gardent
    leur comportement d'origine.
    """

    def __init__(self, app: ASGIApp, minimum_size: int = GZIP_TAILLE_MIN):
        self.app = app
        self.gzip = GZipMiddleware(
            _SansAcceptEncoding(app), minimum_size=minimum_size,
            exclude_content_types=DEFAULT_EXCLUDED_CONTENT_TYPES + EXCLUSIONS_GZIP)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and _est_route_appli(scope["path"]):
            await self.gzip(scope, receive, send)
        else:
            await self.app(scope, receive, send)


class EntetesStatiques:
    """En-têtes de sécurité sur / et /assets ; cache long sur les fichiers de /assets."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        chemin = scope.get("path", "") if scope["type"] == "http" else None
        if chemin is None or not (chemin == "/" or chemin == "/assets" or chemin.startswith("/assets/")):
            await self.app(scope, receive, send)
            return

        async def envoyer(message: Message) -> None:
            if message["type"] == "http.response.start":
                entetes = MutableHeaders(scope=message)
                for nom, valeur in ENTETES_SECURITE.items():
                    entetes.setdefault(nom, valeur)
                if chemin.startswith("/assets/") and message["status"] in (200, 304):
                    entetes.setdefault("Cache-Control", CACHE_CODE if chemin.endswith(EXTENSIONS_CODE) else CACHE_ASSETS)
            await send(message)

        await self.app(scope, receive, envoyer)


# ============================================================
# ASSEMBLAGE
# ============================================================

def creer_routes() -> list:
    """Routes à passer à st.App (elles passent avant les routes internes de Streamlit)."""
    routes: list[BaseRoute] = [
        Route("/", page_accueil, methods=["GET"]),
        Route("/api/rapports", creer_rapport, methods=["POST"]),
        Route("/api/rapports/{identifiant}/pdf", telecharger_pdf, methods=["GET"]),
        Route("/api/rapports/{identifiant}/csv", telecharger_csv, methods=["GET"]),
        Route("/api/modele.csv", modele_csv, methods=["GET"]),
        Route("/exemples/rapport_exemple_2024.pdf", exemple_pdf, methods=["GET"]),
        Mount("/assets", app=StaticFiles(directory=DOSSIER_ASSETS, check_dir=False), name="assets"),
        # Toute autre URL /api/... : 404 JSON plutôt que la page Streamlit de repli
        Route("/api/{chemin:path}", api_introuvable,
              methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]),
    ]
    return routes


def creer_middlewares() -> list:
    """Middlewares à passer à st.App (ils enveloppent ceux de Streamlit)."""
    return [Middleware(EntetesStatiques), Middleware(CompressionSelective)]
