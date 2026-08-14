"""Remplit le stock avec un contenu de frigo réaliste, pour tester.

    python -m outils.peupler_stock            ajoute au stock existant
    python -m outils.peupler_stock --vider    repart d'un stock vide

Les dates sont calculées par rapport à aujourd'hui, donc le jeu reste
pertinent quel que soit le jour où tu le lances. Trois articles sont
volontairement en limite ou dépassés: c'est ce qui rend les suggestions
et la génération de recette intéressantes à observer.

Ce script sert au test. Ne le lance pas sur ta vraie base une fois que
tu auras saisi ton frigo, ou lance-le sans --vider en sachant que tu
auras des doublons à nettoyer.
"""

import sys
from datetime import date, timedelta

from app import base as bdd
from app.domaine import unites
from app.domaine.moteur import normaliser

# (nom, quantité, unité, lieu, jours avant péremption ou None)
STOCK = [
    # --- ce qui presse, le coeur du test
    ("Pavés de saumon",      300, "g",  "frigo",    0),
    ("Champignons de Paris", 250, "g",  "frigo",    1),
    ("Pak choï",             3,   "",   "frigo",    1),
    ("Crème 12%",            200, "ml", "frigo",    2),

    # --- la semaine
    ("Filet de poulet",      400, "g",  "frigo",    3),
    ("Brocoli",              1,   "",   "frigo",    4),
    ("Tofu",                 400, "g",  "frigo",    4),
    ("Poivron rouge",        2,   "",   "frigo",    5),
    ("Courgette",            2,   "",   "frigo",    6),
    ("Oignon nouveau",       4,   "",   "frigo",    6),
    ("Yaourt grec",          500, "g",  "frigo",    9),
    ("Oeufs",                6,   "",   "frigo",   14),
    ("Feta",                 200, "g",  "frigo",   16),
    ("Carotte",              5,   "",   "frigo",   18),
    ("Citron",               3,   "",   "frigo",   14),
    ("Citron vert",          2,   "",   "frigo",   12),
    ("Persil",               30,  "g",  "frigo",    5),
    ("Coriandre",            30,  "g",  "frigo",    4),

    # --- congélateur
    ("Petits pois",          500, "g",  "congelo", 180),
    ("Épinards",             400, "g",  "congelo", 150),
    ("Haricots verts",       600, "g",  "congelo", 200),

    # --- placard, l'ossature des recettes
    ("PST",                  500, "g",  "placard",  None),
    ("Riz",                  1,   "kg", "placard",  None),
    ("Pâtes",                500, "g",  "placard",  None),
    ("Lentilles corail",     500, "g",  "placard",  None),
    ("Pois chiches",         240, "g",  "placard",  400),
    ("Haricots rouges",      240, "g",  "placard",  400),
    ("Tomates concassées",   400, "g",  "placard",  300),
    ("Lait de coco",         400, "ml", "placard",  250),
    ("Sauce soja",           500, "ml", "placard",  200),
    ("Sauce d'huître",       250, "ml", "placard",  180),
    ("Vin de riz",           250, "ml", "placard",  300),
    ("Beurre de cacahuète",  350, "g",  "placard",  120),
    ("Cacahuètes",           200, "g",  "placard",   90),
    ("Oignon",               4,   "",   "placard",   20),
    ("Pomme de terre",       1,   "kg", "placard",   25),
    ("Ail",                  1,   "",   "placard",   40),

    # --- de quoi cuisiner ailleurs qu'en Asie: sans ces bases, le stock
    # est un garde-manger asiatique et toutes les propositions le seront.
    ("Farine",               1,   "kg", "placard",  200),
    ("Chapelure",            250, "g",  "placard",  120),
    ("Huile d'olive",        750, "ml", "placard",  365),
    ("Parmesan",             150, "g",  "frigo",     30),
    ("Beurre",               250, "g",  "frigo",     21),
    ("Lait",                 1,   "l",  "frigo",     10),
    ("Pain pita",            4,   "",   "placard",   12),
    ("Lentilles vertes",     500, "g",  "placard",  400),

    # --- ce qu'on a toujours, sans jamais savoir combien: quantité vide.
    # Ces articles ne sont jamais décomptés automatiquement, mais leur
    # présence au stock autorise les recettes qui les emploient. S'il
    # t'en manque un, retire-le et la recette te le signalera.
    ("Sel",                  None, "",   "placard",  None),
    ("Poivre",               None, "",   "placard",  None),
    ("Sucre",                None, "",   "placard",  None),
    ("Miel",                 None, "",   "placard",  None),
    ("Vinaigre de riz",      None, "",   "placard",  None),
    ("Huile",                None, "",   "placard",  None),
    ("Huile de sésame",      None, "",   "placard",  None),
    ("Fécule de maïs",       None, "",   "placard",  None),
    ("Chapelure",            None, "",   "placard",  None),
    ("Bouillon",             None, "",   "placard",  None),
    ("Concentré de tomate",  None, "",   "placard",  None),
    ("Moutarde",             None, "",   "placard",  None),
    ("Ketchup",              None, "",   "placard",  None),
    ("Gingembre",            None, "",   "placard",  None),
    ("Curcuma",              None, "",   "placard",  None),
    ("Curry",                None, "",   "placard",  None),
    ("Garam masala",         None, "",   "placard",  None),
    ("Coriandre moulue",     None, "",   "placard",  None),
    ("Piment",               None, "",   "placard",  None),
    ("Cannelle",             None, "",   "placard",  None),
    ("Thym",                 None, "",   "placard",  None),
    ("Laurier",              None, "",   "placard",  None),
    ("Graine de sésame",     None, "",   "placard",  None),
    ("Levure",               None, "",   "placard",  None),
    ("Sauce soja foncée",    None, "",   "placard",  None),
    ("Vin de riz",           None, "",   "placard",  None),
    ("Vinaigre de vin",      None, "",   "placard",  None),
    ("Vinaigre noir",        None, "",   "placard",  None),
    ("Poivre de Sichuan",    None, "",   "placard",  None),
    ("Quatre-épices",        None, "",   "placard",  None),
    ("Cumin",                None, "",   "placard",  None),
    ("Paprika",              None, "",   "placard",  None),
    ("Origan",               None, "",   "placard",  None),

    # --- le petit déjeuner, sinon aucune recette du matin ne sort
    ("Skyr",                 500,  "g",  "frigo",     11),
    ("Flocons d'avoine",     500,  "g",  "placard",  200),
    ("Fruits rouges",        450,  "g",  "congelo",  200),
    ("Noix",                 200,  "g",  "placard",  150),
    ("Graines de chia",      200,  "g",  "placard",  200),
    ("Pain complet",         6,    "",   "placard",    5),
    ("Fromage blanc",        500,  "g",  "frigo",     10),
    ("Concombre",            1,    "",   "frigo",      7),
    ("Laitue",               1,    "",   "frigo",      5),
    ("Tomate cerise",        250,  "g",  "frigo",      6),
    ("Pâte de sésame",       300,  "g",  "placard",  180),
    ("Menthe",               20,   "g",  "frigo",      4),
]


def peupler(vider: bool = False) -> None:
    bdd.initialiser()
    aujourdhui = date.today()
    maintenant = f"{aujourdhui.isoformat()}T12:00:00"

    with bdd.base() as con:
        if vider:
            con.execute("DELETE FROM stock")
            print("Stock vidé.")

        for nom, quantite, unite, lieu, jours in STOCK:
            valeur, famille = unites.vers_base(quantite, unite)
            limite = (aujourdhui + timedelta(days=jours)).isoformat() if jours is not None else None
            con.execute(
                """INSERT INTO stock (nom, cle, quantite, famille, lieu, date_limite, ajoute_le)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (nom, normaliser(nom), valeur, famille, lieu, limite, maintenant),
            )

        lignes = con.execute(
            "SELECT lieu, COUNT(*) n FROM stock WHERE consomme_le IS NULL GROUP BY lieu"
        ).fetchall()

    total = sum(l["n"] for l in lignes)
    detail = ", ".join(f"{l['n']} au {l['lieu']}" for l in lignes)
    print(f"{len(STOCK)} articles ajoutés. Stock actif: {total} ({detail}).")
    print("Quatre articles périment sous 48 h, de quoi voir le moteur réagir.")


if __name__ == "__main__":
    peupler(vider="--vider" in sys.argv)
