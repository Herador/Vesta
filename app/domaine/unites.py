"""Unités et quantités.

Règle centrale: on ne stocke jamais une valeur avec son unité d'affichage.
Tout est ramené à l'unité de référence de sa famille, le gramme, le
millilitre ou la pièce. Le kilo et le litre ne sont que des masques
d'affichage. C'est ce qui rend le décompte exact: 2 kg de PST moins 20 g
donne 1980 g, réaffiché en 1,98 kg.
"""

# Facteur vers l'unité de référence de chaque famille.
FAMILLES: dict[str, dict[str, float]] = {
    "masse": {"g": 1, "kg": 1000, "mg": 0.001},
    "volume": {"ml": 1, "cl": 10, "dl": 100, "l": 1000, "càs": 15, "càc": 5,
               "cas": 15, "cac": 5, "c. à soupe": 15, "c. à café": 5},
    "piece": {"": 1, "pc": 1, "pièce": 1, "piece": 1},
}

REFERENCE = {"masse": "g", "volume": "ml", "piece": "pc"}

# Façons humaines de compter une pièce. Un modèle écrira spontanément
# "1 gousse d'ail" ou "2 tranches de pain": autant l'accepter et le
# ramener à la pièce plutôt que de rejeter une recette par ailleurs bonne.
SYNONYMES_PIECE = {
    "gousse", "gousses", "tranche", "tranches", "brin", "brins", "feuille",
    "feuilles", "unite", "unites", "unité", "unités", "piece", "pieces",
    "pièce", "pièces", "pc", "part", "parts", "portion", "portions",
    "tige", "tiges", "botte", "bottes", "boite", "boîte", "sachet", "pot",
    "bocal", "branche", "branches", "oeuf", "pavé", "pave", "filet",
}

# Unités trop vagues pour être décomptées. L'ingrédient est conservé
# pour la recette, mais aucune quantité n'est retirée du stock.
IGNOREES = {"pincée", "pincee", "poignée", "poignee", "trait", "filet",
            "qs", "au goût", "au gout"}

# Poids moyen d'une pièce, en grammes. Sert uniquement quand une recette
# demande des grammes alors que le stock est compté en pièces, ou
# l'inverse. Toujours approximatif, et signalé comme tel.
EQUIVALENCES: dict[str, float] = {
    "oeuf": 55, "gousse ail": 5, "ail": 5, "oignon": 130, "oignon rouge": 130,
    "oignon nouveau": 18, "echalote": 30, "carotte": 90, "poivron": 160,
    "tomate": 120, "courgette": 250, "aubergine": 280, "pomme de terre": 150,
    "patate douce": 250, "citron": 100, "citron vert": 70, "pomme": 180,
    "kiwi": 80, "pak choi": 150, "pain burger": 60, "pain pita": 70,
    "tranche pain": 35, "sucrine": 120, "laitue": 250, "brocoli": 450,
    "pave saumon": 130, "filet poulet": 150, "champignon": 20,
}


def normaliser_unite(unite: str) -> str:
    """Ramène une unité écrite librement à l'une des unités connues."""
    u = (unite or "").strip().lower()
    return "" if u in SYNONYMES_PIECE else u


def vers_base(quantite: float | None, unite: str) -> tuple[float | None, str | None]:
    """Convertit une saisie humaine en couple (valeur de référence, famille).

    >>> vers_base(2, "kg")
    (2000.0, 'masse')
    >>> vers_base(3, "càs")
    (45.0, 'volume')
    >>> vers_base(1, "")        # un poivron
    (1.0, 'piece')
    """
    if quantite is None:
        return None, None

    u = normaliser_unite(unite)
    if u in IGNOREES:
        return None, None

    for famille, unites in FAMILLES.items():
        if u in unites:
            return float(quantite) * unites[u], famille
    return None, None


def afficher(quantite: float | None, famille: str | None, nom: str = "") -> str:
    """Remet une valeur de référence dans l'unité la plus lisible.

    Une pièce n'a pas d'unité: on réutilise le nom de l'article, au
    pluriel s'il y en a plusieurs. C'est pourquoi tu n'as jamais à taper
    d'unité pour un poivron.
    """
    if quantite is None or famille is None:
        return ""

    if famille == "masse":
        return f"{nombre(quantite / 1000)} kg" if quantite >= 1000 else f"{nombre(quantite)} g"

    if famille == "volume":
        return f"{nombre(quantite / 1000)} l" if quantite >= 1000 else f"{nombre(quantite)} ml"

    etiquette = nom.strip().lower()
    # Un seul mot se met au pluriel sans risque. Au-delà, on n'y touche
    # pas: "2 gousse d'ail hachées" serait pire que "2 gousse d'ail hachée".
    if (quantite > 1 and etiquette and " " not in etiquette
            and etiquette not in INVARIABLES
            and not etiquette.endswith(("s", "x"))):
        etiquette += "s"
    return f"{nombre(quantite)} {etiquette}".strip()


def nombre(valeur: float) -> str:
    """Virgule décimale et pas de zéro inutile: 1,98 et non 1.98 ou 2,00."""
    arrondi = round(valeur, 2)
    if abs(arrondi - round(arrondi)) < 0.005:
        return str(int(round(arrondi)))
    return f"{arrondi:g}".replace(".", ",")


LIBELLES = {"càs": "c. à soupe", "cas": "c. à soupe",
            "càc": "c. à café", "cac": "c. à café"}
INVARIABLES = {"ail", "riz", "persil", "sel", "poivre", "sucre", "curry"}


def afficher_dans(quantite: float | None, unite: str, nom: str = "",
                  famille: str | None = None) -> str:
    """Affiche dans l'unité de saisie quand elle est plus parlante.

    Une recette qui annonce 30 ml de sucre est illisible: en cuisine on
    compte en cuillères. On repasse donc dans l'unité d'origine pour les
    cuillères, et on garde le gramme et le millilitre pour le reste.
    """
    u = (unite or "").strip().lower()
    if quantite is not None and u in LIBELLES:
        for unites_famille in FAMILLES.values():
            if u in unites_famille:
                return f"{nombre(quantite / unites_famille[u])} {LIBELLES[u]}"
    return afficher(quantite, famille, nom)


def convertir(quantite: float, depuis: str, vers: str, cle: str) -> tuple[float | None, bool]:
    """Passe d'une famille à l'autre via le poids moyen d'une pièce.

    Renvoie la valeur et un drapeau indiquant qu'elle est approximative.
    Quand l'équivalence est inconnue, on renvoie None: l'app préfère
    poser la question au moment du décompte plutôt que d'inventer.
    """
    if depuis == vers:
        return quantite, False
    if "volume" in (depuis, vers):
        return None, False  # densité inconnue, on ne devine pas

    grammes = equivalence(cle)
    if grammes is None:
        return None, False
    if depuis == "piece" and vers == "masse":
        return quantite * grammes, True
    if depuis == "masse" and vers == "piece":
        return quantite / grammes, True
    return None, False


def equivalence(cle: str) -> float | None:
    """Cherche le poids d'une pièce, en acceptant les clés composées.

    'pave saumon' est trouvé directement, 'saumon fume' retombe sur
    l'entrée la plus spécifique qui partage ses mots.
    """
    if cle in EQUIVALENCES:
        return EQUIVALENCES[cle]
    mots = set(cle.split())
    candidates = [
        (len(set(k.split())), v)
        for k, v in EQUIVALENCES.items()
        if set(k.split()) <= mots or mots <= set(k.split())
    ]
    return max(candidates)[1] if candidates else None
