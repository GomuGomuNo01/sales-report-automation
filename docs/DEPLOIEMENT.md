# Mettre l'application en ligne

Ce guide explique comment publier l'application web pour que n'importe qui puisse l'utiliser depuis un simple lien. Les offres des hébergeurs ont été vérifiées en octobre 2026 ; elles changent souvent, les sources sont listées en fin de page.

## En bref

| Hébergeur | Coût | Carte bancaire | Premier visiteur après une période calme | Génération d'un rapport | Verdict |
|---|---|---|---|---|---|
| **Google Cloud Run** | environ 0 € par mois (quotas gratuits) | oui | quelques secondes de chargement (démarrage à froid) | environ 2 s | **Recommandé** |
| **Render** (offre gratuite) | 0 € | non (une vérification à 1 $ peut être demandée) | environ 1 minute, ou rien avec le maintien en éveil | plus lente (0,1 CPU) | Alternative sans carte |
| **Streamlit Community Cloud** | 0 € | non | page « app endormie » à cliquer après 12 h, puis environ 1 minute | rapide (environ 2 s) | **Utilisé pour la démo** |
| Hugging Face Spaces (Docker) | 9 $ par mois (PRO) depuis juillet 2026 | oui | jusqu'à quelques minutes après 48 h | correcte | Déconseillé |

**Recommandation :** Google Cloud Run si une carte bancaire n'est pas un obstacle. C'est l'expérience la plus fluide pour un recruteur : pas de page de mise en veille, quelques secondes au premier chargement, génération rapide, et un coût nul pour quelques dizaines de visites par mois. Sinon, Render gratuit avec le maintien en éveil.

**Démo actuelle :** la démo publique tourne sur Streamlit Community Cloud ([sales-report-automation-cedric.streamlit.app](https://sales-report-automation-cedric.streamlit.app)). C'est gratuit, sans carte, et ça ne consomme pas les 750 heures gratuites de Render, déjà utilisées par d'autres projets. Seul défaut : la page de mise en veille après 12 heures sans visite.

## Ce dont l'application a besoin (partout)

- Une image **Docker** : le [`Dockerfile`](../Dockerfile) du dépôt est prêt. Il lit le port dans la variable `PORT` fournie par l'hébergeur, tourne sans droits root, accepte un système de fichiers en lecture seule et s'arrête proprement à chaque redéploiement.
- **Une seule instance** : les rapports générés (PDF, CSV) sont gardés en mémoire pendant une heure. Avec plusieurs instances, un lien de téléchargement pourrait arriver sur une autre instance et renvoyer « rapport introuvable ».
- **512 Mo de mémoire au minimum** : mesuré en local, environ 130 Mio au repos, 250 Mio en usage normal, 344 Mio au pic avec 5 générations simultanées.
- **Vérification de santé** : `/_stcore/health`.

Démarrage à froid mesuré en local : environ 3 secondes, hors téléchargement de l'image (environ 210 Mo compressés).

---

## Option 1 : Google Cloud Run (recommandée)

### 1. Préparer le compte

1. Créer un compte sur [console.cloud.google.com](https://console.cloud.google.com) et activer la facturation (carte bancaire obligatoire, même pour rester dans les quotas gratuits ; l'essai gratuit offre 300 $ sur 90 jours).
2. Créer un projet, par exemple `sales-report-automation`.
3. **Créer une alerte budgétaire** (Facturation > Budgets et alertes) à 1 € ou 5 € : Cloud Run n'a pas de plafond de dépense automatique, l'alerte prévient par e-mail.

Toutes les commandes suivantes se lancent dans **Cloud Shell** (le bouton `>_` en haut de la console) : un terminal dans le navigateur où `gcloud` et `git` sont déjà installés.

```bash
gcloud config set project VOTRE_ID_DE_PROJET
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

### 2. Premier déploiement

```bash
git clone https://github.com/GomuGomuNo01/sales-report-automation.git
cd sales-report-automation

gcloud run deploy sales-report-automation \
  --source . \
  --region europe-west9 \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 1 \
  --cpu 1 \
  --memory 1Gi \
  --concurrency 20 \
  --timeout 300 \
  --cpu-boost
```

| Option | Pourquoi |
|---|---|
| `--source .` | Cloud Build construit l'image avec le `Dockerfile` du dépôt (le fichier `.gcloudignore` évite d'envoyer l'inutile) |
| `--region europe-west9` | Paris, au tarif le plus bas (Tier 1) ; `europe-west1` (Belgique) convient aussi |
| `--allow-unauthenticated` | la démo est publique, sans connexion |
| `--min-instances 0` | aucune instance ne tourne sans visiteur : coût nul, quelques secondes de démarrage au premier visiteur |
| `--max-instances 1` | une seule instance, à cause du cache des rapports en mémoire |
| `--memory 1Gi` | marge confortable (pic mesuré : 344 Mio ; `/tmp` est en mémoire sur Cloud Run) |
| `--concurrency 20` | les générations sont de toute façon traitées une à une par l'application |
| `--timeout 300` | une génération dure quelques secondes, mais l'envoi de gros fichiers peut être plus long |
| `--cpu-boost` | plus de CPU au démarrage : démarrage à froid plus court |

Le port n'a pas besoin d'être précisé : Cloud Run fournit `PORT=8080`, lu par le `Dockerfile`. À la fin, la commande affiche l'adresse publique, de la forme `https://sales-report-automation-XXXXXXXXXX.europe-west9.run.app`.

### 3. Garder le stockage des images dans le quota gratuit

Chaque déploiement stocke une nouvelle image (environ 210 Mo) dans Artifact Registry, dont seuls 0,5 Go sont gratuits. Cette règle ne garde que les 2 dernières images :

```bash
gcloud artifacts repositories set-cleanup-policies cloud-run-source-deploy \
  --location=europe-west9 \
  --policy=deploy/artifact-registry-nettoyage.json
```

### 4. Redéployer automatiquement à chaque push sur `main`

Dans la console : **Cloud Run > sales-report-automation > Configurer le déploiement continu** (ou « Connecter le dépôt ») :

1. Fournisseur : GitHub, puis installer l'application Cloud Build sur le dépôt `GomuGomuNo01/sales-report-automation`.
2. Branche : `^main$`.
3. Type de build : **Dockerfile**, chemin `/Dockerfile`.

Chaque push sur `main` reconstruit l'image et publie une nouvelle version. Les 2 500 minutes de build gratuites par mois suffisent largement.

### 5. Ce que ça coûte

Pour un portfolio (quelques dizaines de visites par mois), l'usage reste très en dessous des quotas gratuits mensuels de Cloud Run (180 000 vCPU-secondes, 360 000 Gio-secondes, 2 millions de requêtes) : **environ 0 €**. Supprimer complètement le démarrage à froid avec `--min-instances 1` coûterait environ 13 $ par mois.

---

## Option 2 : Render (gratuit, sans carte bancaire)

Le fichier [`render.yaml`](../render.yaml) décrit tout le déploiement (Docker, offre gratuite, région Francfort, vérification de santé, redéploiement à chaque push sur `main`).

1. Créer un compte sur [render.com](https://render.com) avec son compte GitHub.
2. **New > Blueprint**, choisir le dépôt `GomuGomuNo01/sales-report-automation`, puis **Apply**. Lien direct : [render.com/deploy?repo=https://github.com/GomuGomuNo01/sales-report-automation](https://render.com/deploy?repo=https://github.com/GomuGomuNo01/sales-report-automation).
3. L'adresse est `https://sales-report-automation.onrender.com` (Render ajoute un suffixe si ce nom est déjà pris).

**Limites de l'offre gratuite**

- **Mise en veille après 15 minutes sans visite**, puis environ une minute de réveil pour le visiteur suivant.
- **0,1 CPU** : une génération prend nettement plus que les 2 secondes mesurées sur un poste classique. La progression affichée étape par étape aide à patienter.
- 512 Mo de mémoire : suffisant pour l'application.
- 750 heures gratuites par mois et 5 Go de trafic sortant (un rapport PDF pèse environ 0,6 Mo).

### Maintien en éveil (facultatif)

Le workflow [`.github/workflows/garder-eveille.yml`](../.github/workflows/garder-eveille.yml) interroge la démo toutes les 10 minutes pour éviter la mise en veille. Il ne fait rien tant qu'il n'est pas configuré :

1. GitHub > dépôt > **Settings > Secrets and variables > Actions > Variables > New repository variable**.
2. Nom : `DEMO_URL`, valeur : l'adresse Render (par exemple `https://sales-report-automation.onrender.com`).

À savoir : un service allumé en continu consomme environ 744 heures sur les 750 gratuites du mois ; les minutes GitHub Actions sont gratuites pour un dépôt public ; GitHub met en pause les tâches planifiées après 60 jours sans activité sur le dépôt, et les déclenchements peuvent prendre du retard aux heures chargées.

---

## Streamlit Community Cloud (démo actuelle)

1. [share.streamlit.io](https://share.streamlit.io) > **Create app** > **Deploy a public app from GitHub**.
2. Dépôt `GomuGomuNo01/sales-report-automation`, branche `main`, fichier `app.py`, puis un sous-domaine libre (les sous-domaines sont attribués au premier qui les prend : `sales-report-automation` appartient à une autre application).
3. **Deploy** : l'installation des dépendances prend 2 à 5 minutes la première fois. Chaque push sur `main` redéploie ensuite l'application en quelques secondes.
4. **Après un push qui ajoute ou modifie une route du serveur** (fichier [`webapp/api.py`](../webapp/api.py) ou [`app.py`](../app.py)) : redémarrer l'application. [share.streamlit.io](https://share.streamlit.io) > **⋮** sur la ligne de l'application > **Reboot**, ou depuis l'application : **Manage app** > **⋮** > **Reboot app** (environ une minute d'indisponibilité). Streamlit Cloud remplace les fichiers à chaque push sans relancer le serveur : les fichiers de la page (HTML, CSS, JS) sont à jour tout de suite, mais les routes de l'API ne sont créées qu'au démarrage. Sans redémarrage, une nouvelle adresse renvoie la page Streamlit par défaut au lieu de la réponse attendue.

À savoir :
- l'application y tourne dans une iframe, sous le chemin `/~/+/`, derrière une page propre à Streamlit. Le frontend utilise donc des adresses relatives, et il envoie à la page hôte le message `GUEST_READY` (dans [`main.js`](../webapp/static/assets/js/main.js)) : sans lui, Streamlit garde l'iframe masquée et la page reste blanche. L'hébergement d'une application `st.App` à routes personnalisées n'est pas documenté par Streamlit : ce message pourrait changer avec une future version ;
- après 12 heures sans visite, le visiteur tombe sur une page « This app has gone to sleep » et doit cliquer sur un bouton pour la réveiller.

## Pourquoi pas Hugging Face ?

**Hugging Face Spaces** convient techniquement (Docker, 2 vCPU, 16 Go), mais la création d'un Space Docker exige l'abonnement PRO (9 $ par mois) depuis juillet 2026.

---

## Après la mise en ligne

1. Ouvrir l'adresse, cliquer sur **Générer un rapport de démo** : les 5 étapes doivent s'afficher une par une, puis le tableau de bord.
2. Télécharger le PDF et le CSV.
3. Vérifier que la progression arrive bien en direct (et non d'un seul bloc à la fin) :

   ```bash
   curl -N -X POST -F source=demo -F anomalies=true https://VOTRE-ADRESSE/api/rapports
   ```

4. En cas de changement d'hébergeur, remplacer l'adresse de la démo dans le README :

   ```bash
   sed -i 's#https://sales-report-automation-cedric.streamlit.app#https://VOTRE-ADRESSE#g' README.md
   ```

## Tester l'image Docker en local

```bash
docker build -t sales-report .
docker run --rm -p 8080:8080 -e PORT=8080 sales-report      # → http://localhost:8080
```

Les conditions des hébergeurs ont été reproduites en local avec succès : `PORT=7860` et `PORT=8080`, système de fichiers en lecture seule (`--read-only --tmpfs /tmp`), utilisateur arbitraire (`--user 12345`), mémoire limitée à 512 Mo.

## Sources (consultées le 7 octobre 2026)

- Cloud Run, tarifs et quotas gratuits : [cloud.google.com/run/pricing](https://cloud.google.com/run/pricing)
- Cloud Build, tarifs : [cloud.google.com/build/pricing](https://cloud.google.com/build/pricing) · Artifact Registry, tarifs : [cloud.google.com/artifact-registry/pricing](https://cloud.google.com/artifact-registry/pricing)
- Render, offre gratuite : [render.com/docs/free](https://render.com/docs/free) · Blueprint : [render.com/docs/blueprint-spec](https://render.com/docs/blueprint-spec) · Bouton de déploiement : [render.com/docs/deploy-to-render](https://render.com/docs/deploy-to-render)
- Streamlit Community Cloud, limites et mise en veille : [github.com/streamlit/docs](https://raw.githubusercontent.com/streamlit/docs/main/content/deploy/community-cloud/manage-your-app/_index.md) · application servie sous `/~/+/` : [streamlit/streamlit#7074](https://github.com/streamlit/streamlit/issues/7074)
- Hugging Face Spaces, offre payante pour Docker : [huggingface.co/docs/hub/spaces-overview](https://huggingface.co/docs/hub/spaces-overview) · [huggingface/hub-docs#2624](https://github.com/huggingface/hub-docs/pull/2624)
- Koyeb (offre gratuite fermée aux nouveaux comptes en 2026) : [koyeb.com/blog](https://www.koyeb.com/blog/koyeb-is-joining-mistral-ai-to-build-the-future-of-ai-infrastructure)
