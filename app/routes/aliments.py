"""Le rattachement des aliments aux fiches CIQUAL de l'ANSES.

À faire une fois par aliment: ensuite c'est acquis. Les valeurs
nutritionnelles sont calculées depuis ces fiches, jamais générées.
"""

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query

from app import base as bdd
from app.commun import aujourdhui
from app.domaine import moteur
from app.modeles import Entree, Field

# Pas de prefix ici: les chemins portent déjà /api, ce qui les rend
# lisibles tels quels quand on cherche une route dans le code.
routeur = APIRouter()


from app.domaine import nutrition


# ---------------------------------------------------------------- apports

class AlimentEntree(Entree):
    """Associe un de tes aliments à une composition pour 100 g.

    Deux façons: renvoyer un code CIQUAL, ou saisir les valeurs à la main
    quand rien ne correspond dans la table.
    """
    code_ciqual: str | None = None
    libelle: str | None = None
    ignorer: bool = False  # eau, sel, épices: compté pour zéro
    kcal: float | None = Field(default=None, ge=0)
    proteines: float | None = Field(default=None, ge=0)
    glucides: float | None = Field(default=None, ge=0)
    sucres: float | None = Field(default=None, ge=0)
    lipides: float | None = Field(default=None, ge=0)
    satures: float | None = Field(default=None, ge=0)
    fibres: float | None = Field(default=None, ge=0)
    sel: float | None = Field(default=None, ge=0)


def compositions_pour(con, cles: set[str]) -> dict[str, dict]:
    if not cles:
        return {}
    trous = ",".join("?" * len(cles))
    lignes = con.execute(
        f"SELECT * FROM aliment WHERE cle IN ({trous})", tuple(cles)
    ).fetchall()
    return {l["cle"]: dict(l) for l in lignes}


def hors_stock(ingredients: list[dict], articles: list[dict]) -> list[dict]:
    """Les ingrédients d'une recette qu'on ne trouve pas dans le stock."""
    cles = [a["cle"] for a in articles]
    return [i for i in ingredients
            if not any(moteur.correspond(moteur.normaliser(i["nom"]), c)
                       for c in cles)]


def trouver_exclus(ingredients: list[dict], liste: str) -> list[str]:
    """Les ingrédients d'une recette qui figurent parmi les exclus.

    Comparaison sur les clés normalisées, donc "pâte de crevettes" est
    reconnue par l'entrée "crevette" et "filet de cabillaud" par
    "cabillaud", sans avoir à énumérer toutes les formulations.

    Une entrée préfixée d'un tiret est une exception qui l'emporte:
    "huître, -sauce d'huître" écarte le mollusque sans écarter le
    condiment, qui n'en contient qu'un extrait.
    """
    exclus, exceptions = [], []
    for entree in liste.split(","):
        entree = entree.strip()
        if not entree:
            continue
        (exceptions if entree.startswith("-") else exclus).append(
            moteur.normaliser(entree.lstrip("-")))

    trouves = []
    for ing in ingredients:
        mots = set(moteur.normaliser(ing["nom"]).split())
        if any(e and set(e.split()) <= mots for e in exceptions):
            continue
        for cle in exclus:
            if cle and set(cle.split()) <= mots:
                trouves.append(ing["nom"])
                break
    return trouves


def lier_ciqual(con, cle: str, code: str, confirme: int = 1) -> dict | None:
    """Associe un de tes aliments à une fiche CIQUAL."""
    fiche = con.execute("SELECT * FROM ciqual WHERE code = ?", (code,)).fetchone()
    if fiche is None:
        return None
    con.execute(
        """INSERT OR REPLACE INTO aliment
           (cle, libelle, source, reference, confirme, kcal, proteines,
            glucides, sucres, lipides, satures, fibres, sel)
           VALUES (?, ?, 'ciqual', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (cle, fiche["nom"], fiche["code"], confirme,
         *[fiche[n] for n in nutrition.NUTRIMENTS]),
    )
    return dict(fiche)


def marquer_negligeable(con, cle: str) -> None:
    con.execute(
        """INSERT OR REPLACE INTO aliment
           (cle, libelle, source, reference, confirme, kcal, proteines,
            glucides, sucres, lipides, satures, fibres, sel)
           VALUES (?, 'Non compté', 'ignore', NULL, 1, 0, 0, 0, 0, 0, 0, 0, 0)""",
        (cle,),
    )


def toutes_les_fiches(con) -> list[dict]:
    return [dict(f) for f in con.execute("SELECT * FROM ciqual").fetchall()]


def cles_utilisees(con, avec_carnet: bool = False) -> dict[str, dict]:
    """Les aliments qui te concernent, avec leur origine et leur libellé.

    Le libellé complet est indispensable pour la recherche: la clé de
    "Crème 12%" est réduite à "creme", ce qui ne retrouverait jamais la
    bonne fiche. On cherche donc sur le nom tel que tu l'as écrit.

    Le stock et les repas passent avant le carnet: ce que tu as mangé
    compte plus que ce qu'une recette pourrait un jour demander.
    """
    sources = [
        ("SELECT cle, nom FROM stock WHERE consomme_le IS NULL ORDER BY id", "stock"),
        ("SELECT cle, nom FROM repas_ligne ORDER BY id", "repas"),
    ]
    if avec_carnet:
        # Le carnet en premier pour que le stock puisse écraser son
        # libellé: "filet de poulet en lanières" est de la prose, alors
        # que "poulet" dans ton frigo est un nom d'aliment.
        # essentiel = 1 seulement: inutile de faire associer une pincée
        # de muscade présente dans une seule recette.
        sources.insert(0, ("SELECT cle, nom FROM ingredient_recette WHERE essentiel = 1",
                           "carnet"))

    trouves: dict[str, dict] = {}
    for requete, origine in sources:
        for l in con.execute(requete).fetchall():
            if nutrition.negligeable(l["cle"]):
                continue
            trouves[l["cle"]] = {"origine": origine, "nom": l["nom"]}
    return trouves


@routeur.get("/api/ciqual", tags=["Aliments CIQUAL"], summary="Autocomplétion CIQUAL à la saisie")
def autocompletion(q: str = Query(min_length=2), limite: int = Query(6, ge=1, le=20)):
    """Suggestions CIQUAL pendant la saisie d'un article du stock."""
    with bdd.base() as con:
        fiches = toutes_les_fiches(con)
    if not fiches:
        raise HTTPException(409, "Table CIQUAL non importée. "
                                 "Lance python importer_ciqual.py")
    return [{"code": f["code"], "nom": f["nom"], "groupe": f["groupe"],
             "kcal": f["kcal"], "transforme": f["transforme"]}
            for f in nutrition.chercher(fiches, q, limite)]


@routeur.get("/api/aliments/a-confirmer", tags=["Aliments CIQUAL"], summary="Ce qu'il reste à rattacher")
def a_confirmer(limite: int = Query(30, ge=1, le=200),
                carnet: bool = Query(False, description="inclure les ingrédients du carnet jamais cuisinés")):
    """La file d'attente: ce qui n'est pas lié, ou lié sans confirmation.

    Chaque entrée arrive avec ses trois meilleurs candidats, pour que la
    décision se prenne en un geste.
    """
    with bdd.base() as con:
        fiches = toutes_les_fiches(con)
        origines = cles_utilisees(con, carnet)
        connus = {l["cle"]: dict(l) for l in
                  con.execute("SELECT * FROM aliment").fetchall()}

    ordre = {"repas": 0, "stock": 1, "carnet": 2}
    en_attente = [(cle, info) for cle, info in origines.items()
                  if (cle not in connus or not connus[cle]["confirme"])
                  and not nutrition.est_negligeable(cle)]
    en_attente.sort(key=lambda x: (ordre.get(x[1]["origine"], 3), x[0]))

    return [{
        "cle": cle,
        "nom": info["nom"],
        "origine": info["origine"],
        "actuel": connus.get(cle),
        "propositions": nutrition.chercher_large(fiches, info["nom"], cle, 3),
    } for cle, info in en_attente[:limite]]


@routeur.post("/api/aliments/tout-lier", tags=["Aliments CIQUAL"], summary="Rattacher tout ce qui est sûr")
def tout_lier(carnet: bool = Query(False), refaire: bool = Query(False,
              description="recalculer aussi les liaisons non confirmées")):
    """Le bouton qui traite la file d'un coup.

    Ne lie que ce qui est sûr. Un aliment dont la meilleure fiche est un
    produit transformé reste en attente: "saumon" ne doit jamais devenir
    "saumon fumé" sans que tu l'aies voulu.
    """
    with bdd.base() as con:
        fiches = toutes_les_fiches(con)
        if not fiches:
            raise HTTPException(409, "Table CIQUAL non importée.")
        origines = cles_utilisees(con, carnet)
        garde = "" if refaire else " OR confirme = 0"
        connus = {l["cle"] for l in con.execute(
            f"SELECT cle FROM aliment WHERE confirme = 1{garde}").fetchall()}

        lies, douteux, orphelins, ignores = [], [], [], []
        for cle in sorted(set(origines) - connus):
            if nutrition.est_negligeable(cle):
                marquer_negligeable(con, cle)
                ignores.append(cle)
                continue
            trouvees = nutrition.chercher_large(fiches, origines[cle]["nom"], cle, 1)
            if not trouvees:
                orphelins.append(cle)
            elif trouvees[0]["transforme"]:
                douteux.append({"cle": cle, "propose": trouvees[0]["nom"]})
            else:
                lier_ciqual(con, cle, trouvees[0]["code"], confirme=0)
                lies.append({"cle": cle, "vers": trouvees[0]["nom"]})

    return {"lies": lies, "a_trancher": douteux, "non_comptes": ignores,
            "sans_correspondance": orphelins}


@routeur.post("/api/aliments/tout-confirmer", tags=["Aliments CIQUAL"], summary="Valider les rattachements automatiques")
def tout_confirmer():
    """Valide d'un coup tous les rapprochements automatiques.

    À utiliser après avoir relu la file: les rapprochements restent
    marqués non confirmés tant que tu ne les as pas vus, mais les
    reconfirmer un par un n'aurait aucun intérêt une fois relus.
    """
    with bdd.base() as con:
        n = con.execute("UPDATE aliment SET confirme = 1 WHERE confirme = 0").rowcount
    return {"confirmes": n}


@routeur.get("/api/aliments", tags=["Aliments CIQUAL"], summary="Lister les rattachements connus")
def lister_aliments(a_confirmer: bool = False):
    """Les associations connues entre tes aliments et la table CIQUAL."""
    requete = "SELECT * FROM aliment"
    if a_confirmer:
        requete += " WHERE confirme = 0"
    with bdd.base() as con:
        return [dict(l) for l in con.execute(requete + " ORDER BY cle").fetchall()]


@routeur.get("/api/aliments/recherche", tags=["Aliments CIQUAL"], summary="Chercher une fiche CIQUAL")
def rechercher_aliment(q: str = Query(min_length=2), limite: int = Query(8, ge=1, le=30)):
    """Cherche dans CIQUAL. Sert à corriger un rapprochement automatique."""
    with bdd.base() as con:
        fiches = [dict(f) for f in con.execute(
            "SELECT code, nom, cle, groupe, kcal, proteines, glucides, sucres, "
            "lipides, satures, fibres, sel FROM ciqual"
        ).fetchall()]
    if not fiches:
        raise HTTPException(409, "La table CIQUAL n'est pas importée. "
                                 "Lance python -m outils.importer_ciqual")

    trouvees = nutrition.chercher(fiches, q, limite)
    if trouvees:
        return trouvees

    # La recherche exacte veut tous les mots, ce qui ne pardonne rien:
    # "yaourt grec" ne rencontre pas "Yaourt à la grecque". Plutôt que de
    # renvoyer une page vide, on retente sur le mot le plus significatif.
    mots = sorted(q.split(), key=len, reverse=True)
    for mot in mots[:2]:
        if len(mot) >= 4:
            trouvees = nutrition.chercher(fiches, mot, limite)
            if trouvees:
                return trouvees
    return []


@routeur.put("/api/aliments/{cle}", tags=["Aliments CIQUAL"], summary="Rattacher un aliment à une fiche")
def associer_aliment(cle: str, entree: AlimentEntree):
    with bdd.base() as con:
        if entree.code_ciqual:
            fiche = con.execute("SELECT * FROM ciqual WHERE code = ?",
                                (entree.code_ciqual,)).fetchone()
            if fiche is None:
                raise HTTPException(404, "Code CIQUAL inconnu")
            valeurs = [fiche[n] for n in nutrition.NUTRIMENTS]
            libelle, source, reference = fiche["nom"], "ciqual", fiche["code"]
        elif entree.ignorer:
            valeurs = [0.0] * len(nutrition.NUTRIMENTS)
            libelle, source, reference = "Non compté", "ignore", None
        else:
            valeurs = [getattr(entree, n) for n in nutrition.NUTRIMENTS]
            if all(v is None for v in valeurs):
                raise HTTPException(400, "Donne un code CIQUAL, des valeurs, ou ignorer")
            libelle, source, reference = entree.libelle or cle, "manuel", None

        con.execute(
            """INSERT OR REPLACE INTO aliment
               (cle, libelle, source, reference, confirme, kcal, proteines,
                glucides, sucres, lipides, satures, fibres, sel)
               VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (cle, libelle, source, reference, *valeurs),
        )
        return dict(con.execute("SELECT * FROM aliment WHERE cle = ?", (cle,)).fetchone())


@routeur.get("/api/recettes/{recette_id}/apports", tags=["Apports"],
             summary="Apports d'une recette")
def apports_recette(recette_id: int, portions: int | None = Query(None, ge=1, le=12)):
    """Ce que vaut une assiette de cette recette, par personne.

    Calculé depuis les ingrédients, à l'échelle demandée. Vaut pour les
    recettes du carnet comme pour celles que l'assistant vient
    d'inventer: les unes et les autres ont des ingrédients et des
    quantités, c'est tout ce qu'il faut.
    """
    from app.routes.recettes import charger_recettes, recette_affichee

    with bdd.base() as con:
        trouvees = charger_recettes(con, recette_id)
        if not trouvees:
            raise HTTPException(404, "Recette introuvable")
        recette = recette_affichee(trouvees[0], portions)
        compositions = compositions_pour(con, {i["cle"] for i in recette["ingredients"]})

    calcul = nutrition.apports(recette["ingredients"], compositions,
                               recette["portions"])
    return {"recette": {"id": recette_id, "titre": recette["titre"],
                        "portions": recette["portions"]},
            **calcul}


@routeur.get("/api/repas/{repas_id}/apports", tags=["Apports"], summary="Apports d'un repas")
def apports_repas(repas_id: int):
    """Les apports d'un repas, avec ce qui n'a pas pu être compté."""
    with bdd.base() as con:
        repas = con.execute("SELECT * FROM repas WHERE id = ?", (repas_id,)).fetchone()
        if repas is None:
            raise HTTPException(404, "Repas introuvable")
        lignes = [dict(l) for l in con.execute(
            "SELECT * FROM repas_ligne WHERE repas_id = ?", (repas_id,)
        ).fetchall()]
        compositions = compositions_pour(con, {l["cle"] for l in lignes})

    return {"repas": {"id": repas["id"], "titre": repas["titre"],
                      "portions": repas["portions"], "termine_le": repas["termine_le"]},
            **nutrition.apports(lignes, compositions, repas["portions"])}


@routeur.get("/api/apports", tags=["Apports"], summary="Tendances sur une période")
def apports_periode(jours: int = Query(7, ge=1, le=90)):
    """Les tendances sur une période, par personne et par jour.

    Volontairement présenté en moyennes et en variété plutôt qu'en score
    du jour: les quantités sont estimées, donc l'échelle qui a du sens
    est la semaine, pas le repas isolé.
    """
    depuis = (aujourdhui() - timedelta(days=jours - 1)).isoformat()

    with bdd.base() as con:
        repas = con.execute(
            "SELECT * FROM repas WHERE statut = 'termine' AND termine_le >= ? "
            "ORDER BY termine_le", (depuis,),
        ).fetchall()
        if not repas:
            return {"jours": jours, "repas": 0,
                    "message": "Aucun repas enregistré sur la période."}

        ids = [r["id"] for r in repas]
        trous = ",".join("?" * len(ids))
        toutes = [dict(l) for l in con.execute(
            f"SELECT * FROM repas_ligne WHERE repas_id IN ({trous})", ids
        ).fetchall()]
        compositions = compositions_pour(con, {l["cle"] for l in toutes})

    par_repas, ignores, aliments = [], [], {}
    cumul = {n: 0.0 for n in nutrition.NUTRIMENTS}

    for r in repas:
        lignes = [l for l in toutes if l["repas_id"] == r["id"]]
        calcul = nutrition.apports(lignes, compositions, r["portions"])
        for n in nutrition.NUTRIMENTS:
            cumul[n] += calcul["par_personne"][n]
        ignores += [i["nom"] for i in calcul["couverture"]["ignores"]]
        for l in lignes:
            aliments[l["nom"]] = aliments.get(l["nom"], 0) + 1
        par_repas.append({
            "id": r["id"], "titre": r["titre"], "termine_le": r["termine_le"],
            "par_personne": calcul["par_personne"],
            "complet": calcul["couverture"]["complet"],
        })

    return {
        "jours": jours,
        "repas": len(repas),
        "moyenne_par_repas": {n: round(v / len(repas), 1) for n, v in cumul.items()},
        "moyenne_par_jour": {n: round(v / jours, 1) for n, v in cumul.items()},
        "variete": {
            "aliments_distincts": len(aliments),
            "les_plus_frequents": sorted(aliments.items(), key=lambda x: -x[1])[:8],
        },
        "non_comptes": sorted(set(ignores)),
        "detail": par_repas,
    }
