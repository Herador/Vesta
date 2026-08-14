"""Apports nutritionnels.

Principe: les chiffres sont calculés à partir de la table CIQUAL de
l'ANSES, jamais générés par un modèle. Un modèle qui invente des
calories est exactement ce qu'on veut éviter ici.

Deuxième principe: on dit toujours ce qui n'a pas pu être compté. Un
total qui ignore trois ingrédients sur huit sans le signaler est un
mensonge par omission, et c'est le défaut de la plupart des applis de
suivi. Chaque calcul renvoie donc sa couverture.
"""

import re
import unicodedata

from app.domaine.moteur import TAILLE, normaliser
from app.domaine import unites

NUTRIMENTS = ("kcal", "proteines", "glucides", "sucres",
              "lipides", "satures", "fibres", "sel")

# Reconnaissance des colonnes du fichier CIQUAL. Les intitulés changent
# d'une édition à l'autre ("Protéines, N x 6.25" puis "N x facteur de
# Jones"), donc on cherche des motifs plutôt que des noms exacts.
# Reconnaissance des colonnes du fichier CIQUAL. Chaque champ liste des
# jeux de mots qui doivent TOUS figurer dans l'intitulé. Indispensable
# ici: la table contient quatre colonnes d'énergie, deux en kilojoules
# et deux en kilocalories, qu'un simple préfixe confondrait.
COLONNES = {
    "code":       [["alim_code"]],
    "nom":        [["alim_nom_fr"]],
    "groupe":     [["alim_grp_nom_fr"]],
    "sousgroupe": [["alim_ssgrp_nom_fr"]],
    "kcal":       [["energie", "reglement", "kcal"], ["energie", "kcal"]],
    "proteines":  [["proteine", "jone"], ["proteine"]],
    "glucides":   [["glucide"]],
    "sucres":     [["sucre"]],
    "lipides":    [["lipide"]],
    "satures":    [["ag satures"], ["acide gras satures"]],
    "fibres":     [["fibre", "alimentaire"], ["fibre", "g 100"]],
    "sel":        [["sel chlorure"], ["sel"]],
}

# Trois catégories de mots, et la distinction est le coeur du sujet.
#
# PREPARATIONS: même aliment, cuisson différente. Comme tes recettes
# pèsent cru, la fiche crue est la bonne quelle que soit la cuisson, et
# la matière grasse ajoutée est déjà comptée comme ingrédient.
PREPARATIONS = {"cuit": 2, "cuite": 2, "vapeur": 2, "grille": 2, "grillee": 2,
                "poele": 2, "poelee": 2, "saute": 2, "sautee": 2, "roti": 2,
                "rotie": 2, "bouilli": 2, "bouillie": 2, "four": 2, "onde": 2,
                "blanchi": 2, "etuve": 2, "braise": 2, "poche": 2,
                "frit": 3, "frite": 3, "pane": 3, "panee": 3,
                "puree": 2.5, "compote": 2.5, "jus": 2.5}

# TRANSFORMATIONS DURES: aliment différent. Un saumon fumé n'est pas un
# saumon cuit autrement, c'est autre chose. Jamais associé tout seul.
TRANSFORMATIONS = {"fume", "fumee", "confit", "confite", "marine", "marinee",
                   "saumure", "sale", "salee", "sucre", "sucree", "sirop",
                   "rillette", "tartinade", "farci", "farcie", "prepare",
                   "preparee", "sandwich", "pizza", "tarte", "sauce", "surimi",
                   "aromatise", "aromatisee", "pane", "panee"}

# TRANSFORMATIONS DOUCES: c'est la forme sous laquelle on achète
# l'aliment. Des lentilles sont sèches, un concentré de tomate est
# appertisé, des graines de chia sont séchées. On pénalise un peu pour
# préférer le frais quand il existe, mais on n'interdit pas la liaison.
CONSERVATION = {"sec", "seche", "sechee", "deshydrate", "deshydratee", "appertise",
                "appertisee", "conserve", "reconstitue", "reconstituee",
                "surgele", "surgelee", "lyophilise"}

# Abats et morceaux particuliers: chercher "poulet" ne doit pas remonter
# le foie ni le pilon avant la viande elle-même.
MORCEAUX = {"foie", "coeur", "gesier", "rognon", "langue", "cervelle",
            "tripe", "os", "carcasse", "aile", "pilon", "cuisse",
            "manchon", "abat", "couenne"}

# Emballage et conditionnement: neutres, mais légèrement pénalisés pour
# préférer la fiche générique quand les deux existent.
CONDITIONNEMENT = {"preemballe", "preemballee", "rayon", "frai", "surgele"}

# Les fiches que CIQUAL destine explicitement à celui qui ne veut pas
# choisir. Ce sont nos meilleurs défauts.
GENERIQUES = ("aliment moyen", "sans precision", "tout type", "sans autre precision")


def est_generique(nom: str) -> bool:
    return any(g in sans_accents(nom) for g in GENERIQUES)


def sans_marqueurs(nom: str) -> str:
    """Retire les marques de fiche générique avant de calculer la clé.

    "Tomate sans précision, crue (aliment moyen)" doit donner la même
    clé que "Tomate, crue", sinon ces quatre mots de bruit la font
    perdre contre "Tomate verte, crue".
    """
    propre = sans_accents(nom)
    for marque in GENERIQUES:
        propre = propre.replace(marque, " ")
    return propre

BONUS_GENERIQUE = 3.0
BONUS_CRU = 2.5
BONUS_ELEVAGE = 0.3     # le saumon vendu en France est d'élevage
MALUS_TRANSFORME = 5.0
MALUS_HORS_SUJET = 6.0  # groupes écartés: glaces, boissons, plats préemballés


def sans_accents(texte: str) -> str:
    texte = unicodedata.normalize("NFD", texte.lower())
    return "".join(c for c in texte if unicodedata.category(c) != "Mn")


def cle_ciqual(nom: str) -> str:
    """Clé de recherche d'une fiche CIQUAL.

    Contrairement à normaliser(), on ne coupe rien et on ne retire aucun
    qualificatif: c'est précisément après la virgule que CIQUAL indique
    'cru', 'cuit à la vapeur' ou 'fumé'. Sans ces mots, impossible de
    distinguer un aliment brut d'un aliment transformé.
    """
    texte = re.sub(r"[^a-z0-9]+", " ", sans_accents(nom))
    mots = []
    for mot in texte.split():
        if mot in TAILLE:
            continue
        if len(mot) > 3 and mot[-1] in "sx":
            mot = mot[:-1]
        if mot not in TAILLE:
            mots.append(mot)
    return " ".join(mots)


def nettoyer(valeur) -> float | None:
    """Convertit une cellule CIQUAL en nombre.

    La table écrit '< 0,5', 'traces', '-' ou '' selon les cas. On prend
    la borne haute pour les '<', zéro pour les traces, et rien du tout
    quand la donnée est absente, ce qui vaut mieux qu'un zéro faux.
    """
    if valeur is None:
        return None
    if isinstance(valeur, (int, float)):
        return float(valeur)

    texte = str(valeur).strip().lower().replace("\xa0", "").replace(" ", "")
    if not texte or texte in {"-", "nd", "na"}:
        return None
    if "trace" in texte:
        return 0.0

    texte = texte.lstrip("<>≤≥").replace(",", ".")
    try:
        return float(texte)
    except ValueError:
        return None


def aplatir(entete) -> str:
    """Un intitulé CIQUAL contient des retours à la ligne au milieu des
    mots-clés. On les écrase avant toute comparaison."""
    return sans_accents(" ".join(str(entete or "").split()))


def associer_colonnes(entetes: list) -> dict[str, int]:
    """Retrouve l'index de chaque colonne utile dans le fichier."""
    propres = [aplatir(e) for e in entetes]
    trouvees: dict[str, int] = {}
    for champ, jeux in COLONNES.items():
        for mots in jeux:
            for i, entete in enumerate(propres):
                if i in trouvees.values():
                    continue
                if all(mot in entete for mot in mots):
                    trouvees[champ] = i
                    break
            if champ in trouvees:
                break
    return trouvees


def analyser(fiche: dict, mots_cherches: set[str],
             tete_cherchee: str = "") -> tuple[float, bool]:
    """Note une fiche et dit si elle désigne un aliment transformé.

    Un score bas est meilleur. Le drapeau `transforme` sert de garde-fou:
    on n'associe jamais automatiquement un saumon fumé à quelqu'un qui a
    écrit 'saumon'.
    """
    mots = set(fiche["cle"].split()) - MOTS_VIDES
    surplus = mots - mots_cherches
    score = len(surplus) - len(surplus & VARIANTES)
    nom = sans_accents(fiche["nom"])

    for mot, penalite in PREPARATIONS.items():
        if mot in mots and mot not in mots_cherches:
            score += penalite

    for mot in MORCEAUX:
        if mot in mots and mot not in mots_cherches:
            score += 2.5
    for mot in CONDITIONNEMENT:
        if mot in mots and mot not in mots_cherches:
            score += 0.5
    for mot in CONSERVATION:
        if mot in mots and mot not in mots_cherches:
            score += 1.5

    # Une fiche qui énumère ses variantes est une fiche générique:
    # "Poivron, vert, jaune ou rouge, cru" vaut mieux qu'un choix
    # arbitraire entre les trois couleurs. Mais le "ou" sert aussi à
    # nommer une espèce précise, "Champignon, chanterelle ou girolle",
    # et là ce serait un contresens. On ne récompense donc que les
    # fiches dont tout le surplus est une variante ou une cuisson.
    accessoires = (VARIANTES | set(PREPARATIONS) | CONSERVATION
                   | CONDITIONNEMENT | {"cru", "crue", "tout", "type"})
    if " ou " in nom and not (surplus - accessoires):
        score -= 2.0

    # "tout type" est la façon dont CIQUAL écrit l'aliment générique.
    # On lit la chaîne brute: "type" fait partie des mots de liaison
    # filtrés, il a donc disparu de `mots`.
    if "tout type" in fiche["cle"]:
        score -= 2.5

    transforme = False
    for mot in TRANSFORMATIONS:
        if mot in mots and mot not in mots_cherches:
            score += MALUS_TRANSFORME
            transforme = True

    # Un aliment est designe par le premier mot de sa fiche. Sans cette
    # regle, "beurre" tombe sur "Haricot beurre, cru" et "miel" sur
    # "Melon miel", qui sont des aliments totalement differents.
    tete = fiche["cle"].split()[0] if fiche["cle"] else ""
    if tete and tete == tete_cherchee:
        score -= 2.0

    if "cru" in mots or "crue" in mots:
        score -= BONUS_CRU
    if "elevage" in mots:
        score -= BONUS_ELEVAGE
    if not fiche.get("pertinent", 1):
        score += MALUS_HORS_SUJET
    if fiche.get("generique"):
        score -= 3.5
    if fiche.get("kcal") is None:
        # une fiche sans énergie ne sert à rien pour un suivi
        score += 4.0

    return round(score, 2), transforme


# Ce que tu écris à gauche, ce que CIQUAL écrit à droite.
ALIAS = {
    "pst": "proteine soja texturee",   # fiche unique, et réhydratée: à corriger à la main
    "pate": "pate seche",              # CIQUAL dit "Pâtes sèches, standard, crues"
    "nouille": "pate seche",
    "panko": "chapelure",
    "chapelure panko": "chapelure",
    "huile neutre": "huile tournesol",
    "skyr": "fromage blanc",
    "salade": "laitue",
    "riz jasmin": "riz thai",
    "riz rond": "riz blanc",
    "farine": "farine ble",
    "frite": "frite pomme de terre",
    "tagliatelle": "pate seche",
    "spaghetti": "pate seche",
    "pain complet levain": "pain complet",
    "germe soja": "graine germee haricot mungo",
    "chou chinois": "chou chinoi pe tsai",
    "beurre": "beurre mg doux",
    "vinaigre de riz": "vinaigre",
    "vinaigre riz": "vinaigre",
    "pate de sesame": "sesame graine",
    "pate sesame": "sesame graine",
    "germe de soja": "graine germee haricot mungo",
    "piment seche": "piment",
    "flocon avoine": "avoine flocon",
    "fruit rouge": "fruit rouge cru",
    "jus citron": "jus citron",
    "jus lime": "jus citron",
    "jus orange": "jus orange",
    "sauce soja foncee": "sauce soja",
    "vinaigre noir": "vinaigre",
    "pak choi": "chou chinoi pak choi",
}

# Aliments dont l'apport ne se mesure pas aux quantités de cuisine:
# eau de cuisson, sel, épices, et les condiments asiatiques dosés à la
# cuillère. Certains n'existent pas dans CIQUAL; les forcer vers une
# fiche approchante ferait plus de dégâts que de les compter pour zéro.
NEGLIGEABLES = {
    "eau", "sel", "poivre", "epice", "aromate", "herbe", "arome", "colorant",
    "levure", "bicarbonate", "gelatine", "agar", "bouillon", "vinaigre",
    "cumin", "curcuma", "paprika", "cannelle", "muscade", "curry", "safran",
    "coriandre moulue", "origan", "thym", "laurier", "piment", "masala",
    "garam masala", "quatre epice", "poivre sichuan", "poivre blanc",
    "vin de riz", "sauce huitre", "gochujang", "pate de haricot",
    "haricot noir fermente",
}

# Mots de liaison, ignorés des deux côtés de la comparaison.
MOTS_VIDES = {"de", "du", "des", "la", "le", "les", "a", "au", "aux", "en",
              "et", "ou", "l", "d", "un", "une", "avec", "sur", "sans", "type"}


def est_negligeable(cle: str) -> bool:
    """Vrai si l'aliment ne vaut pas la peine d'être associé à une fiche.

    Une entrée d'un seul mot suffit à disqualifier: "sel" attrape "sel de
    céleri". Une entrée de plusieurs mots doit être entièrement contenue,
    pour que "vin de riz" ne rende pas négligeable tout ce qui contient
    le mot "riz".
    """
    mots = set(cle.split()) - MOTS_VIDES
    for entree in NEGLIGEABLES:
        attendus = set(entree.split()) - MOTS_VIDES
        if len(attendus) == 1 and attendus <= mots:
            return True
        if len(attendus) > 1 and attendus <= mots:
            return True
    return False


# Conservé pour compatibilité: une seule règle, un seul comportement.
negligeable = est_negligeable


# Variantes qui ne coûtent rien: un poivron rouge reste un poivron, un
# saumon d'élevage reste un saumon. Sans ça, la fiche générique
# "Poivron, vert, jaune ou rouge, cru" serait pénalisée pour avoir cité
# ses trois couleurs.
VARIANTES = {"vert", "verte", "rouge", "jaune", "blanc", "blanche", "noir",
             "noire", "orange", "elevage", "sauvage", "standard", "moyen",
             "nature", "entier", "entiere", "demi",
             # façon CIQUAL de décrire la partie comestible: gratuit aussi
             "chair", "pulpe", "peau", "pepin", "noyau", "san", "cerneau"}


def mots_recherches(texte: str) -> set[str]:
    """Les mots à retrouver dans une fiche.

    On passe par cle_ciqual et non par normaliser, pour garder les
    chiffres et les qualificatifs: "crème 12%" doit pouvoir tomber sur
    "Crème 12 à 25% MG", ce qu'un simple "creme" ne permettrait jamais.
    """
    cle = normaliser(texte)
    if cle in ALIAS:
        # cle_ciqual pour couper les pluriels de la même façon que dans
        # les fiches: "doux" y est stocké "dou".
        return set(cle_ciqual(ALIAS[cle]).split()) - MOTS_VIDES
    # On garde les chiffres, qui distinguent une crème 12% d'une crème
    # entière, mais on jette les adjectifs de découpe, qui ne distinguent
    # rien du tout: personne ne cherche une fiche "carotte en tronçons".
    return set(normaliser(texte, garder_chiffres=True).split()) - MOTS_VIDES


def mots_ordonnes(texte: str) -> list[str]:
    """Les mêmes mots que mots_recherches, mais dans l'ordre d'écriture.

    Seul le premier compte: c'est lui qui nomme l'aliment. "huile
    d'olive" est une huile, "olive à l'huile" est une olive.
    """
    cle = normaliser(texte)
    source = ALIAS[cle] if cle in ALIAS else normaliser(texte, garder_chiffres=True)
    return [m for m in cle_ciqual(source).split() if m not in MOTS_VIDES]


def chercher_large(fiches: list[dict], nom: str, cle: str, limite: int = 8) -> list[dict]:
    """Cherche d'abord sur le libellé complet, puis sur la clé.

    "gousses d'ail" ne correspond à aucune fiche, parce que CIQUAL ne
    parle pas de gousses. Il faut donc pouvoir retomber sur "ail". Le
    libellé reste essayé en premier: c'est lui qui porte le "12%" de la
    crème ou le "fumé" du saumon.
    """
    trouvees = chercher(fiches, nom, limite)
    if not trouvees and cle and normaliser(nom) != cle:
        trouvees = chercher(fiches, cle, limite)
    return trouvees


def chercher(fiches: list[dict], texte: str, limite: int = 8) -> list[dict]:
    """Classe les fiches CIQUAL correspondant à un libellé.

    Une fiche n'est retenue que si elle contient tous les mots cherchés.
    C'est ce qui protège de la confusion que tu redoutais: chercher
    'saumon' remonte le saumon frais et relègue le fumé, mais chercher
    'saumon fumé' ne peut plus remonter que du fumé.
    """
    mots = mots_recherches(texte)
    if not mots:
        return []
    ordonnes = mots_ordonnes(texte)
    tete = ordonnes[0] if ordonnes else ""

    resultats = []
    for fiche in fiches:
        if not mots <= (set(fiche["cle"].split()) - MOTS_VIDES):
            continue
        score, transforme = analyser(fiche, mots, tete)
        resultats.append({**fiche, "score": score, "transforme": transforme})

    resultats.sort(key=lambda f: (f["score"], len(f["nom"])))
    return resultats[:limite]


def en_grammes(quantite: float | None, famille: str | None,
               cle: str) -> tuple[float | None, bool]:
    """Ramène une quantité en grammes, seule unité utilisable ici.

    Les compositions sont données pour 100 g. Une pièce passe par le
    poids moyen, un volume par l'approximation 1 ml pour 1 g, valable
    pour un lait ou une sauce, fausse d'environ 8% pour une huile.
    Les deux cas sont signalés comme approximatifs.
    """
    if quantite is None or famille is None:
        return None, False
    if famille == "masse":
        return quantite, False
    if famille == "volume":
        return quantite, True
    grammes, _ = unites.convertir(quantite, "piece", "masse", cle)
    return grammes, grammes is not None


def apports(lignes: list[dict], compositions: dict[str, dict],
            portions: int = 1) -> dict:
    """Additionne les apports d'une liste de lignes de repas.

    lignes:        [{nom, cle, quantite, famille}]
    compositions:  {cle: {kcal, proteines, ...}} pour 100 g
    """
    totaux = {n: 0.0 for n in NUTRIMENTS}
    comptes, ignores, approximatifs = [], [], []

    for ligne in lignes:
        composition = compositions.get(ligne["cle"])
        grammes, approx = en_grammes(ligne.get("quantite"), ligne.get("famille"),
                                     ligne["cle"])

        if composition is None:
            ignores.append({"nom": ligne["nom"], "raison": "aliment inconnu"})
            continue
        if grammes is None:
            ignores.append({"nom": ligne["nom"], "raison": "quantité non convertible"})
            continue

        for nutriment in NUTRIMENTS:
            valeur = composition.get(nutriment)
            if valeur is not None:
                totaux[nutriment] += valeur * grammes / 100

        comptes.append({"nom": ligne["nom"], "grammes": round(grammes, 1)})
        if approx:
            approximatifs.append(ligne["nom"])

    portions = max(1, portions)
    return {
        "total": {n: round(v, 1) for n, v in totaux.items()},
        "par_personne": {n: round(v / portions, 1) for n, v in totaux.items()},
        "couverture": {
            "comptes": comptes,
            "ignores": ignores,
            "approximatifs": approximatifs,
            "complet": not ignores,
        },
    }
