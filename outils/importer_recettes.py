"""Import du carnet dans la base.

    python extraire_carnet.py     puis     python -m outils.importer_recettes

Idempotent: relancer ne crée pas de doublons, les recettes sont
reconnues par leur titre et mises à jour. Tes propres recettes, ajoutées
depuis l'app avec la source 'moi', ne sont jamais touchées.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from app import base as bdd
from app.domaine import unites
from app.domaine.moteur import normaliser

# Unités de condiment: on garde l'ingrédient dans la recette, mais son
# absence ne doit pas disqualifier le plat. Personne ne renonce à un
# curry parce qu'il manque une cuillère de vinaigre.
UNITES_ACCESSOIRES = {"càs", "càc", "cas", "cac", "pincée", "pincee"}


def est_essentiel(ingredient: dict) -> bool:
    """Le format le déclare explicitement. À défaut, une unité de
    condiment signale un ingrédient dont l'absence n'empêche pas le plat."""
    if "essentiel" in ingredient:
        return bool(ingredient["essentiel"])
    if ingredient.get("partie") == "garniture":
        return False
    return ingredient.get("unite", "") not in UNITES_ACCESSOIRES


def duree_estimee(etapes: list[dict]) -> int | None:
    """Somme des minuteurs, plus une marge pour le travail à la main.

    Le carnet ne stocke pas de durée totale, mais chaque étape chronométrée
    en porte une. La marge de 4 minutes par étape non chronométrée
    correspond à la découpe et à la mise en place.
    """
    total = sum(e["secondes"] or 0 for e in etapes)
    manuelles = sum(1 for e in etapes if not e["secondes"])
    if not total and not manuelles:
        return None
    return max(5, round((total + manuelles * 240) / 60))


def charger(chemin: Path) -> list[dict]:
    """Accepte un fichier ou un dossier entier de fichiers JSON."""
    if chemin.is_dir():
        recettes = []
        for fichier in sorted(chemin.glob("*.json")):
            recettes += json.loads(fichier.read_text(encoding="utf-8"))
        return recettes
    return json.loads(chemin.read_text(encoding="utf-8"))


def importer(chemin: Path) -> None:
    recettes = charger(chemin)
    bdd.initialiser()
    ajoutees = majs = ignorees = 0
    sans_quantite: list[str] = []

    with bdd.base() as con:
        for r in recettes:
            existante = con.execute(
                "SELECT id, source FROM recette WHERE titre = ?", (r["titre"],)
            ).fetchone()

            if existante and existante["source"] == "moi":
                ignorees += 1
                continue  # on ne piétine pas une recette écrite à la main

            champs = (
                r.get("categorie"),
                r.get("cuisine"),
                r.get("portions_base", 2),
                r.get("temps_min") or duree_estimee(r.get("etapes", [])),
                r.get("description"),
                r.get("note"),
                json.dumps(r.get("etapes", []), ensure_ascii=False),
            )

            if existante:
                recette_id = existante["id"]
                con.execute(
                    """UPDATE recette SET categorie = ?, cuisine = ?, portions_base = ?,
                       temps_min = ?, description = ?, note = ?, etapes = ? WHERE id = ?""",
                    (*champs, recette_id),
                )
                con.execute("DELETE FROM ingredient_recette WHERE recette_id = ?", (recette_id,))
                majs += 1
            else:
                cur = con.execute(
                    """INSERT INTO recette
                       (titre, categorie, cuisine, portions_base, temps_min,
                        description, note, etapes, source, cree_le)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'carnet', ?)""",
                    (r["titre"], *champs, datetime.now().isoformat(timespec="seconds")),
                )
                recette_id = cur.lastrowid
                ajoutees += 1

            for ordre, ing in enumerate(r["ingredients"]):
                quantite, famille = unites.vers_base(ing.get("quantite"), ing.get("unite", ""))
                if quantite is None and ing.get("quantite"):
                    sans_quantite.append(f"{r['titre']}: {ing['nom']} ({ing.get('unite')})")
                con.execute(
                    """INSERT OR REPLACE INTO ingredient_recette
                       (recette_id, cle, nom, quantite, famille, unite, partie,
                        essentiel, ordre)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (recette_id, normaliser(ing["nom"]), ing["nom"], quantite, famille,
                     ing.get("unite", ""), ing.get("partie", "plat"),
                     int(est_essentiel(ing)), ordre),
                )

    print(f"{ajoutees} recettes ajoutées, {majs} mises à jour, {ignorees} conservées telles quelles.")
    if sans_quantite:
        print(f"{len(sans_quantite)} ingrédients gardés sans quantité décomptable "
              f"(unité trop vague), par exemple: {sans_quantite[0]}")


if __name__ == "__main__":
    fichier = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "donnees" / "recettes"
    if not fichier.exists():
        raise SystemExit(f"{fichier} introuvable.")
    importer(fichier)
