"""
Scheduler : exécution automatique du pipeline
Le rapport est généré automatiquement le 1er de chaque mois à 8h00.
Usage : python main.py --mode schedule
"""

import schedule
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _job(periode: str = None):
    """
    Tâche exécutée automatiquement par le scheduler.
    Importe run_pipeline ici pour éviter les imports circulaires.
    """
    from main import run_pipeline

    logger.info("Scheduler : déclenchement automatique du pipeline")

    # Génère automatiquement le libellé du mois précédent
    if periode is None:
        mois_noms = {
            1: "Janvier", 2: "Fevrier", 3: "Mars",
            4: "Avril",   5: "Mai",     6: "Juin",
            7: "Juillet", 8: "Aout",    9: "Septembre",
            10: "Octobre", 11: "Novembre", 12: "Decembre"
        }
        maintenant = datetime.now()
        # Rapport du mois précédent
        if maintenant.month == 1:
            mois_rapport = 12
            annee_rapport = maintenant.year - 1
        else:
            mois_rapport  = maintenant.month - 1
            annee_rapport = maintenant.year

        periode = f"{mois_noms[mois_rapport]} {annee_rapport}"

    try:
        chemin = run_pipeline(periode=periode)
        logger.info(f"Scheduler : rapport genere -> {chemin}")
    except Exception as e:
        logger.error(f"Scheduler : erreur lors de l execution -> {e}")


def start_scheduler(periode: str = None):
    """
    Lance le scheduler en boucle infinie.
    Planification : le 1er de chaque mois à 08:00.
    Un rapport de test est généré immédiatement au démarrage.
    """
    logger.info("=" * 55)
    logger.info("  SCHEDULER DEMARRE")
    logger.info("  Planification : 1er du mois a 08:00")
    logger.info("  Arret : Ctrl+C")
    logger.info("=" * 55)

    # Exécution immédiate au démarrage pour valider
    logger.info("Execution initiale au demarrage...")
    _job(periode=periode)

    # Planification mensuelle — le 1er à 08:00
    schedule.every().month.at("08:00").do(_job)

    # Pour les tests : décommenter la ligne ci-dessous
    # pour une exécution toutes les minutes
    # schedule.every(1).minutes.do(_job)

    logger.info("Scheduler en attente... (Ctrl+C pour arreter)")

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)   # Vérifie toutes les 60 secondes
    except KeyboardInterrupt:
        logger.info("Scheduler arrête par l utilisateur.")