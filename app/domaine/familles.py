"""À quelle famille appartient un aliment.

Sert uniquement à l'affichage: l'application montre un pictogramme par
famille plutôt qu'une pastille anonyme. La liste est volontairement
courte, une quinzaine de familles, parce qu'un pictogramme par aliment
serait impossible à tenir et illisible à petite taille.

La correspondance vit ici et non dans le front: c'est le même genre de
connaissance que les durées de conservation, et elle se teste sans
navigateur.
"""

from app.domaine.moteur import normaliser

# Un mot qui l'emporte sur tous les autres, quelle que soit la précision
# des entrées. "sauce soja" est un condiment avant d'être une légumineuse,
# et "huile de sésame" un condiment avant d'être une graine.
PREMIERS = {
    "sauce": "condiment", "huile": "condiment", "vinaigre": "condiment",
    "bouillon": "condiment", "jus": "condiment",
    # Une confiture de fraise est un sucre, pas un fruit; un miel aussi.
    "sirop": "sucre", "confiture": "sucre", "miel": "sucre",
    "compote": "sucre", "chocolat": "sucre",
}

# En dehors de ces mots, la première famille dont tous les mots figurent
# dans la clé l'emporte, et les entrées les plus précises passent devant.
FAMILLES: dict[str, tuple[str, ...]] = {
    "poisson": (
        "saumon", "truite", "cabillaud", "colin", "lieu", "merlu", "thon",
        "sardine", "maquereau", "poisson", "dorade", "bar", "sole",
    ),
    "viande": (
        "poulet", "dinde", "canard", "pintade", "caille",
        "boeuf", "porc", "agneau", "veau", "lapin", "lardon", "jambon",
        "saucisse", "chorizo", "bacon", "steak", "viande",
    ),
    "oeuf": ("oeuf",),
    "laitage": (
        "lait", "creme", "yaourt", "skyr", "fromage", "feta", "parmesan",
        "mozzarella", "beurre", "mascarpone", "ricotta", "chevre",
    ),
    "champignon": ("champignon", "cepe", "girolle", "shiitake", "pleurote"),
    "feuille": (
        "salade", "laitue", "epinard", "blette", "chou", "pak choi", "roquette",
        "mache", "cresson", "endive", "sucrine", "brocoli", "chou fleur",
    ),
    "herbe": (
        "persil", "coriandre", "menthe", "basilic", "ciboulette", "aneth",
        "estragon", "thym", "laurier", "romarin",
    ),
    "racine": (
        "carotte", "pomme de terre", "patate douce", "navet", "betterave",
        "radis", "panais", "topinambour", "celeri", "oignon", "echalote",
        "ail", "gingembre", "poireau",
    ),
    "legume": (
        "tomate", "poivron", "courgette", "aubergine", "concombre",
        "haricot vert", "courge", "potiron", "mais",
        "artichaut", "asperge", "fenouil", "germe", "legume",
    ),
    "fruit": (
        "pomme", "poire", "orange", "citron", "lime", "banane", "kiwi",
        "raisin", "fraise", "framboise", "peche", "abricot", "melon",
        "ananas", "mangue", "avocat", "prune", "cerise", "fruit",
    ),
    "legumineuse": (
        "lentille", "pois chiche", "pois casse", "pois", "petits pois",
        "haricot rouge", "haricot blanc", "haricot noir", "feve",
        "pst", "tofu", "tempeh", "soja", "seitan", "edamame",
    ),
    "cereale": (
        "riz", "pate", "nouille", "semoule", "boulgour", "quinoa", "farine",
        "flocon", "avoine", "polenta", "couscous", "chapelure",
    ),
    "pain": ("pain", "tortilla", "pita", "wrap", "brioche", "biscotte"),
    "graine": (
        "noix", "noi", "cacahuete", "amande", "noisette", "graine", "sesame",
        "pistache", "chia", "tournesol", "courge graine",
    ),
    "condiment": (
        "sauce", "vinaigre", "huile", "moutarde", "ketchup",
        "concentre", "bouillon", "gochujang", "pate de haricot", "vin",
    ),
    "epice": (
        "sel", "poivre", "cumin", "curcuma", "paprika", "cannelle", "curry",
        "masala", "piment", "muscade", "safran", "epice", "quatre",
        "origan", "basilic seche", "herbe de provence", "levure",
        "bicarbonate", "gingembre moulu", "coriandre moulue", "anis",
        "clou de girofle", "vanille", "carvi", "fenugrec", "sumac",
    ),
    "conserve": ("tomate concassee", "conserve", "appertise"),
    "sucre": ("sucre", "chocolat", "confiture", "compote", "biscuit"),
}


# Les entrées ci-dessus sont écrites en français courant; les clés
# qu'on leur compare ont subi la normalisation, qui coupe les pluriels.
# Sans ce passage, "pois chiche" ne rencontrerait jamais "poi chiche" et
# les légumineuses restaient sans pictogramme.
FAMILLES = {nom: tuple(normaliser(e) for e in entrees)
            for nom, entrees in FAMILLES.items()}
PREMIERS = {normaliser(mot): nom for mot, nom in PREMIERS.items()}


def famille(cle: str) -> str:
    """La famille d'un aliment, ou 'autre' si on ne sait pas.

    >>> famille("champignon de pari")
    'champignon'
    >>> famille("pave saumon")
    'poisson'
    """
    mots = set(cle.split())
    if not mots:
        return "autre"

    for mot, nom in PREMIERS.items():
        if mot in mots:
            return nom

    meilleure, precision = "autre", 0
    for nom, entrees in FAMILLES.items():
        for entree in entrees:
            attendus = set(entree.split())
            if attendus <= mots and len(attendus) > precision:
                meilleure, precision = nom, len(attendus)
    return meilleure
