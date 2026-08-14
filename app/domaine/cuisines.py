"""Les cuisines du monde, rangées par continent.

Sert à deux choses: proposer une origine variée au modèle, et savoir
dans quel fichier de recettes une création irait naturellement.

La liste n'a pas vocation à être exhaustive, seulement assez large pour
qu'on ne retombe pas trois fois de suite sur la même région. Ajoute ce
qui te manque, l'ordre à l'intérieur d'un continent n'a pas d'importance.
"""

import random

CUISINES: dict[str, list[str]] = {
    "asie": [
        "chinoise", "sichuanaise", "cantonaise", "japonaise", "coréenne",
        "thaïe", "vietnamienne", "indienne", "indonésienne", "malaisienne",
        "philippine", "taïwanaise", "singapourienne", "népalaise",
        "sri-lankaise", "birmane", "cambodgienne", "laotienne", "ouzbèke",
        "mongole", "tibétaine", "bengalie",
    ],
    "moyen-orient": [
        "libanaise", "syrienne", "turque", "israélienne", "palestinienne",
        "iranienne", "irakienne", "jordanienne", "yéménite", "arménienne",
        "géorgienne", "azérie", "kurde",
    ],
    "europe": [
        "française", "provençale", "basque", "corse", "italienne",
        "sicilienne", "toscane", "espagnole", "catalane", "portugaise",
        "grecque", "allemande", "autrichienne", "suisse", "belge",
        "néerlandaise", "britannique", "irlandaise", "suédoise", "danoise",
        "norvégienne", "finlandaise", "polonaise", "hongroise", "tchèque",
        "roumaine", "bulgare", "serbe", "croate", "russe", "ukrainienne",
    ],
    "afrique": [
        "marocaine", "algérienne", "tunisienne", "libyenne", "égyptienne",
        "sénégalaise", "ivoirienne", "malienne", "nigériane", "ghanéenne",
        "camerounaise", "congolaise", "éthiopienne", "érythréenne",
        "somalienne", "kenyane", "tanzanienne", "sud-africaine", "malgache",
        "réunionnaise", "mauricienne", "cap-verdienne",
    ],
    "amériques": [
        "mexicaine", "oaxaquenienne", "tex-mex", "cajun", "américaine",
        "québécoise", "cubaine", "jamaïcaine", "haïtienne", "portoricaine",
        "dominicaine", "péruvienne", "brésilienne", "argentine", "chilienne",
        "colombienne", "vénézuélienne", "bolivienne", "équatorienne",
        "uruguayenne", "guyanaise",
    ],
    "océanie": [
        "australienne", "néo-zélandaise", "hawaïenne", "polynésienne",
        "fidjienne",
    ],
}

# Où ranger une création: sert à l'export vers les fichiers de recettes.
CONTINENT_DE = {
    cuisine: continent
    for continent, cuisines in CUISINES.items()
    for cuisine in cuisines
}

# Le Moyen-Orient partage le fichier asie.json, comme dans le carnet.
FICHIER_DE = {"moyen-orient": "asie", "océanie": "ameriques"}


def toutes() -> list[str]:
    return [c for liste in CUISINES.values() for c in liste]


def continent_de(cuisine: str | None) -> str | None:
    """Le continent d'une cuisine, en tolérant les approximations.

    Le modèle écrit parfois "asiatique" ou "nord-africaine" au lieu d'un
    pays. On rattache ce qu'on peut plutôt que de perdre l'information.
    """
    if not cuisine:
        return None
    c = cuisine.strip().lower()
    if c in CONTINENT_DE:
        return CONTINENT_DE[c]
    if c in CUISINES:
        return c
    for continent in CUISINES:
        if continent.split("-")[0] in c or c in continent:
            return continent
    if "asiat" in c:
        return "asie"
    if "africa" in c or "afric" in c:
        return "afrique"
    if "europ" in c:
        return "europe"
    if "latino" in c or "améric" in c or "americ" in c:
        return "amériques"
    if "orient" in c or "levant" in c or "maghr" in c:
        return "moyen-orient"
    return None


def fichier_de(cuisine: str | None) -> str:
    """Le fichier de recettes où cette cuisine irait naturellement."""
    continent = continent_de(cuisine)
    if continent is None:
        return "monde"
    return FICHIER_DE.get(continent, continent.replace("é", "e"))


def pistes(recentes: list[str], combien: int = 5) -> tuple[str, list[str]]:
    """Tire un continent puis quelques cuisines dedans.

    Passer par un continent plutôt que par une liste plate change le
    résultat: en tirant au hasard dans l'ensemble, on retombe sans cesse
    sur les régions les plus fournies. Ici chaque continent a la même
    chance d'être choisi, et les continents récemment visités sont mis
    de côté.
    """
    vus = {continent_de(c) for c in recentes}
    vus.discard(None)

    candidats = [c for c in CUISINES if c not in vus] or list(CUISINES)
    continent = random.choice(candidats)
    liste = CUISINES[continent]
    return continent, random.sample(liste, min(combien, len(liste)))
