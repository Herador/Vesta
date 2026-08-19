"""Ce que partagent tous les tests.

La base est jetable et recréée pour chaque test: aucune chance de
toucher au vrai stock, et aucun test ne dépend de l'ordre d'exécution.
"""

from datetime import date, timedelta

import pytest


@pytest.fixture(autouse=True)
def base_jetable(monkeypatch, tmp_path):
    """Redirige la base vers un fichier temporaire, avant tout import."""
    monkeypatch.setenv("VESTA_BASE", str(tmp_path / "essai.db"))
    import app.base as bdd
    bdd.initialiser()
    yield


@pytest.fixture
def client():
    """Un client HTTP branché sur l'application, base vide."""
    from fastapi.testclient import TestClient
    from app.api import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def dans():
    """Une date à N jours d'ici, au format attendu par l'API."""
    def calculer(jours: int) -> str:
        return (date.today() + timedelta(days=jours)).isoformat()
    return calculer


@pytest.fixture
def recette_simple():
    """Une recette valide et minimale, à déformer dans les tests."""
    return {
        "titre": "Plat d'essai",
        "categorie": "plat",
        "cuisine": "francaise",
        "portions_base": 2,
        "temps_min": 25,
        "description": "Une recette pour les tests.",
        "note": None,
        "ingredients": [
            {"nom": "poulet", "quantite": 300, "unite": "g", "partie": "plat"},
            {"nom": "carotte", "quantite": 2, "unite": "", "partie": "plat"},
            {"nom": "riz", "quantite": 150, "unite": "g", "partie": "accompagnement"},
        ],
        "etapes": [
            {"titre": "Couper", "texte": "Couper 2 carottes en rondelles fines.",
             "secondes": None},
            {"titre": "Cuire", "texte": "Saisir 300 g de poulet six minutes.",
             "secondes": 360},
            {"titre": "Servir", "texte": "Servir avec 150 g de riz cuit à l'eau.",
             "secondes": None},
        ],
    }
