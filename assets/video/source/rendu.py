"""
rendu.py — Fabrique la vidéo de présentation et sa musique

1. Compose la bande-son (musique.py) ;
2. ouvre presentation.html dans Chromium (Playwright) et capture les 1 200
   images (40 s à 30 images par seconde), en positionnant toutes les
   animations à l'instant voulu : aucune image sautée, rendu reproductible ;
3. assemble l'image et le son avec ffmpeg.

Produit, dans assets/video/ :
    SalesReport_presentation.mp4   vidéo 1920 × 1080, H.264 + AAC
    musique.mp3                    bande-son seule
    presentation-poster.jpg        image d'aperçu 1280 × 720 avec un bouton lecture
                                   (README et lecteur de la page GitHub Pages)

Prérequis (en plus de requirements.txt) :
    pip install playwright imageio-ffmpeg
    playwright install chromium

    python assets/video/source/rendu.py               # vidéo complète
    python assets/video/source/rendu.py --images 4 12 25 37.5   # quelques images fixes, pour vérifier
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

import musique

ICI       = Path(__file__).resolve().parent
SORTIE    = ICI.parent
PAGE      = (ICI / "presentation.html").as_uri() + "?rendu"
LARGEUR, HAUTEUR = 1920, 1080
IPS       = 30
DUREE     = musique.DUREE
VIDEO     = "SalesReport_presentation.mp4"
AFFICHE   = "presentation-poster.jpg"
INSTANT_AFFICHE = 3.4  # écran-titre complet


def trouver_ffmpeg() -> str:
    chemin = shutil.which("ffmpeg")
    if chemin:
        return chemin
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("ffmpeg introuvable : installez-le, ou « pip install imageio-ffmpeg ».")


def ouvrir(p):
    navigateur = p.chromium.launch()
    page = navigateur.new_page(viewport={"width": LARGEUR, "height": HAUTEUR}, device_scale_factor=1)
    page.goto(PAGE)
    page.evaluate("window.pret")
    return navigateur, page


def images_fixes(instants: list) -> None:
    """Quelques captures (dans le dossier courant), pour vérifier la mise en page sans tout rendre."""
    with sync_playwright() as p:
        navigateur, page = ouvrir(p)
        for t in instants:
            page.evaluate(f"window.allerA({t})")
            chemin = Path.cwd() / f"image_{t:05.2f}s.png"
            page.screenshot(path=str(chemin))
            print(chemin)
        navigateur.close()


def affiche(page, dossier: Path) -> None:
    """Image d'aperçu : l'écran-titre avec un bouton lecture, en 1280 × 720."""
    page.evaluate(f"window.allerA({INSTANT_AFFICHE})")
    page.evaluate("document.body.classList.add('affiche')")
    capture = dossier / "affiche.png"
    page.screenshot(path=str(capture))
    page.evaluate("document.body.classList.remove('affiche')")
    subprocess.run([trouver_ffmpeg(), "-y", "-loglevel", "error", "-i", str(capture),
                    "-vf", "scale=1280:720:flags=lanczos", "-q:v", "3", str(SORTIE / AFFICHE)], check=True)


def video() -> None:
    ffmpeg = trouver_ffmpeg()
    with tempfile.TemporaryDirectory() as dossier:
        wav = Path(dossier) / "musique.wav"
        print("Composition de la musique…")
        musique.ecrire_wav(str(wav), musique.composer())

        encodeur = subprocess.Popen([
            ffmpeg, "-y", "-loglevel", "error",
            "-f", "image2pipe", "-framerate", str(IPS), "-c:v", "png", "-i", "-",
            "-i", str(wav),
            "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
            "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-tune", "animation",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
            str(SORTIE / VIDEO),
        ], stdin=subprocess.PIPE)

        total = int(DUREE * IPS)
        with sync_playwright() as p:
            navigateur, page = ouvrir(p)
            for i in range(total):
                page.evaluate(f"window.allerA({i / IPS})")
                encodeur.stdin.write(page.screenshot(type="png"))
                if i % IPS == 0:
                    print(f"\rImages : {i}/{total}", end="", flush=True)
            affiche(page, Path(dossier))
            navigateur.close()
        encodeur.stdin.close()
        if encodeur.wait() != 0:
            sys.exit("Échec de l'encodage vidéo.")
        print(f"\rImages : {total}/{total}")

        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(wav),
                        "-c:a", "libmp3lame", "-b:a", "192k", str(SORTIE / "musique.mp3")], check=True)
    print(f"Terminé : {SORTIE / VIDEO}, {SORTIE / 'musique.mp3'}, {SORTIE / AFFICHE}")


if __name__ == "__main__":
    analyse = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    analyse.add_argument("--images", nargs="+", type=float, help="instants (s) à capturer en PNG au lieu de la vidéo")
    args = analyse.parse_args()
    images_fixes(args.images) if args.images else video()
