"""Le carnet: consultation, écriture et mise à l'échelle des recettes."""

import json

from fastapi import APIRouter, HTTPException, Query

from app import base as bdd
from app.commun import aujourdhui, en_sortie, maintenant, stock_actif
from app.domaine import moteur, unites
from app.modeles import *

# Pas de prefix ici: les chemins portent déjà /api, ce qui les rend
# lisibles tels quels quand on cherche une route dans le code.
routeur = APIRouter()


def purger_essais() -> int:
    """Efface les recettes inventées que personne n'a cuisinées.

    Sans ça, chaque génération abandonnée laisserait une ligne invisible
    en base. On garde celles du jour: on peut fermer l'app et y revenir
    une heure plus tard.
    """
    with bdd.base() as con:
        return con.execute(
            """DELETE FROM recette
               WHERE essai = 1
                 AND date(cree_le) < date('now', '-1 day')
                 AND id NOT IN (SELECT recette_id FROM repas
                                WHERE recette_id IS NOT NULL)"""
        ).rowcount


def charger_recettes(con, recette_id: int | None = None) -> list[dict]:
    """Le carnet, chaque recette avec ses ingrédients et ses étapes.

    Deux requêtes seulement, puis on recolle en mémoire. Avec une
    trentaine de recettes on pourrait faire n'importe quoi, mais autant
    prendre l'habitude.
    """
    ou = "WHERE id = ?" if recette_id else "WHERE essai = 0"
    params = (recette_id,) if recette_id else ()
    recettes = {}
    for l in con.execute(f"SELECT * FROM recette {ou}", params).fetchall():
        r = dict(l)
        r["etapes"] = json.loads(r["etapes"]) if r["etapes"] else []
        r["ingredients"] = []
        recettes[r["id"]] = r

    for ing in con.execute(
        "SELECT * FROM ingredient_recette ORDER BY ordre"
    ).fetchall():
        if ing["recette_id"] in recettes:
            recettes[ing["recette_id"]]["ingredients"].append({
                "nom": ing["nom"], "cle": ing["cle"], "quantite": ing["quantite"],
                "famille": ing["famille"], "unite": ing["unite"],
                "partie": ing["partie"], "essentiel": bool(ing["essentiel"]),
            })
    return list(recettes.values())


def recette_affichee(r: dict, portions: int | None = None) -> dict:
    """Met les quantités à l'échelle du nombre de portions demandé."""
    facteur = (portions or r["portions_base"]) / r["portions_base"]
    sortie = {**r, "portions": portions or r["portions_base"]}
    sortie["ingredients"] = [{
        "nom": i["nom"], "cle": i["cle"], "essentiel": i["essentiel"],
        "partie": i.get("partie", "plat"),
        # L'unité de saisie voyage avec la quantité: l'écran d'édition en
        # a besoin pour réafficher des cuillères et non des millilitres.
        "unite": i.get("unite", ""),
        "quantite": (i["quantite"] * facteur) if i["quantite"] is not None else None,
        "famille": i["famille"],
        "affichage": unites.afficher_dans(i["quantite"] * facteur, i.get("unite", ""),
                                          i["nom"], i["famille"])
        if i["quantite"] is not None else "",
    } for i in r["ingredients"]]
    return sortie


@routeur.get("/api/recettes", tags=["Recettes"], summary="Lister le carnet")
def lister_recettes():
    with bdd.base() as con:
        recettes = charger_recettes(con)
    recettes.sort(key=lambda r: r["titre"].lower())
    return recettes


@routeur.get("/api/recettes/{recette_id}", tags=["Recettes"], summary="Lire une recette, à l'échelle voulue")
def lire_recette(recette_id: int, portions: int | None = Query(None, ge=1, le=12)):
    with bdd.base() as con:
        trouvees = charger_recettes(con, recette_id)
    if not trouvees:
        raise HTTPException(404, "Recette introuvable")
    return recette_affichee(trouvees[0], portions)


@routeur.post("/api/recettes", status_code=201, tags=["Recettes"],
          summary="Ajouter une recette à la main")
def ajouter_recette(recette: RecetteEntree):
    with bdd.base() as con:
        if con.execute("SELECT id FROM recette WHERE titre = ?", (recette.titre,)).fetchone():
            raise HTTPException(409, "Une recette porte déjà ce titre")
        cur = con.execute(
            """INSERT INTO recette (titre, categorie, cuisine, portions_base, temps_min,
                                    description, note, etapes, source, cree_le)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'moi', ?)""",
            (recette.titre, recette.categorie, recette.cuisine,
             recette.portions_base, recette.temps_min,
             recette.description, recette.note,
             json.dumps([e.model_dump() for e in recette.etapes], ensure_ascii=False),
             maintenant()),
        )
        for ordre, ing in enumerate(recette.ingredients):
            quantite, famille = unites.vers_base(ing.quantite, ing.unite)
            con.execute(
                """INSERT OR REPLACE INTO ingredient_recette
                   (recette_id, cle, nom, quantite, famille, unite, essentiel, ordre)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (cur.lastrowid, moteur.normaliser(ing.nom), ing.nom, quantite, famille,
                 ing.unite, int(ing.essentiel), ordre),
            )
        return charger_recettes(con, cur.lastrowid)[0]


@routeur.put("/api/recettes/{recette_id}", tags=["Recettes"],
         summary="Modifier une recette")
def modifier_recette(recette_id: int, recette: RecetteEntree):
    """Remplace une recette de bout en bout.

    Les ingrédients et les étapes sont réécrits en entier: c'est plus
    simple à raisonner qu'une mise à jour partielle, et l'écran d'édition
    renvoie de toute façon la recette complète.
    """
    with bdd.base() as con:
        actuelle = con.execute("SELECT id, source FROM recette WHERE id = ?",
                               (recette_id,)).fetchone()
        if actuelle is None:
            raise HTTPException(404, "Recette introuvable")
        double = con.execute("SELECT id FROM recette WHERE titre = ? AND id != ?",
                             (recette.titre, recette_id)).fetchone()
        if double:
            raise HTTPException(409, "Une autre recette porte déjà ce titre")

        con.execute(
            """UPDATE recette SET titre = ?, categorie = ?, cuisine = ?,
               portions_base = ?, temps_min = ?, description = ?, note = ?,
               etapes = ?, source = 'moi', essai = 0 WHERE id = ?""",
            (recette.titre, recette.categorie, recette.cuisine,
             recette.portions_base, recette.temps_min, recette.description,
             recette.note,
             json.dumps([e.model_dump() for e in recette.etapes], ensure_ascii=False),
             recette_id),
        )
        con.execute("DELETE FROM ingredient_recette WHERE recette_id = ?", (recette_id,))
        for ordre, ing in enumerate(recette.ingredients):
            quantite, famille = unites.vers_base(ing.quantite, ing.unite)
            con.execute(
                """INSERT OR REPLACE INTO ingredient_recette
                   (recette_id, cle, nom, quantite, famille, unite, partie, essentiel, ordre)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (recette_id, moteur.normaliser(ing.nom), ing.nom, quantite, famille,
                 ing.unite, ing.partie, int(ing.essentiel), ordre),
            )
        return charger_recettes(con, recette_id)[0]


@routeur.post("/api/recettes/{recette_id}/garder", tags=["Recettes"],
          summary="Garder une recette essayée")
def garder_recette(recette_id: int):
    """Fait entrer au carnet une recette inventée qu'on a aimée."""
    with bdd.base() as con:
        if con.execute("UPDATE recette SET essai = 0 WHERE id = ?",
                       (recette_id,)).rowcount == 0:
            raise HTTPException(404, "Recette introuvable")
    return {"garde": True}


@routeur.delete("/api/recettes/{recette_id}", status_code=204, tags=["Recettes"],
            summary="Supprimer une recette")
def supprimer_recette(recette_id: int):
    with bdd.base() as con:
        if con.execute("DELETE FROM recette WHERE id = ?", (recette_id,)).rowcount == 0:
            raise HTTPException(404, "Recette introuvable")


@routeur.post("/api/recettes/{recette_id}/favori", tags=["Recettes"], summary="Basculer le favori")
def basculer_favori(recette_id: int):
    with bdd.base() as con:
        if con.execute("UPDATE recette SET favori = 1 - favori WHERE id = ?",
                       (recette_id,)).rowcount == 0:
            raise HTTPException(404, "Recette introuvable")
        ligne = con.execute("SELECT favori FROM recette WHERE id = ?", (recette_id,)).fetchone()
    return {"favori": bool(ligne["favori"])}
