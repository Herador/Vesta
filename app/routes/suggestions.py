"""Les suggestions: que cuisiner avec ce qu'on a, classé par urgence."""

from fastapi import APIRouter, Query

from app import base as bdd
from app.commun import en_sortie, stock_actif
from app.domaine import moteur
from app.routes.recettes import charger_recettes

# Pas de prefix ici: les chemins portent déjà /api, ce qui les rend
# lisibles tels quels quand on cherche une route dans le code.
routeur = APIRouter()


@routeur.get("/api/suggestions", tags=["Suggestions"], summary="Que cuisiner ce soir")
def suggestions(
    limite: int = Query(6, ge=1, le=20),
    imposes: str | None = Query(None, description="ids du stock à utiliser, séparés par des virgules"),
):
    """Ce que tu peux faire ce soir, classé par pertinence.

    Sans `imposes`, le moteur privilégie ce qui périme. Avec, il ne
    retient que les recettes qui utilisent tous les articles demandés.
    """
    ids = [int(x) for x in imposes.split(",") if x.strip()] if imposes else []

    with bdd.base() as con:
        articles = [en_sortie(l).model_dump() for l in stock_actif(con)]
        recettes = charger_recettes(con)

    trouvees = moteur.proposer(articles, recettes, ids, limite)
    return [{
        "recette": {
            "id": s.recette["id"], "titre": s.recette["titre"],
            "categorie": s.recette["categorie"], "cuisine": s.recette["cuisine"],
            "temps_min": s.recette["temps_min"],
            "description": s.recette["description"],
            "portions_base": s.recette["portions_base"],
            "favori": bool(s.recette["favori"]),
            "derniere_fois": s.recette["derniere_fois"],
        },
        "score": s.score,
        "pourquoi": s.pourquoi,
        "utilise": [{"id": a["id"], "nom": a["nom"], "affichage": a["affichage"]}
                    for a in s.utilise],
        "manquants": s.manquants,
    } for s in trouvees]
