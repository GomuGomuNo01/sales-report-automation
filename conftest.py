"""
conftest.py — Configuration pytest à la racine du projet.
Garantit que les imports `from src.xxx` et `from config` fonctionnent
quelle que soit la cwd au moment de lancer pytest.
"""

import sys
import os

# Ajoute la racine du projet au PYTHONPATH si elle n'y est pas déjà
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
