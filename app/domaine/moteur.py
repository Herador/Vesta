"""Moteur local: propose des recettes du carnet à partir du stock réel.

Aucun appel réseau, aucun coût, fonctionne hors ligne. Le principe:
on note chaque recette du carnet selon deux critères qui comptent
vraiment le soir, ce qu'elle utilise de ce qui va périmer, et ce
qu'il manque pour la faire.

Ce module ne connaît pas la base de données: il reçoit des listes de
dictionnaires et renvoie des résultats. C'est ce qui le rend testable
en deux lignes, sans démarrer le serveur.
"""

import re
import unicodedata
from dataclasses import dataclass, field

# Mots qui décrivent l'état d'un aliment, pas l'aliment lui-même.
# On les retire pour que "saumon frais" et "saumon" soient la même chose.
# Attention à ne jamais mettre de couleur ici: haricot rouge et haricot
# vert doivent rester deux ingrédients différents.
# Adjectifs de taille, de forme, de découpe et de contenant. Ils ne
# désignent jamais un aliment différent: une carotte en lamelles reste
# une carotte. Retirés partout, y compris dans les fiches CIQUAL, sans
# quoi "petits pois" ne retrouverait jamais "Petits pois, crus".
TAILLE = {
    "moyen", "moyenne", "gro", "grosse", "fin", "fine", "epai", "epaisse",
    "mince", "long", "longue", "court", "courte", "droit", "droite",
    "beau", "belle", "joli", "jolie", "calibre", "gousse", "brin", "bouquet",
    "petit", "petite", "grand", "grande",
    "lamelle", "batonnet", "cisele", "ciselee", "effeuille", "emiette",
    "emiettee", "ecrase", "ecrasee", "presse", "pressee", "evide", "evidee",
    "epluche", "epluchee", "pele", "pelee", "lave", "lavee", "essore",
    "essoree", "hache", "emince", "rape", "coupe", "cube", "laniere",
    "julienne", "rondelle", "fleurette", "troncon", "quartier", "morceau",
    "poignee", "pincee", "filet", "trait", "louche", "cuillere", "boite",
    "bocal", "sachet", "paquet", "pot", "barquette", "portion", "part",
}

# État, cuisson et mots de liaison. Retirés de TES libellés, mais gardés
# dans les fiches CIQUAL: c'est là que se joue la différence entre un
# saumon cru et un saumon fumé.
ETAT = {
    # "frais" avait été retiré pour distinguer la crème fraîche de la
    # crème dessert. C'était une mauvaise raison: en cuisine les deux
    # crèmes sont interchangeables, alors que "pavés de saumon frais"
    # cessait d'être reconnu comme du saumon.
    "frai", "fraiche", "bio", "surgele", "congele", "nature", "entier",
    "demi", "cru", "cuit",
    "non", "sans", "peau", "dore", "concasse",
    "pile", "moulu", "battu", "fondu", "chaud", "froid", "tiede", "creuse",
    "farci", "tranche", "de", "du", "des", "le", "la", "les", "un", "une",
    "en", "au", "aux", "a", "l", "d", "et", "pour", "avec", "couvrir",
    "environ", "feuille", "decongele", "degele",
    "entiere", "hachee", "emincee", "rapee", "coupee", "doree", "egouttee",
    "concassee", "pilee", "moulue", "battue", "fondue", "creusee",
    "farcie", "chaude", "froide",
}

QUALIFICATIFS = TAILLE | ETAT

# Appliqués après normalisation, sur la chaîne entière.
SYNONYMES = {
    "proteine soja texturee": "pst",
    "proteine soja granule": "pst",
    "proteine soja": "pst",
    "soja texture": "pst",
    "emince soja": "pst",
    "pomme terre": "pomme de terre",
    "pdt": "pomme de terre",
    "pousse epinard": "epinard",
    "blanc poulet": "poulet",
    "filet poulet": "poulet",
    "escalope dinde": "dinde",
    "pave saumon": "saumon",
    "champignon pari": "champignon",
    "chou chinoi": "chou chinois",
    "gousse ail": "ail",
    # Le même aliment sous deux noms: une sauce à l'arachide est une
    # sauce à la cacahuète, et les deux figurent dans les recettes.
    "arachide": "cacahuete",
    "pate arachide": "beurre cacahuete",
    "beurre arachide": "beurre cacahuete",
    # "citron" est inclus dans "citron vert", donc les deux se
    # confondaient. Une lime n'est pas un citron: on la renomme.
    "citron vert": "lime",
    "jus citron vert": "lime",
    "zeste citron vert": "lime",
    "jus lime": "lime",
}


def normaliser(texte: str, garder_chiffres: bool = False) -> str:
    """Ramène un libellé humain à une clé comparable.

    'Pavés de saumon frais' et 'saumon' donnent tous les deux 'saumon'.
    Le singulier est obtenu en coupant le s ou le x final, ce qui produit
    parfois des mots faux comme 'poi' pour 'pois'. Sans importance: seule
    compte la cohérence entre les deux côtés de la comparaison.
    """
    texte = texte.lower()
    # Ce qui suit une parenthèse, une virgule ou un "ou" est une précision,
    # pas l'aliment: "citron (zeste et jus)" et "muesli ou flocons" doivent
    # donner "citron" et "muesli".
    texte = re.sub(r"\(.*?\)", " ", texte)
    texte = re.split(r",| ou ", texte)[0]

    texte = unicodedata.normalize("NFD", texte)
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    texte = re.sub(r"[^a-z0-9]+", " ", texte)

    # "non salées" ne doit jamais devenir "salées". Quand une négation
    # porte sur un mot, on retire les deux: mieux vaut perdre la nuance
    # que l'inverser.
    jetons, sauter = [], False
    for i, mot in enumerate(texte.split()):
        if sauter:
            sauter = False
            continue
        if mot in ("non", "san", "sans"):
            sauter = True
            continue
        jetons.append(mot)

    mots = []
    for mot in jetons:
        if mot.isdigit() and not garder_chiffres:
            continue  # pour l'appariement, "crème 12%" est de la crème
        if mot in QUALIFICATIFS:
            continue  # avant la coupe du pluriel, sinon "sans" devient "san"
        if len(mot) > 3 and mot[-1] in "sx":
            mot = mot[:-1]
        if mot and mot not in QUALIFICATIFS:
            mots.append(mot)

    cle = " ".join(mots)
    return SYNONYMES.get(cle, cle)


# Mots qui font d'un aliment un autre aliment. Le jus d'un citron n'est
# pas un citron, l'huile d'olive n'est pas une olive, et une pomme de
# terre n'est pas une pomme. Quand l'un de ces mots figure d'un seul
# côté de la comparaison, les deux ne se correspondent pas, même si les
# ensembles de mots s'incluent.
TRANSFORMATIONS = {
    "jus", "zeste", "huile", "farine", "lait", "creme", "beurre", "sirop",
    "puree", "compote", "confiture", "poudre", "sauce", "vinaigre", "pate",
    "graine", "germe", "pousse", "fleur", "bouillon", "extrait", "essence",
    "sucre", "vin", "biere", "coulis", "concentre", "flocon", "semoule",
    # cas particuliers du français: le second mot change l'aliment
    "terre", "coco",
}


# Mots qui précisent une variété sans changer l'aliment. Un poivron
# rouge reste un poivron; une pâte de crevettes n'est pas des pâtes.
# Seuls ces mots-là autorisent une correspondance par inclusion.
VARIETES = {
    "vert", "verte", "rouge", "jaune", "blanc", "blanche", "noir", "noire",
    "orange", "rose", "violet", "elevage", "sauvage", "nouveau", "nouvelle",
    "doux", "douce", "complet", "complete", "cerise", "rond", "ronde",
    "long", "longue", "basmati", "thai", "jasmin", "corail", "vierge",
    "extra", "fume", "fumee", "italien", "grec", "grecque", "chinoi",
    "gre", "semi", "allege", "entier", "entiere", "nature", "bio",
}


def correspond(cle_a: str, cle_b: str) -> bool:
    """Deux clés désignent-elles le même aliment ?

    On compare des ensembles de mots plutôt que des chaînes, et on accepte
    l'inclusion dans les deux sens: 'saumon' correspond à 'saumon fume',
    mais 'haricot vert' ne correspond pas à 'haricot rouge' puisque ni
    l'un ni l'autre n'est inclus dans son voisin.
    """
    a, b = set(cle_a.split()), set(cle_b.split())
    if not a or not b:
        return False
    # Une transformation présente d'un seul côté disqualifie: sans ce
    # test, "citron" et "jus de citron" seraient le même ingrédient.
    surplus = a ^ b
    if surplus & TRANSFORMATIONS:
        return False
    # Les mots restants après normalisation désignent des aliments, pas
    # des états: seule une variété peut différer. Sans cette règle,
    # "pâte de crevettes" correspondait à "pâtes".
    if surplus - VARIETES:
        return False
    return a <= b or b <= a


# Le barème d'urgence, en jours restants. Un seul pour tout le projet:
# le poids (score des suggestions) et le rang (tri et marqueurs de
# l'assistant) en sortent tous les deux, donc un seuil ne bouge qu'ici.
PALIERS_URGENCE: list[tuple[int, float]] = [
    (0, 4.0),   # aujourd'hui ou dépassé
    (2, 3.0),   # sous deux jours
    (4, 1.5),
    (7, 0.6),   # cette semaine
]
POIDS_LOINTAIN = 0.3     # au-delà d'une semaine
POIDS_SANS_DATE = 0.2    # les épices, l'huile: aucune échéance


def poids_urgence(jours: int | None) -> float:
    """Combien vaut le fait d'utiliser cet article ce soir."""
    if jours is None:
        return POIDS_SANS_DATE
    for seuil, poids in PALIERS_URGENCE:
        if jours <= seuil:
            return poids
    return POIDS_LOINTAIN


def rang_urgence(jours: int | None) -> int:
    """Position dans le barème, 0 = le plus pressé. Sert à trier une
    liste et à choisir un marqueur. Sans date = le moins pressé."""
    if jours is None:
        return len(PALIERS_URGENCE) + 1
    for rang, (seuil, _) in enumerate(PALIERS_URGENCE):
        if jours <= seuil:
            return rang
    return len(PALIERS_URGENCE)


@dataclass
class Suggestion:
    recette: dict
    score: float
    utilise: list[dict] = field(default_factory=list)      # articles du stock
    manquants: list[str] = field(default_factory=list)     # essentiels absents
    pourquoi: str = ""


def proposer(
    stock: list[dict],
    recettes: list[dict],
    imposes: list[int] | None = None,
    limite: int = 6,
) -> list[Suggestion]:
    """Classe les recettes du carnet selon le stock du moment.

    stock:     [{id, nom, jours_restants, ...}]
    recettes:  [{id, titre, ingredients: [{nom, cle, essentiel}], ...}]
    imposes:   ids d'articles du stock qui doivent absolument être utilisés

    Il n'y a plus de liste de "basiques" supposés au placard: ce qu'on a
    toujours sous la main est saisi dans le stock, sans quantité, et un
    manque redevient visible.
    """
    stock_cles = [(a, a.get("cle") or normaliser(a["nom"])) for a in stock]
    imposes = imposes or []

    resultats: list[Suggestion] = []

    for recette in recettes:
        utilise, manquants, manquants_secondaires = [], [], []
        urgences: list[float] = []
        essentiels = 0

        for ing in recette["ingredients"]:
            if ing["essentiel"]:
                essentiels += 1

            trouve = next(
                (article for article, cle in stock_cles if correspond(ing["cle"], cle)),
                None,
            )
            if trouve:
                utilise.append(trouve)
                urgences.append(poids_urgence(trouve.get("jours_restants")))
                continue

            (manquants if ing["essentiel"] else manquants_secondaires).append(ing["nom"])

        # Une recette qui n'utilise rien du stock n'a aucun intérêt ici.
        if not utilise:
            continue

        ids_utilises = {a["id"] for a in utilise}
        if imposes and not set(imposes) <= ids_utilises:
            continue  # elle ne case pas ce que l'utilisateur a exigé

        couverture = 1.0 if essentiels == 0 else (essentiels - len(manquants)) / essentiels

        # Le malus par ingrédient manquant décroît: le premier manque
        # coûte cher, les suivants moins. Sans ça, un citron absent
        # suffisait à faire passer derrière un plat qui sauve le saumon
        # de demain, ce qui est exactement l'inverse du but.
        # L'urgence ne s'additionne pas à parts égales: ce qui compte est
        # de sauver l'aliment le plus menacé, pas d'en accumuler. Sans ce
        # maximum dominant, trois ingrédients à quatre jours passaient
        # devant un saumon qui périme aujourd'hui.
        urgence = max(urgences) + 0.4 * (sum(urgences) - max(urgences))

        malus = sum(2.5 / (1 + i) for i in range(len(manquants)))
        score = couverture * 10 + urgence - malus - 0.4 * len(manquants_secondaires)

        if recette.get("favori"):
            score += 1.5
        if recette.get("categorie") in ("petitdej", "collation"):
            score -= 5.0  # ne concurrence pas un plat du soir
        score -= lassitude(recette.get("derniere_fois"))

        resultats.append(Suggestion(
            recette=recette,
            score=round(score, 2),
            utilise=utilise,
            manquants=manquants,
            pourquoi=expliquer(utilise, manquants),
        ))

    resultats.sort(key=lambda s: s.score, reverse=True)
    return resultats[:limite]


def lassitude(derniere_fois: str | None) -> float:
    """Malus pour une recette faite récemment. On ne veut pas du bibimbap
    trois fois dans la semaine sous prétexte qu'il matche bien."""
    if not derniere_fois:
        return 0.0
    from datetime import date, datetime
    try:
        faite = datetime.fromisoformat(derniere_fois).date()
    except ValueError:
        return 0.0
    ecart = (date.today() - faite).days
    if ecart <= 6:
        return 4.0
    if ecart <= 13:
        return 2.0
    if ecart <= 20:
        return 0.8
    return 0.0


def expliquer(utilise: list[dict], manquants: list[str]) -> str:
    """La phrase que l'app affichera sous le titre de la recette."""
    presses = [a["nom"] for a in utilise
               if a.get("jours_restants") is not None and a["jours_restants"] <= 2]

    if presses:
        debut = "Elle passe " + joindre(presses) + " avant qu'il ne soit trop tard"
    else:
        debut = "Elle utilise " + joindre([a["nom"] for a in utilise[:3]])

    if not manquants:
        return debut + ", et tu as tout le reste."
    if len(manquants) == 1:
        return debut + ". Il te manque juste " + manquants[0] + "."
    return debut + ". Il te manque " + joindre(manquants) + "."


def joindre(mots: list[str]) -> str:
    mots = [m.lower() for m in mots]
    if len(mots) <= 1:
        return "".join(mots)
    return ", ".join(mots[:-1]) + " et " + mots[-1]
