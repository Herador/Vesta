"""Contrôle de forme des recettes avant import.

    python -m outils.verifier_recettes recettes/
    python -m outils.verifier_recettes recettes/asie.json

Ne juge pas la cuisine, seulement la forme: un nom d'ingrédient doit
être un nom d'aliment, une unité doit être connue, un ingrédient doit
servir dans au moins une étape. C'est ce garde-fou qui permet d'ajouter
une recette sans repasser derrière soi.
"""

import json
import sys
import unicodedata
from pathlib import Path

from app.domaine.moteur import TAILLE, TRANSFORMATIONS, normaliser
from app.domaine import unites
from app.domaine.nutrition import cle_ciqual

CATEGORIES = {"plat", "petitdej", "collation", "defi"}
PARTIES = {"plat", "sauce", "marinade", "garniture", "accompagnement"}
UNITES = {"", "g", "kg", "ml", "cl", "l", "càs", "càc", "cas", "cac"}

# Terminaisons de participe passé: le signe qu'un ingrédient décrit une
# préparation au lieu de nommer un aliment.
PARTICIPES_PREPARATION = {
    "emince", "hache", "rape", "coupe", "cisele", "ecrase", "pele",
    "epluche", "egoutte", "dore", "grille", "revenu", "fondu", "battu",
    "mixe", "lave", "essore", "effeuille", "presse", "creuse", "farci",
}
MOTS_INTERDITS = {"en", "coupe", "coupé", "avec", "sans", "pour", "ou", "et"}

# Ce qu'on n'écrit jamais dans une liste d'ingrédients.
ASSAISONNEMENTS = {"sel", "poivre", "sel poivre", "poivre sel", "eau"}


# Des noms composés où un mot de taille ou de préparation appartient à
# l'aliment lui-même: "petits pois" n'est pas une taille de pois, et le
# fromage râpé s'achète déjà râpé.
_ADMIS = [
    "petits pois", "fromage râpé", "pois cassés", "crème fraîche",
    "tomates concassées", "lait concentré", "sucre glace", "amandes effilées",
    "noix de coco râpée", "gros sel", "poivre moulu", "coriandre moulue",
    "épinards hachés", "haricots coupés", "petits oignons",
]


def mot_nu(mot: str) -> str:
    """Un mot désaccentué et au singulier, sans autre traitement.

    On ne peut pas passer par normaliser() ici: elle supprime justement
    les mots qu'on cherche à repérer. "moyenne" et "émincés" en
    ressortaient vides, et n'étaient donc jamais signalés.
    """
    sans = unicodedata.normalize("NFD", mot.lower())
    sans = "".join(c for c in sans if unicodedata.category(c) != "Mn")
    sans = "".join(c for c in sans if c.isalnum())
    return sans[:-1] if len(sans) > 3 and sans[-1] in "sx" else sans


# La liste est écrite en français lisible, puis passée dans le même
# traitement que les noms contrôlés: sinon "petits pois" ne rencontrerait
# jamais "petit poi", et on chercherait longtemps pourquoi.
NOMS_ADMIS = {" ".join(mot_nu(m) for m in nom.lower().split()) for nom in _ADMIS}


def cle_negligeable(cle: str) -> bool:
    from app.domaine.nutrition import est_negligeable
    return est_negligeable(cle)


def charger(chemin: Path) -> list[tuple[Path, dict]]:
    fichiers = sorted(chemin.glob("*.json")) if chemin.is_dir() else [chemin]
    recettes = []
    for fichier in fichiers:
        contenu = json.loads(fichier.read_text(encoding="utf-8"))
        recettes += [(fichier, r) for r in contenu]
    return recettes


def verifier_ingredient(ing: dict) -> list[str]:
    soucis = []
    nom = ing.get("nom", "").strip()

    if not nom:
        return ["ingrédient sans nom"]

    mots = [mot_nu(m) for m in nom.lower().split()]

    # Un nom composé admis saute les contrôles de forme du libellé, mais
    # garde ceux de quantité et d'unité.
    if " ".join(mots) in NOMS_ADMIS:
        return controler_mesure(ing, nom)

    # Quatre mots sont permis quand le nom désigne une transformation:
    # "jus de citron vert" est un ingrédient à part entière. On regarde
    # le premier mot écrit, pas la clé normalisée: celle-ci peut avoir
    # remplacé "jus de citron vert" par un synonyme.
    limite = 4 if mots and mots[0] in TRANSFORMATIONS else 3
    if len(nom.split()) > limite:
        soucis.append(f"'{nom}': nom trop long, garde l'aliment nu")

    for brut, mot in zip(nom.lower().split(), mots):
        if mot in MOTS_INTERDITS and len(mots) > 2:
            soucis.append(f"'{nom}': '{brut}' décrit une préparation, à mettre dans l'étape")
            break
        if mot in TAILLE:
            soucis.append(f"'{nom}': '{brut}' est une taille ou une découpe, à mettre dans l'étape")
            break
    if len(mots) > 1 and mots[-1] in PARTICIPES_PREPARATION:
        soucis.append(f"'{nom}': '{nom.split()[-1]}' décrit une préparation, "
                      "à mettre dans l'étape")

    return soucis + controler_mesure(ing, nom)


def controler_mesure(ing: dict, nom: str) -> list[str]:
    """La quantité, l'unité et la partie: contrôlés dans tous les cas."""
    soucis = []
    if unites.normaliser_unite(ing.get("unite", "")) not in UNITES:
        soucis.append(f"'{nom}': unité inconnue '{ing.get('unite')}'")
    quantite = ing.get("quantite")
    if quantite is None or quantite <= 0:
        soucis.append(f"'{nom}': quantité manquante ou nulle")
    if ing.get("partie", "plat") not in PARTIES:
        soucis.append(f"'{nom}': partie inconnue '{ing.get('partie')}'")
    return soucis


# Les façons d'écrire une unité dans une phrase, et la famille visée.
UNITES_ECRITES = [
    (r"c\.?\s*à\s*soupe|cuill[eè]res?\s+à\s+soupe|càs", "volume", 15),
    (r"c\.?\s*à\s*caf[eé]|cuill[eè]res?\s+à\s+caf[eé]|càc", "volume", 5),
    (r"ml\b|millilitres?", "volume", 1),
    (r"cl\b|centilitres?", "volume", 10),
    (r"\bl\b|litres?", "volume", 1000),
    (r"\bg\b|grammes?", "masse", 1),
    (r"\bkg\b|kilos?", "masse", 1000),
]

# En dessous de ce rapport, on ne dit rien: une étape peut dire "un peu
# d'huile" sans chiffrer, ou n'employer qu'une partie de ce que la liste
# annonce. Au-delà, ce n'est plus une approximation mais une erreur
# d'unité: le cas rencontré valait dix fois la quantité voulue.
ECART_TOLERE = 5


def verifier_recette(r: dict) -> list[str]:
    soucis = []
    for champ in ("titre", "categorie", "portions_base", "temps_min",
                  "description", "ingredients", "etapes"):
        if not r.get(champ):
            soucis.append(f"champ manquant: {champ}")
    if soucis:
        return soucis

    if r["categorie"] not in CATEGORIES:
        soucis.append(f"catégorie inconnue: {r['categorie']}")
    if not 1 <= r["portions_base"] <= 12:
        soucis.append("portions_base hors limites")
    if len(r["etapes"]) < 3:
        soucis.append("moins de 3 étapes, la recette est probablement incomplète")

    for ing in r["ingredients"]:
        soucis += verifier_ingredient(ing)

    for i, etape in enumerate(r["etapes"], 1):
        if not etape.get("titre"):
            soucis.append(f"étape {i} sans titre")
        if len(etape.get("texte", "")) < 20:
            soucis.append(f"étape {i}: texte trop court")

    # Un ingrédient qui n'apparaît dans aucune étape est soit oublié dans
    # la préparation, soit en trop dans la liste. Les deux sont des bugs.
    # cle_ciqual et non normaliser: ce dernier est fait pour un libellé
    # isolé et tronque le texte à la première virgule.
    mots_etapes = set(cle_ciqual(" ".join(e.get("texte", "") for e in r["etapes"])).split())
    for ing in r["ingredients"]:
        cle = cle_ciqual(ing.get("nom", ""))
        if cle and not set(cle.split()) & mots_etapes:
            soucis.append(f"'{ing['nom']}' n'apparaît dans aucune étape")

    return soucis


def nettoyer_recette(r: dict) -> dict:
    """Rabote une recette venue du modèle avant de la contrôler.

    Le modèle respecte le format neuf fois sur dix; le dixième cas est
    une clé absente ou une valeur du mauvais type. On répare ce qui est
    réparable, verifier_recette refuse le reste.
    """
    propre = {
        "titre": str(r.get("titre", "")).strip(),
        "categorie": r.get("categorie") if r.get("categorie") in CATEGORIES else "plat",
        "cuisine": r.get("cuisine"),
        "portions_base": int(r.get("portions_base") or 2),
        "temps_min": int(r.get("temps_min") or 30),
        "description": str(r.get("description", "")).strip(),
        "note": str(r.get("note", "")).strip() or None,
        "ingredients": [],
        "etapes": [],
    }
    for i in r.get("ingredients", []):
        if not isinstance(i, dict) or not i.get("nom"):
            continue
        cle = normaliser(i["nom"])
        # Le sel et le poivre s'ajoutent au jugé, on ne les liste pas.
        if cle in ASSAISONNEMENTS:
            continue
        # Un condiment sans quantité est un geste, pas un ingrédient:
        # on le laisse dans les étapes et on le retire de la liste.
        if not i.get("quantite") and cle_negligeable(cle):
            continue
        propre["ingredients"].append({
            "nom": str(i["nom"]).strip(),
            "quantite": i.get("quantite"),
            # "1 gousse d'ail" devient "1 ail": récupérable, donc récupéré.
            "unite": unites.normaliser_unite(i.get("unite", "")),
            "partie": i.get("partie") if i.get("partie") in PARTIES else "plat",
            "essentiel": bool(i.get("essentiel", True)),
        })
    for e in r.get("etapes", []):
        if not isinstance(e, dict) or not e.get("texte"):
            continue
        secondes = e.get("secondes")
        propre["etapes"].append({
            "titre": str(e.get("titre") or "Étape").strip(),
            "texte": str(e["texte"]).strip(),
            "secondes": int(secondes) if isinstance(secondes, (int, float)) and secondes else None,
        })
    return propre


def verifier(chemin: Path) -> int:
    recettes = charger(chemin)
    titres, problemes = {}, 0

    for fichier, r in recettes:
        titre = r.get("titre", "(sans titre)")
        if titre in titres:
            print(f"  [{titre}] titre en double, déjà dans {titres[titre].name}")
            problemes += 1
        titres[titre] = fichier

        soucis = verifier_recette(r)
        if soucis:
            problemes += len(soucis)
            print(f"\n{titre} ({fichier.name})")
            for s in soucis:
                print(f"  - {s}")

    print(f"\n{len(recettes)} recettes contrôlées, {problemes} problèmes.")
    if not problemes:
        print("Format conforme, tu peux importer.")
    return problemes


if __name__ == "__main__":
    cible = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "donnees" / "recettes"
    if not cible.exists():
        raise SystemExit(f"{cible} introuvable.")
    sys.exit(1 if verifier(cible) else 0)
