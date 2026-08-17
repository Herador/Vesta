"""Combien de temps un aliment se garde, selon l'endroit.

Sert à deux choses: proposer une date quand on n'en saisit pas, et
recalculer cette date quand un article change de rangement.

Les durées sont des ordres de grandeur usuels, pas des règles
sanitaires. Elles servent à faire remonter les bons produits dans les
suggestions, pas à décider si quelque chose est propre à la
consommation: pour ça, la date du paquet et le nez restent les seules
références. Toute date calculée ici se corrige à la main dans l'app.
"""

from datetime import date, timedelta

# Durées en jours, par lieu. Les entrées les plus précises l'emportent:
# "haricot vert" avant "haricot", et "haricot" avant la famille.
CONSERVATION: dict[str, dict[str, int]] = {
    # --- légumes feuilles et herbes: les plus fragiles
    "salade": {"frigo": 5, "congelo": 240},
    "laitue": {"frigo": 5, "congelo": 240},
    "epinard": {"frigo": 4, "congelo": 300},
    "blette": {"frigo": 5, "congelo": 300},
    "chou chinois": {"frigo": 7, "congelo": 240},
    "pak choi": {"frigo": 5, "congelo": 240},
    "persil": {"frigo": 6, "congelo": 180},
    "coriandre": {"frigo": 5, "congelo": 180},
    "menthe": {"frigo": 6, "congelo": 180},
    "basilic": {"frigo": 4, "congelo": 180},
    "ciboulette": {"frigo": 6, "congelo": 180},
    "germe": {"frigo": 3, "congelo": 120},

    # --- légumes fruits
    "tomate": {"frigo": 7, "placard": 5, "congelo": 240},
    "tomate cerise": {"frigo": 8, "placard": 5, "congelo": 240},
    "poivron": {"frigo": 10, "congelo": 300},
    "concombre": {"frigo": 7, "congelo": 60},
    "courgette": {"frigo": 7, "congelo": 300},
    "aubergine": {"frigo": 7, "congelo": 240},
    "champignon": {"frigo": 5, "congelo": 240},
    "brocoli": {"frigo": 6, "congelo": 300},
    "chou fleur": {"frigo": 8, "congelo": 300},
    "haricot vert": {"frigo": 5, "congelo": 300},
    "petits pois": {"frigo": 4, "congelo": 300},
    "avocat": {"frigo": 5, "placard": 4},

    # --- légumes racines et bulbes: la longue garde
    "carotte": {"frigo": 21, "placard": 10, "congelo": 300},
    "pomme de terre": {"placard": 30, "frigo": 21},
    "patate douce": {"placard": 25, "frigo": 18},
    "oignon": {"placard": 45, "frigo": 30},
    "oignon rouge": {"placard": 45, "frigo": 30},
    "oignon nouveau": {"frigo": 7, "congelo": 180},
    "echalote": {"placard": 40, "frigo": 30},
    "ail": {"placard": 60, "frigo": 40},
    "gingembre": {"frigo": 25, "placard": 12, "congelo": 300},
    "betterave": {"frigo": 20, "congelo": 240},

    # --- fruits
    "pomme": {"frigo": 30, "placard": 10},
    "poire": {"frigo": 12, "placard": 5},
    "orange": {"frigo": 20, "placard": 8},
    "citron": {"frigo": 21, "placard": 8},
    "lime": {"frigo": 18, "placard": 7},
    "pamplemousse": {"frigo": 20, "placard": 8},
    "kiwi": {"frigo": 14, "placard": 5},
    "raisin": {"frigo": 7},
    "fraise": {"frigo": 3, "congelo": 300},
    "framboise": {"frigo": 3, "congelo": 300},
    "fruit rouge": {"frigo": 3, "congelo": 300},
    "peche": {"frigo": 6, "placard": 3},
    "abricot": {"frigo": 5, "placard": 3},
    "melon": {"frigo": 6},
    "ananas": {"frigo": 6, "placard": 3},

    # --- protéines
    "poulet": {"frigo": 2, "congelo": 270},
    "dinde": {"frigo": 2, "congelo": 270},
    "lardon": {"frigo": 5, "congelo": 60},
    "saumon": {"frigo": 2, "congelo": 90},
    "truite": {"frigo": 2, "congelo": 90},
    "oeuf": {"frigo": 25},
    "tofu": {"frigo": 7, "congelo": 150},
    "pst": {"placard": 400},
    "lentille": {"placard": 400},
    "pois chiche": {"placard": 400},
    "haricot rouge": {"placard": 400},

    # --- laitages
    "lait": {"frigo": 5},
    "creme": {"frigo": 5},
    "yaourt": {"frigo": 20},
    "skyr": {"frigo": 20},
    "fromage blanc": {"frigo": 14},
    "beurre": {"frigo": 40, "congelo": 240},
    "parmesan": {"frigo": 60},
    "feta": {"frigo": 20},
    "fromage rape": {"frigo": 12, "congelo": 180},

    # --- féculents et secs
    "pain": {"placard": 3, "congelo": 90},
    "pain complet": {"placard": 4, "congelo": 90},
    "pain burger": {"placard": 6, "congelo": 90},
    "pain pita": {"placard": 8, "congelo": 90},
    "riz": {"placard": 700},
    "pate": {"placard": 700},
    "farine": {"placard": 400},
    "chapelure": {"placard": 200},
    "flocon avoine": {"placard": 300},
    "noix": {"placard": 180, "frigo": 300},
    "cacahuete": {"placard": 180},
    "graine": {"placard": 300},
}

# Quand l'aliment n'est pas dans la table, on retombe sur la famille de
# son rangement. Volontairement prudent au frigo, généreux au placard.
PAR_DEFAUT = {"frigo": 7, "congelo": 240, "placard": 120}

# Un aliment sans date connue et sans correspondance ne reçoit pas de
# date du tout: mieux vaut pas de compte à rebours qu'un faux.
SANS_ESTIMATION = {"sel", "poivre", "epice", "huile", "vinaigre", "sucre"}


def duree(cle: str, lieu: str) -> int | None:
    """Le nombre de jours de conservation, ou None si on ne sait pas.

    La correspondance se fait par mots: "haricot vert" trouve son entrée
    exacte, "pavé de saumon" retombe sur "saumon", et l'entrée la plus
    précise l'emporte quand plusieurs conviennent.
    """
    mots = set(cle.split())
    if not mots or mots & SANS_ESTIMATION:
        return None

    candidates = [(len(set(k.split())), v) for k, v in CONSERVATION.items()
                  if set(k.split()) <= mots]
    for _, lieux in sorted(candidates, reverse=True):
        if lieu in lieux:
            return lieux[lieu]
        # L'aliment est connu mais pas dans ce rangement: on n'invente
        # pas, la famille du lieu prendra le relais.
        break
    return PAR_DEFAUT.get(lieu)


def date_estimee(cle: str, lieu: str, depuis: date | None = None) -> date | None:
    """La date probable de fin, comptée depuis l'arrivée au stock."""
    jours = duree(cle, lieu)
    if jours is None:
        return None
    return (depuis or date.today()) + timedelta(days=jours)


def redater(cle: str, lieu: str, ajoute_le: date, ancienne: date | None) -> date | None:
    """La nouvelle date après un changement de rangement.

    Congeler prolonge, décongeler raccourcit. On recompte depuis l'entrée
    au stock plutôt que depuis aujourd'hui, sinon un aller-retour
    frigo-congélateur rajeunirait indéfiniment un produit.

    Un aliment sorti du congélateur fait exception: il repart de zéro,
    puisque c'est le moment de la décongélation qui lance le décompte.
    """
    jours = duree(cle, lieu)
    if jours is None:
        return ancienne
    if lieu == "congelo":
        return ajoute_le + timedelta(days=jours)
    depart = max(ajoute_le, date.today()) if ancienne is None else ajoute_le
    estimee = depart + timedelta(days=jours)
    return estimee if estimee >= date.today() else date.today() + timedelta(days=2)
