# Image de l'application web (interface + API de génération)
#   docker build -t sales-report .
#   docker run -p 8501:8501 sales-report   →  http://localhost:8501
# Hébergeurs : la plateforme injecte PORT (Cloud Run : 8080, Render : 10000).
# Guide complet : docs/DEPLOIEMENT.md
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLCONFIGDIR=/tmp/matplotlib \
    PORT=8501

WORKDIR /app

# Dépendances d'exécution uniquement (les outils de test sont dans requirements-dev.txt)
COPY requirements.txt .
RUN pip install -r requirements.txt

# Utilisateur non-root. Le code appartient à root (lecture seule pour l'appli) ;
# les dossiers que config.py crée au démarrage existent déjà, inscriptibles par
# l'utilisateur 1000 et par le groupe 0 (uid arbitraire : OpenShift, --user 12345),
# et config.py démarre aussi sur un système de fichiers en lecture seule.
RUN useradd --create-home --uid 1000 app
COPY . .
RUN mkdir -p data/raw data/processed output/rapports output/charts output/logs \
 && chown -R app:0 data output && chmod -R g=u data output
USER 1000

EXPOSE 8501
HEALTHCHECK CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ[\"PORT\"]}/_stcore/health', timeout=5)"

# exec : Streamlit devient le PID 1 et reçoit SIGTERM (arrêt propre au redéploiement)
CMD ["sh", "-c", "exec streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0"]
