"""L'assemblage: application, routeurs, documentation, front.

Ce module ne contient aucune logique. Il déclare l'application, monte
les routeurs dans l'ordre, et sert la PWA. Tout le reste vit dans
`app/routes/` et `app/domaine/`.

Lancement:
    uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
"""

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import base as bdd
from app.routes import (aliments, assistant, recettes, reglages, repas,
                        stock, suggestions)

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_WEB = RACINE / "web"

# L'ordre de cette liste est celui des sections dans /docs. Il suit le
# parcours réel: on remplit le frigo, on cherche quoi faire, on cuisine,
# et le reste vient après.
SECTIONS = [
    {"name": "Stock", "description":
     "Ce qu'il y a dans le frigo, le congélateur et le placard. "
     "Un article sans quantité (les épices, l'huile) n'est jamais "
     "décompté automatiquement."},
    {"name": "Suggestions", "description":
     "Ce que tu peux cuisiner ce soir avec ce que tu as, classé par "
     "urgence. Calcul local, sans appel réseau."},
    {"name": "Repas", "description":
     "Le cycle de cuisine: démarrer, puis valider le compte rendu. "
     "Le stock n'est décompté qu'à la validation."},
    {"name": "Recettes", "description":
     "Le carnet: consultation, écriture, modification, suppression."},
    {"name": "Apports", "description":
     "Les valeurs nutritionnelles, calculées depuis la table CIQUAL. "
     "Jamais générées par un modèle."},
    {"name": "Aliments CIQUAL", "description":
     "Le rattachement de tes aliments aux fiches de l'ANSES. À faire "
     "une fois par aliment, ensuite c'est acquis."},
    {"name": "Assistant", "description":
     "Génération de recettes et commentaires. Facultatif: sans clé "
     "configurée, ces routes répondent 503 et le reste fonctionne."},
    {"name": "Réglages", "description":
     "Ta façon de cuisiner et le nombre de personnes."},
    {"name": "Service", "description": "État de l'application."},
]

DESCRIPTION = """
Gestion du garde-manger, des recettes et des repas.

**Pour démarrer**: `POST /api/stock` pour remplir le frigo, puis
`GET /api/suggestions` pour voir quoi cuisiner.

**Pour cuisiner**: `POST /api/repas` démarre, `POST /api/repas/{id}/terminer`
valide le compte rendu et décompte le stock.
"""


@asynccontextmanager
async def cycle_de_vie(app: FastAPI):
    bdd.initialiser()
    recettes.purger_essais()
    yield


app = FastAPI(title="Vesta", version="0.4",
              description=DESCRIPTION, openapi_tags=SECTIONS,
              lifespan=cycle_de_vie)


@app.exception_handler(sqlite3.IntegrityError)
def contrainte_violee(requete: Request, erreur: sqlite3.IntegrityError):
    """Une contrainte de la base signale une requête incohérente, pas une
    panne: mieux vaut un 409 explicite qu'une trace de 60 lignes."""
    return JSONResponse(status_code=409, content={
        "detail": "Les données envoyées ne sont pas cohérentes avec la base: "
                  f"{erreur}"})


@app.get("/api/sante", tags=["Service"], summary="Vérifier que le service répond")
def sante():
    from app.commun import aujourdhui
    return {"etat": "ok", "date": aujourdhui().isoformat()}


# L'ordre de montage compte: aliments avant assistant, car ce dernier
# réutilise ses fonctions, et le front en dernier pour que /api/* soit
# toujours résolu avant le catch-all des fichiers statiques.
for module in (stock, suggestions, repas, recettes, aliments, assistant, reglages):
    app.include_router(module.routeur)

if DOSSIER_WEB.is_dir():
    app.mount("/", StaticFiles(directory=DOSSIER_WEB, html=True), name="web")
