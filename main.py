"""
main.py — Point d'entrée unique du pipeline
Usage : python main.py
        python main.py --periode "Janvier - Juin 2024"
        python main.py --mode schedule
"""

import argparse
import logging
import sys
import os
from datetime import datetime
from src.extractor   import extract
from src.cleaner     import clean
from src.transformer import transform
from src.visualizer  import generate_all_charts
from src.reporter    import generate_report

logger = logging.getLogger(__name__)


# ============================================================
# CONFIGURATION DES LOGS
# ============================================================

def _setup_logging() -> None:
    """Configure les handlers console et fichier sur le logger racine."""
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"pipeline_{datetime.now().strftime('%Y%m%d')}.log")
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    root.addHandler(console)

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    root.addHandler(fh)


# ============================================================
# PIPELINE PRINCIPAL
# ============================================================

def run_pipeline(periode: str = None) -> str:
    """
    Exécute le pipeline complet ETL + visualisation + rapport.

    Args:
        periode : libellé de la période affiché dans le rapport
                  ex : "Janvier - Decembre 2024"
                  Si None, utilise le mois courant automatiquement.

    Returns:
        str : chemin vers le PDF généré
    """
    debut = datetime.now()
    logger.info("=" * 55)
    logger.info("  PIPELINE SALES REPORT AUTOMATION - DEMARRAGE")
    logger.info("=" * 55)

    try:
        # ---- Étape 1 : Extraction ----
        df_brut = extract()

        # ---- Étape 2 : Nettoyage ----
        df_propre = clean(df_brut)

        # ---- Étape 3 : Transformation ----
        resultats = transform(df_propre)

        # ---- Étape 4 : Visualisation ----
        chemins_charts = generate_all_charts(resultats)

        # ---- Étape 5 : Rapport PDF ----
        chemin_pdf = generate_report(
            resultats=resultats,
            chemins_charts=chemins_charts,
            periode=periode
        )

        # ---- Résumé final ----
        duree = (datetime.now() - debut).total_seconds()
        logger.info("=" * 55)
        logger.info("  PIPELINE TERMINE AVEC SUCCES")
        logger.info(f"  Duree        : {duree:.2f} secondes")
        logger.info(f"  Rapport PDF  : {chemin_pdf}")
        logger.info(f"  CA Total     : {resultats['kpis']['ca_total']:,.2f} EUR")
        logger.info(f"  Commandes    : {resultats['kpis']['nb_commandes']}")
        logger.info("=" * 55)

        return chemin_pdf

    except FileNotFoundError as e:
        logger.error(f"Fichier introuvable : {e}")
        logger.error("Verifiez que des fichiers CSV sont present dans data/raw/")
        sys.exit(1)

    except ValueError as e:
        logger.error(f"Erreur de donnees : {e}")
        sys.exit(1)

    except Exception as e:
        logger.error(f"Erreur inattendue : {e}", exc_info=True)
        sys.exit(1)


# ============================================================
# INTERFACE EN LIGNE DE COMMANDE
# ============================================================

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Sales Report Automation - Generateur de rapports commerciaux",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Exemples :
  python main.py
  python main.py --periode "Janvier - Decembre 2024"
  python main.py --mode schedule
        """
    )

    parser.add_argument(
        "--periode",
        type=str,
        default=None,
        help="Periode affichee dans le rapport (ex: 'Janvier - Juin 2024')"
    )

    parser.add_argument(
        "--mode",
        type=str,
        choices=["once", "schedule"],
        default="once",
        help=(
            "once     : execution unique (defaut)\n"
            "schedule : execution automatique le 1er de chaque mois"
        )
    )

    return parser.parse_args()


# ============================================================
# POINT D'ENTRÉE
# ============================================================

if __name__ == "__main__":
    _setup_logging()
    args = parse_arguments()

    if args.mode == "schedule":
        from src.scheduler import start_scheduler
        start_scheduler(periode=args.periode)
    else:
        run_pipeline(periode=args.periode)