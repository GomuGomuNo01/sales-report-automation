# Image de l'interface web de démonstration
#   docker build -t sales-report .
#   docker run -p 8501:8501 sales-report   →  http://localhost:8501
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8501

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Utilisateur non-root ; config.py crée data/ et output/ au démarrage
RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen(f'http://localhost:{__import__(\"os\").environ[\"PORT\"]}/_stcore/health')"

CMD streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0
