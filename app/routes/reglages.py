"""Les réglages: la façon de cuisiner et le nombre de personnes."""

from fastapi import APIRouter, HTTPException, Query

from app import base as bdd
from app.commun import aujourdhui, en_sortie, maintenant, stock_actif
from app.domaine import moteur, unites
from app.modeles import *

# Pas de prefix ici: les chemins portent déjà /api, ce qui les rend
# lisibles tels quels quand on cherche une route dans le code.
routeur = APIRouter()


@routeur.get("/api/reglages", response_model=Reglages, tags=["Réglages"],
         summary="Lire mes réglages")
def lire_reglages():
    with bdd.base() as con:
        valeurs = {l["cle"]: l["valeur"]
                   for l in con.execute("SELECT cle, valeur FROM reglage").fetchall()}
    return Reglages(contraintes=valeurs["contraintes"],
                    personnes=int(valeurs["personnes"]))


@routeur.put("/api/reglages", response_model=Reglages, tags=["Réglages"],
         summary="Modifier mes réglages")
def ecrire_reglages(reglages: Reglages):
    with bdd.base() as con:
        for cle, valeur in (("contraintes", reglages.contraintes),
                            ("personnes", str(reglages.personnes))):
            con.execute(
                "INSERT INTO reglage (cle, valeur) VALUES (?, ?) "
                "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur",
                (cle, valeur),
            )
    return reglages
