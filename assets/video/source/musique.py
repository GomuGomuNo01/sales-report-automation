"""
musique.py — Bande-son originale de la vidéo de présentation (40 s)

Composée et synthétisée entièrement par ce script : aucun échantillon, aucune
boucle ni aucun son externe. Les instruments sont fabriqués à partir de
sinusoïdes et de bruit (synthèse additive), d'où une musique libre de droits,
diffusée sous la même licence que le projet (MIT).

Tempo 120 BPM : 1 temps = 0,5 s, 1 mesure = 2 s, 20 mesures. La structure suit
les 6 scènes de la vidéo (presentation.html) :

    0-4 s    intro          nappe et arpège, montée vers la scène suivante
    4-10 s   problème       tic-tac d'horloge, signaux d'erreur, accord tendu
    10-22 s  fonctionnement groove complet, un « ding » par étape du pipeline
    22-30 s  résultat       impact, refrain avec mélodie
    30-36 s  avantages      groove, un « ding » par carte
    36-40 s  conclusion     impact, accord final qui s'éteint

    python musique.py [sortie.wav]
"""

import sys
import wave

import numpy as np

SR      = 44_100
BPM     = 120
TEMPS   = 60 / BPM          # 0,5 s
MESURE  = 4 * TEMPS         # 2 s
DUREE   = 40.0
N       = int(SR * DUREE)

rng = np.random.default_rng(2024)

# Moments clés, partagés avec la vidéo (presentation.html)
ERREURS        = [6.0, 6.5, 7.0, 7.5]                # badges d'erreur
ETAPES         = [11.0, 12.5, 14.0, 15.5, 17.0]      # étapes du pipeline
CARTES         = [30.5, 31.5, 32.5, 33.5]            # cartes « avantages »
IMPACTS        = [22.0, 36.0]
CARILLON       = 37.0                                # adresse de la démo

ACCORDS = {
    "Am": [57, 60, 64, 69], "F": [53, 57, 60, 65], "C": [55, 60, 64, 67],
    "G": [55, 59, 62, 67], "E": [56, 59, 64, 68], "Cadd9": [55, 60, 62, 67, 74],
}
BASSES = {"Am": 33, "F": 29, "C": 36, "G": 31, "E": 28, "Cadd9": 36}

# Un accord par mesure (20 mesures)
GRILLE = ["Am", "F",                                  # intro
          "Am", "F", "E",                             # problème
          "Am", "F", "C", "G", "Am", "G",             # fonctionnement
          "Am", "F", "C", "G",                        # résultat
          "Am", "F", "G",                             # avantages
          "C", "Cadd9"]                               # conclusion

# Brillance de la nappe (fréquence de coupure, Hz) par mesure
BRILLANCE = [700, 1100, 900, 900, 1000, 1500, 1600, 1700, 1800, 1900, 2100,
             2800, 2800, 3000, 3000, 2400, 2400, 2600, 2200, 1800]


# ============================================================
# OUTILS
# ============================================================

def hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def temps(n: int) -> np.ndarray:
    return np.arange(n) / SR


def coupe_bas(f, fc):
    """Réponse d'un passe-bas du 2e ordre (Butterworth) à la fréquence f."""
    return 1 / np.sqrt(1 + (np.asarray(f) / fc) ** 4)


def filtre(x: np.ndarray, bas=None, haut=None) -> np.ndarray:
    """Filtrage dans le domaine fréquentiel : passe-haut `bas`, passe-bas `haut` (Hz)."""
    spectre = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    gain = np.ones_like(f)
    if haut:
        gain *= coupe_bas(f, haut)
    if bas:
        gain *= 1 / np.sqrt(1 + (bas / np.maximum(f, 1e-6)) ** 4)
    return np.fft.irfft(spectre * gain, len(x))


def enveloppe(n: int, attaque: float, relache: float) -> np.ndarray:
    env = np.ones(n)
    a, r = int(attaque * SR), int(relache * SR)
    if a:
        env[:a] = np.linspace(0, 1, a)
    if r:
        env[-r:] *= np.linspace(1, 0, r) ** 2
    return env


class Piste:
    """Bus stéréo, avec un départ vers la réverbération."""

    def __init__(self):
        self.sec = np.zeros((2, N))
        self.reverb = np.zeros((2, N))

    def ajouter(self, debut: float, son: np.ndarray, gain=1.0, pan=0.0, reverb=0.0):
        if son.ndim == 1:
            angle = (pan + 1) * np.pi / 4          # panoramique à puissance constante
            son = np.vstack([son * np.cos(angle), son * np.sin(angle)])
        i = int(round(debut * SR))
        if i >= N:
            return
        fin = min(N, i + son.shape[1])
        morceau = son[:, : fin - i] * gain
        self.sec[:, i:fin] += morceau
        if reverb:
            self.reverb[:, i:fin] += morceau * reverb


# ============================================================
# INSTRUMENTS (synthèse additive et bruit)
# ============================================================

def nappe(notes, duree, fc):
    """Accord tenu : 3 voix légèrement désaccordées par note, harmoniques de dent de scie filtrées."""
    n = int((duree + 0.8) * SR)
    t = temps(n)
    sortie = np.zeros((2, n))
    for note in notes:
        for voix, (cents, pan) in enumerate([(-9, -0.7), (0, 0.0), (9, 0.7)]):
            f0 = hz(note) * 2 ** (cents / 1200)
            onde = np.zeros(n)
            k_max = int(min(fc * 4, 9000) / f0)
            for k in range(1, max(k_max, 1) + 1):
                onde += (1 / k) * coupe_bas(f0 * k, fc) * np.sin(2 * np.pi * f0 * k * t + rng.uniform(0, 2 * np.pi))
            angle = (pan + 1) * np.pi / 4
            sortie += np.vstack([onde * np.cos(angle), onde * np.sin(angle)])
    env = np.ones(n)
    a, tenue = int(0.35 * SR), int(duree * SR)
    env[:a] = np.linspace(0, 1, a)
    env[tenue:] = np.exp(-temps(n - tenue) * 6)
    return sortie * env / (len(notes) * 3)


def pincee(note, duree=0.45):
    """Corde pincée : harmoniques aigus qui s'éteignent plus vite que le fondamental."""
    n = int(duree * SR)
    t = temps(n)
    f0 = hz(note)
    son = sum((1 / k) * np.exp(-t * (4 + 2.2 * k)) * np.sin(2 * np.pi * f0 * k * t) for k in range(1, 10))
    return son * enveloppe(n, 0.002, 0.05)


def basse(note, duree, courte=True):
    n = int(duree * SR)
    t = temps(n)
    f0 = hz(note)
    son = np.sin(2 * np.pi * f0 * t) + 0.5 * np.sin(2 * np.pi * 2 * f0 * t) + 0.18 * np.sin(2 * np.pi * 3 * f0 * t)
    decroissance = np.exp(-t * 5) * 0.6 + 0.4 if courte else np.exp(-t * 0.6)
    return son * decroissance * enveloppe(n, 0.004, 0.04)


def lead(note, duree):
    """Mélodie : onde proche du carré (harmoniques impairs), léger vibrato."""
    n = int(duree * SR)
    t = temps(n)
    f0 = hz(note) * (1 + 0.003 * np.sin(2 * np.pi * 5.5 * t) * np.clip(t * 4, 0, 1))
    phase = 2 * np.pi * np.cumsum(f0) / SR
    son = sum((1 / k) * coupe_bas(hz(note) * k, 2600) * np.sin(k * phase) for k in (1, 3, 5, 7, 9))
    return son * (0.7 + 0.3 * np.exp(-t * 8)) * enveloppe(n, 0.008, 0.08)


def grosse_caisse():
    n = int(0.45 * SR)
    t = temps(n)
    f = 45 + 115 * np.exp(-t * 32)
    son = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7)
    clic = filtre(rng.normal(0, 1, n), bas=1500) * np.exp(-t * 400) * 0.25
    return son + clic


def charleston(ouvert=False):
    n = int((0.25 if ouvert else 0.08) * SR)
    t = temps(n)
    return filtre(rng.normal(0, 1, n), bas=7000) * np.exp(-t * (14 if ouvert else 70))


def clap():
    n = int(0.3 * SR)
    t = temps(n)
    bruit = filtre(rng.normal(0, 1, n), bas=900, haut=5000)
    env = np.exp(-t * 20)
    for retard in (0.0, 0.011, 0.022):  # trois claquements rapprochés
        i = int(retard * SR)
        env[i:i + int(0.006 * SR)] += 0.8
    return bruit * env * 0.6 + 0.3 * np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30)


def tic(aigu=True):
    n = int(0.06 * SR)
    t = temps(n)
    f = 2400 if aigu else 1800
    return (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * f * 1.5 * t)) * np.exp(-t * 90)


def signal_erreur():
    """Deux notes descendantes un peu « buzzer », pour les badges d'erreur."""
    morceaux = []
    for f in (520, 390):
        n = int(0.09 * SR)
        t = temps(n)
        carre = sum((1 / k) * np.sin(2 * np.pi * f * k * t) for k in (1, 3, 5))
        morceaux.append(carre * enveloppe(n, 0.003, 0.03))
    return np.concatenate(morceaux)


def cloche(note, duree=1.6):
    n = int(duree * SR)
    t = temps(n)
    f0 = hz(note)
    partiels = [(1, 1.0, 3), (2.0, 0.45, 4.5), (3.01, 0.25, 6), (4.2, 0.12, 9), (5.43, 0.08, 12)]
    son = sum(a * np.exp(-t * d) * np.sin(2 * np.pi * f0 * r * t) for r, a, d in partiels)
    return son * enveloppe(n, 0.002, 0.2)


def montee(duree):
    """Montée de bruit qui s'éclaircit, avec une sinusoïde qui grimpe."""
    n = int(duree * SR)
    t = temps(n)
    progression = t / duree
    bruit = rng.normal(0, 1, n)
    sombre, clair = filtre(bruit, haut=800), filtre(bruit, bas=2500, haut=12000)
    son = (sombre * (1 - progression) + clair * progression) * progression ** 2
    f = 200 * 6 ** progression
    son += 0.25 * np.sin(2 * np.pi * np.cumsum(f) / SR) * progression ** 3
    return son * enveloppe(n, 0.05, 0.01)


def impact():
    n = int(2.2 * SR)
    t = temps(n)
    f = 32 + 60 * np.exp(-t * 6)
    boum = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.2)
    souffle = filtre(rng.normal(0, 1, n), haut=600) * np.exp(-t * 4) * 0.5
    crash = filtre(rng.normal(0, 1, n), bas=5000) * np.exp(-t * 2.5) * 0.18
    return boum + souffle + crash


def reverberation(signal: np.ndarray, duree=2.0) -> np.ndarray:
    """Convolution par une réponse impulsionnelle synthétique (bruit qui décroît), décorrélée en stéréo."""
    n = int(duree * SR)
    t = temps(n)
    sortie = np.zeros_like(signal)
    taille = 1 << int(np.ceil(np.log2(signal.shape[1] + n)))
    for canal in range(2):
        ri = filtre(rng.normal(0, 1, n), haut=5000) * np.exp(-t * 3.2)
        ri[: int(0.012 * SR)] = 0  # pré-délai
        conv = np.fft.irfft(np.fft.rfft(signal[canal], taille) * np.fft.rfft(ri, taille), taille)
        sortie[canal] = conv[: signal.shape[1]]
    return sortie / np.max(np.abs(sortie) + 1e-9) * np.max(np.abs(signal) + 1e-9) * 0.5


# ============================================================
# ARRANGEMENT
# ============================================================

def composer() -> np.ndarray:
    melodique = Piste()   # subit le « pompage » de la grosse caisse
    rythmique = Piste()
    effets = Piste()
    coups = []            # instants de grosse caisse, pour le pompage

    caisse = grosse_caisse()

    for m, nom in enumerate(GRILLE):
        debut = m * MESURE
        notes = ACCORDS[nom]
        section = ("intro" if m < 2 else "probleme" if m < 5 else "pipeline" if m < 11
                   else "resultat" if m < 15 else "avantages" if m < 18 else "fin")

        # --- Nappe ---
        duree_nappe = MESURE if m < 19 else 3.0
        gain_nappe = {"intro": 1.25, "probleme": 0.85, "fin": 1.0}.get(section, 0.75)
        melodique.ajouter(debut, nappe(notes, duree_nappe, BRILLANCE[m]), gain=0.30 * gain_nappe, reverb=0.35)

        # --- Arpège (doubles croches dans le groove, croches ailleurs) ---
        aigus = [n + 12 for n in sorted(notes)[:4]]
        motif = [0, 1, 2, 3, 2, 1, 2, 3]
        if section in ("pipeline", "resultat", "avantages"):
            for i in range(16):
                note = aigus[motif[i % 8]] + (12 if i % 8 == 3 else 0)
                melodique.ajouter(debut + i * TEMPS / 4, pincee(note, 0.3), gain=0.12 * (1.0 if i % 4 == 0 else 0.7),
                                  pan=-0.55 if i % 2 else 0.55, reverb=0.3)
        elif section in ("intro", "fin") and not (section == "intro" and m == 0):
            for i in range(8):
                melodique.ajouter(debut + i * TEMPS / 2, pincee(aigus[motif[i]], 0.5), gain=0.09,
                                  pan=-0.4 if i % 2 else 0.4, reverb=0.45)

        # --- Basse ---
        racine = BASSES[nom]
        if section == "probleme":
            melodique.ajouter(debut, basse(racine, MESURE, courte=False), gain=0.24)
        elif section in ("pipeline", "resultat", "avantages"):
            for i in range(8):
                note = racine + (12 if i % 2 else 0)
                melodique.ajouter(debut + i * TEMPS / 2, basse(note, TEMPS / 2 * 0.9), gain=0.24)
        elif section == "fin" and m == 18:
            melodique.ajouter(debut, basse(racine, 4.0, courte=False), gain=0.26)

        # --- Batterie ---
        if section == "probleme":
            for b in range(4):
                rythmique.ajouter(debut + b * TEMPS, tic(b % 2 == 0), gain=0.10, pan=0.2 if b % 2 else -0.2)
                if b in (0, 2):
                    rythmique.ajouter(debut + b * TEMPS, caisse, gain=0.55)
                    coups.append(debut + b * TEMPS)
        elif section in ("pipeline", "resultat", "avantages"):
            fin_de_montee = m == 10  # mesure 10 : roulement avant l'impact
            for b in range(4):
                instant = debut + b * TEMPS
                if not (fin_de_montee and b >= 2):
                    rythmique.ajouter(instant, caisse, gain=0.8)
                    coups.append(instant)
                rythmique.ajouter(instant + TEMPS / 2, charleston(ouvert=section != "pipeline"),
                                  gain=0.14, pan=0.3)
                for d in (0.25, 0.75):
                    rythmique.ajouter(instant + d * TEMPS, charleston(), gain=0.065, pan=-0.3)
                if b in (1, 3) and (m >= 6) and not fin_de_montee:
                    rythmique.ajouter(instant, clap(), gain=0.33, reverb=0.2)
            if fin_de_montee:
                # Roulement sur les deux derniers temps : doubles croches puis triples croches
                roulement = ([debut + 2 * TEMPS + i * TEMPS / 4 for i in range(4)]
                             + [debut + 3 * TEMPS + i * TEMPS / 8 for i in range(8)])
                for i, instant in enumerate(roulement):
                    rythmique.ajouter(instant, clap(), gain=0.08 + 0.022 * i, reverb=0.1)

    # --- Mélodie du refrain (mesures 11 à 14) ---
    phrases = [
        [76, None, 76, 74, 72, None, 69, None],
        [72, None, 72, 74, 76, None, 77, 76],
        [79, None, 76, None, 72, 74, 76, None],
        [74, None, 71, None, 74, None, 79, None],
    ]
    for p, phrase in enumerate(phrases):
        debut = (11 + p) * MESURE
        for i, note in enumerate(phrase):
            if note is None:
                continue
            longueur = 2 if i + 1 < len(phrase) and phrase[i + 1] is None else 1
            melodique.ajouter(debut + i * TEMPS / 2, lead(note, longueur * TEMPS / 2 * 0.95),
                              gain=0.16, pan=0.15, reverb=0.3)

    # --- Effets synchronisés avec l'image ---
    effets.ajouter(0.25, cloche(81, 2.0), gain=0.10, reverb=0.6)                   # apparition du logo
    effets.ajouter(2.0, montee(2.0), gain=0.10)                                    # vers « le problème »
    for instant in ERREURS:
        effets.ajouter(instant, signal_erreur(), gain=0.07, pan=0.3, reverb=0.25)
    effets.ajouter(8.0, montee(2.0), gain=0.12)                                    # vers le pipeline
    for instant, note in zip(ETAPES, [81, 84, 88, 91, 93]):
        effets.ajouter(instant, cloche(note, 1.2), gain=0.11, reverb=0.5)
    effets.ajouter(20.0, montee(2.0), gain=0.16)                                   # vers le résultat
    for instant in IMPACTS:
        effets.ajouter(instant, impact(), gain=0.55, reverb=0.3)
    for instant, note in zip(CARTES, [76, 79, 84, 88]):
        effets.ajouter(instant, cloche(note, 1.0), gain=0.10, reverb=0.5)
    effets.ajouter(35.0, montee(1.0), gain=0.10)                                   # vers la conclusion
    for i, note in enumerate([84, 88, 91, 96]):                                     # carillon final
        effets.ajouter(CARILLON + i * 0.12, cloche(note, 2.5), gain=0.08, reverb=0.7)

    # --- Pompage : la nappe, la basse et l'arpège s'effacent à chaque grosse caisse ---
    t = temps(N)
    gain = np.ones(N)
    for c in coups:
        i = int(c * SR)
        fenetre = t[i:] - c
        gain[i:] = np.minimum(gain[i:], 1 - 0.45 * np.exp(-fenetre * 9))
    melodique.sec *= gain
    melodique.reverb *= gain

    envoi = melodique.reverb + rythmique.reverb + effets.reverb
    mix = melodique.sec + rythmique.sec + effets.sec + reverberation(envoi) * 1.6

    # --- Mastering : saturation douce, normalisation, fondus ---
    mix /= np.max(np.abs(mix))
    mix = np.tanh(1.6 * mix) / np.tanh(1.6)
    mix *= 10 ** (-1 / 20) / np.max(np.abs(mix))  # crête à -1 dBFS
    mix[:, : int(0.03 * SR)] *= np.linspace(0, 1, int(0.03 * SR))
    fondu = int(1.5 * SR)
    mix[:, -fondu:] *= np.linspace(1, 0, fondu) ** 2
    return mix


def ecrire_wav(chemin: str, mix: np.ndarray) -> None:
    donnees = (np.clip(mix.T, -1, 1) * 32767).astype("<i2")
    with wave.open(chemin, "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(donnees.tobytes())


if __name__ == "__main__":
    ecrire_wav(sys.argv[1] if len(sys.argv) > 1 else "musique.wav", composer())
