"""Import de la table CIQUAL de l'ANSES.

Télécharge la table sur https://ciqual.anses.fr, rubrique
téléchargement, puis:

    python -m outils.importer_ciqual Table_Ciqual.xlsx
    python -m outils.importer_ciqual Table_Ciqual.csv

Si le fichier est au vieux format .xls, ouvre-le et enregistre-le en
.xlsx ou en CSV UTF-8: openpyxl ne lit pas le format d'avant 2007.

L'import est à faire une seule fois. Les 3500 aliments occupent moins
d'un mégaoctet et fonctionnent ensuite hors ligne.
"""

import csv
import sys
from pathlib import Path

from app import base as bdd
from app.domaine import nutrition

# Un aliment sans énergie ni protéines est une fiche vide, inutile ici.
INDISPENSABLES = ("kcal", "proteines")

# Groupes qu'on garde en base mais qu'on relègue en fin de recherche.
# Rien n'est supprimé: si tu cherches un jour une glace ou une eau
# minérale, la fiche est là. Elle passe simplement après le reste.
GROUPES_SECONDAIRES = {
    "glaces et sorbets",
    "aliments infantiles",
    "eaux et autres boissons",
    "entrées et plats composés",
}


def lire_lignes(chemin: Path):
    """Renvoie (entetes, lignes) quel que soit le format du fichier."""
    if chemin.suffix.lower() == ".csv":
        with chemin.open(encoding="utf-8-sig", newline="") as f:
            echantillon = f.read(4096)
            f.seek(0)
            try:
                dialecte = csv.Sniffer().sniff(echantillon, delimiters=";,\t")
            except csv.Error:
                dialecte = csv.excel
                dialecte.delimiter = ";"
            lignes = list(csv.reader(f, dialecte))
        return lignes[0], lignes[1:]

    if chemin.suffix.lower() in (".xlsx", ".xlsm"):
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise SystemExit("Il manque openpyxl: pip install openpyxl")
        feuille = load_workbook(chemin, read_only=True, data_only=True).active
        lignes = [[c for c in ligne] for ligne in feuille.values]
        return lignes[0], lignes[1:]

    raise SystemExit(
        f"Format non géré: {chemin.suffix}. Enregistre le fichier en .xlsx ou en CSV UTF-8."
    )


def importer(chemin: Path) -> None:
    entetes, lignes = lire_lignes(chemin)
    colonnes = nutrition.associer_colonnes(entetes)

    manquantes = [c for c in ("code", "nom", "kcal") if c not in colonnes]
    if manquantes:
        raise SystemExit(
            f"Colonnes introuvables: {', '.join(manquantes)}.\n"
            f"Entêtes lues: {[str(e)[:40] for e in entetes[:12]]}"
        )
    print("Colonnes reconnues:", ", ".join(sorted(colonnes)))

    bdd.initialiser()
    gardees = vides = 0
    secondaires = [0]

    def cellule(ligne, champ):
        i = colonnes.get(champ)
        return ligne[i] if i is not None and i < len(ligne) else None

    with bdd.base() as con:
        con.execute("DELETE FROM ciqual")
        for ligne in lignes:
            code = cellule(ligne, "code")
            nom = cellule(ligne, "nom")
            if not code or not nom:
                continue

            valeurs = {n: nutrition.nettoyer(cellule(ligne, n))
                       for n in nutrition.NUTRIMENTS}
            if all(valeurs[n] is None for n in INDISPENSABLES):
                vides += 1
                continue

            groupe = cellule(ligne, "groupe")
            generique = int(nutrition.est_generique(str(nom)))
            pertinent = int(str(groupe or "").strip().lower() not in GROUPES_SECONDAIRES)
            secondaires[0] += 1 - pertinent

            con.execute(
                """INSERT OR REPLACE INTO ciqual
                   (code, nom, cle, groupe, sousgroupe, pertinent, generique, kcal,
                    proteines, glucides, sucres, lipides, satures, fibres, sel)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(code).strip(), str(nom).strip(),
                 nutrition.cle_ciqual(nutrition.sans_marqueurs(str(nom))),
                 groupe, cellule(ligne, "sousgroupe"), pertinent, generique,
                 *[valeurs[n] for n in nutrition.NUTRIMENTS]),
            )
            gardees += 1

    print(f"{gardees} aliments importés, dont {secondaires[0]} rangés en second plan "
          f"(glaces, boissons, plats préemballés)."
          + (f" {vides} fiches vides ignorées." if vides else ""))
    associer_automatiquement()


def associer_automatiquement() -> int:
    """Rapproche chaque aliment du stock et du carnet d'une fiche CIQUAL.

    Les rapprochements sont marqués non confirmés: l'app te les fera
    valider ou corriger une fois, et la correction vaudra pour toujours.
    """
    with bdd.base() as con:
        fiches = [dict(f) for f in con.execute("SELECT * FROM ciqual").fetchall()]
        if not fiches:
            return 0

        cles = {l["cle"] for l in con.execute(
            "SELECT DISTINCT cle FROM stock WHERE consomme_le IS NULL"
        ).fetchall()}
        cles |= {l["cle"] for l in con.execute(
            "SELECT DISTINCT cle FROM ingredient_recette"
        ).fetchall()}
        deja = {l["cle"] for l in con.execute("SELECT cle FROM aliment").fetchall()}

        associes, orphelins, douteux = 0, [], []
        for cle in sorted(cles - deja):
            if nutrition.est_negligeable(cle):
                continue  # eau, sel, épices, condiments à la cuillère
            trouvees = nutrition.chercher(fiches, cle, limite=1)
            if not trouvees:
                orphelins.append(cle)
                continue
            f = trouvees[0]
            if f["transforme"]:
                # "saumon" ne doit jamais devenir "saumon fumé" tout seul
                douteux.append(f"{cle} -> {f['nom']}")
                continue
            con.execute(
                """INSERT OR REPLACE INTO aliment
                   (cle, libelle, source, reference, confirme, kcal, proteines,
                    glucides, sucres, lipides, satures, fibres, sel)
                   VALUES (?, ?, 'ciqual', ?, 0, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (cle, f["nom"], f["code"],
                 *[f[n] for n in nutrition.NUTRIMENTS]),
            )
            associes += 1

    print(f"{associes} aliments rapprochés automatiquement, à confirmer dans l'app.")
    if douteux:
        print(f"{len(douteux)} laissés de côté car la meilleure fiche est un aliment "
              f"transformé, à trancher toi-même: {', '.join(douteux[:4])}")
    if orphelins:
        print(f"{len(orphelins)} sans correspondance: {', '.join(orphelins[:8])}")
    return associes


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m outils.importer_ciqual <fichier CIQUAL .xlsx ou .csv>")
    fichier = Path(sys.argv[1])
    if not fichier.exists():
        raise SystemExit(f"{fichier} introuvable.")
    importer(fichier)
