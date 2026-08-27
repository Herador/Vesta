"""Le cycle d'un repas: démarrer, puis valider le compte rendu.

Le stock ne bouge qu'à la validation. Un repas en cours survit à la
fermeture de l'app: on cuisine quarante minutes, on pose le téléphone,
on y revient.
"""

from fastapi import APIRouter, HTTPException, Query

from app import base as bdd
from app.commun import aujourdhui, maintenant, stock_actif
from app.domaine import moteur, unites
from app.modeles import CompteRendu, RepasEntree
from app.routes.recettes import charger_recettes, recette_affichee

# Pas de prefix ici: les chemins portent déjà /api, ce qui les rend
# lisibles tels quels quand on cherche une route dans le code.
routeur = APIRouter()


def reporter_sur_les_autres(con, article: dict, quantite: float,
                            actifs: list[dict], retires: list[str]) -> float:
    """Épuise les autres paquets du même aliment et renvoie ce qui reste
    à prendre sur celui-ci.

    On garde le paquet visé pour la fin: c'est celui qui périme le plus
    tôt, et le compte rendu l'a annoncé comme entamé.
    """
    autres = [a for a in actifs
              if a["id"] != article["id"] and a["cle"] == article["cle"]
              and a["famille"] == article["famille"] and a["quantite"] is not None]
    autres.sort(key=lambda a: (a["date_limite"] is None, a["date_limite"] or ""))

    reste = quantite - article["quantite"]
    for autre in autres:
        if reste <= 0.001:
            break
        pris = min(reste, autre["quantite"])
        if pris >= autre["quantite"] - 0.001:
            con.execute("UPDATE stock SET consomme_le = ? WHERE id = ?",
                        (maintenant(), autre["id"]))
            retires.append(autre["nom"])
        else:
            con.execute("UPDATE stock SET quantite = ? WHERE id = ?",
                        (round(autre["quantite"] - pris, 2), autre["id"]))
        reste -= pris

    # Ce qui reste après les autres paquets revient sur celui d'origine,
    # qui sera vidé s'il n'y suffit pas.
    return article["quantite"] + max(reste, 0)


def somme_disponible(articles: list[dict], famille: str | None) -> float | None:
    """Ce qu'on a en tout de cet aliment, tous paquets confondus.

    None dès qu'un des paquets n'a pas de quantité connue: mieux vaut ne
    rien annoncer qu'un total faux.
    """
    if famille is None:
        return None
    total = 0.0
    for a in articles:
        if a["quantite"] is None or a["famille"] != famille:
            return None
        total += a["quantite"]
    return round(total, 2)


def preparer_lignes(con, recette: dict, portions: int) -> list[dict]:
    """Ce que la recette va prendre dans le stock, à l'échelle des portions.

    Quand la recette compte en grammes et le stock en pièces, on convertit
    via le poids moyen d'une pièce et on marque la ligne comme approximative.
    Quand la conversion est impossible, la quantité reste vide: l'app
    préfère te poser la question au compte rendu plutôt que d'inventer.
    """
    facteur = portions / recette["portions_base"]
    articles = stock_actif(con)
    lignes = []

    # La sauce soja peut figurer dans la marinade ET dans la sauce. Deux
    # lignes viseraient le même article du stock: on additionne d'abord.
    cumules: dict[str, dict] = {}
    for ing in recette["ingredients"]:
        deja = cumules.get(ing["cle"])
        if deja and deja["quantite"] is not None and ing["quantite"] is not None:
            deja["quantite"] += ing["quantite"]
        elif not deja:
            cumules[ing["cle"]] = dict(ing)

    for ing in cumules.values():
        candidats = [a for a in articles if moteur.correspond(ing["cle"], a["cle"])]
        if not candidats:
            continue
        # à ingrédient égal, on entame d'abord ce qui périme le plus tôt
        candidats.sort(key=lambda a: (a["date_limite"] is None,
                                      a["date_limite"] or ""))
        article = candidats[0]
        # Un article sans quantité connue, l'huile ou les épices, n'a pas
        # de famille: on garde alors celle de la recette pour au moins
        # afficher combien en mettre. Le décompte, lui, ne s'appliquera
        # pas, mais ce n'était déjà pas le cas.
        cible = article["famille"] or ing["famille"]
        besoin, approx = None, False
        if ing["quantite"] is not None and cible:
            besoin = ing["quantite"] * facteur
            if ing["famille"] != cible:
                besoin, approx = unites.convertir(besoin, ing["famille"],
                                                  cible, ing["cle"])
        # Deux paquets de riz sont un seul stock de riz: on annonce le
        # total, et le décompte enchaînera d'un paquet à l'autre.
        disponible = somme_disponible(candidats, cible)
        lignes.append({
            "stock_id": article["id"], "nom": article["nom"], "cle": article["cle"],
            "quantite": besoin, "famille": cible,
            "disponible": disponible, "paquets": len(candidats),
            "approx": approx, "improvise": False,
        })
    return lignes


def paquets_de(actifs: list[dict], cle: str, famille: str | None) -> dict:
    """Combien on a de cet aliment en tout, et sur combien de paquets."""
    memes = [a for a in actifs if a["cle"] == cle]
    return {"disponible": somme_disponible(memes, famille), "paquets": len(memes)}


def repas_complet(con, repas_id: int) -> dict:
    repas = con.execute("SELECT * FROM repas WHERE id = ?", (repas_id,)).fetchone()
    if repas is None:
        raise HTTPException(404, "Repas introuvable")
    lignes = con.execute("SELECT * FROM repas_ligne WHERE repas_id = ? ORDER BY id",
                         (repas_id,)).fetchall()

    # Le disponible se recalcule à la lecture plutôt que de dormir en
    # base: le stock a pu changer depuis, et une quantité périmée
    # afficherait plus que ce qu'on a vraiment.
    actifs = stock_actif(con)
    return {
        **dict(repas),
        "lignes": [{
            **dict(l),
            **paquets_de(actifs, l["cle"], l["famille"]),
            "affichage": unites.afficher(l["quantite"], l["famille"], l["nom"]),
            "approx": bool(l["approx"]), "improvise": bool(l["improvise"]),
        } for l in lignes],
    }


@routeur.post("/api/repas", status_code=201, tags=["Repas"], summary="Démarrer un repas")
def commencer_repas(entree: RepasEntree):
    """Démarre la cuisine. Rien n'est décompté à ce stade.

    Le repas reste en cours tant qu'il n'est pas validé, ce qui lui permet
    de survivre à la fermeture de l'app pendant que tu cuisines.
    """
    with bdd.base() as con:
        trouvees = charger_recettes(con, entree.recette_id)
        if not trouvees:
            raise HTTPException(404, "Recette introuvable")
        recette = trouvees[0]

        en_cours = con.execute(
            "SELECT id FROM repas WHERE statut = 'en_cours'"
        ).fetchone()
        if en_cours:
            raise HTTPException(409, f"Un repas est déjà en cours (id {en_cours['id']})")

        cur = con.execute(
            """INSERT INTO repas (recette_id, titre, portions, statut, commence_le)
               VALUES (?, ?, ?, 'en_cours', ?)""",
            (recette["id"], recette["titre"], entree.portions, maintenant()),
        )
        for ligne in preparer_lignes(con, recette, entree.portions):
            con.execute(
                """INSERT INTO repas_ligne
                   (repas_id, stock_id, nom, cle, quantite, famille, approx, improvise)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
                (cur.lastrowid, ligne["stock_id"], ligne["nom"], ligne["cle"],
                 ligne["quantite"], ligne["famille"], int(ligne["approx"])),
            )
        return {**repas_complet(con, cur.lastrowid),
                "recette": recette_affichee(recette, entree.portions)}


@routeur.get("/api/repas/en-cours", tags=["Repas"], summary="Reprendre le repas en cours")
def repas_en_cours():
    with bdd.base() as con:
        ligne = con.execute("SELECT id FROM repas WHERE statut = 'en_cours'").fetchone()
        if ligne is None:
            return None
        return repas_complet(con, ligne["id"])


@routeur.delete("/api/repas/{repas_id}", status_code=204, tags=["Repas"], summary="Abandonner sans décompter")
def abandonner_repas(repas_id: int):
    """Annule sans rien décompter."""
    with bdd.base() as con:
        if con.execute("DELETE FROM repas WHERE id = ?", (repas_id,)).rowcount == 0:
            raise HTTPException(404, "Repas introuvable")


@routeur.post("/api/repas/{repas_id}/terminer", tags=["Repas"], summary="Valider le compte rendu et décompter")
def terminer_repas(repas_id: int, rendu: CompteRendu):
    """Le compte rendu: c'est ici, et seulement ici, que le stock bouge.

    Les lignes envoyées remplacent celles qui avaient été prévues, ce qui
    permet de corriger une quantité comme d'ajouter ce que tu as improvisé.
    """
    with bdd.base() as con:
        repas = con.execute(
            "SELECT * FROM repas WHERE id = ? AND statut = 'en_cours'", (repas_id,)
        ).fetchone()
        if repas is None:
            raise HTTPException(404, "Aucun repas en cours avec cet identifiant")

        con.execute("DELETE FROM repas_ligne WHERE repas_id = ?", (repas_id,))
        retires, ajustes, ignores = [], [], []

        articles_actifs = stock_actif(con)

        for ligne in rendu.lignes:
            cle = moteur.normaliser(ligne.nom)
            article = None

            if ligne.stock_id:
                article = con.execute(
                    "SELECT * FROM stock WHERE id = ? AND consomme_le IS NULL",
                    (ligne.stock_id,),
                ).fetchone()
                if article is None:
                    raise HTTPException(
                        404, f"L'article {ligne.stock_id} n'est plus dans le stock actif. "
                             "Rien n'a été décompté.")
            else:
                # Improviser avec quelque chose qu'on a déjà doit décompter.
                # On retrouve l'article par son nom, sinon la ligne resterait
                # hors stock alors que le poivron est bien dans le frigo.
                correspondants = [a for a in articles_actifs
                                  if moteur.correspond(cle, a["cle"])]
                if correspondants:
                    article = min(correspondants,
                                  key=lambda a: (a["date_limite"] is None,
                                                 a["date_limite"] or ""))

            quantite, famille = unites.vers_base(ligne.quantite, ligne.unite)

            if article is None:
                # improvisé et absent du stock: on garde la trace, rien à décompter
                con.execute(
                    """INSERT INTO repas_ligne
                       (repas_id, stock_id, nom, cle, quantite, famille, approx, improvise)
                       VALUES (?, NULL, ?, ?, ?, ?, 0, 1)""",
                    (repas_id, ligne.nom, cle, quantite, famille),
                )
                ignores.append(ligne.nom)
                continue

            if famille and article["famille"] and famille != article["famille"]:
                quantite, _ = unites.convertir(quantite, famille, article["famille"], cle)
                famille = article["famille"]

            # Un article sans quantité connue (les épices, l'huile) ne
            # sort du stock que si tu le dis: on ignore combien il en
            # restait, donc on ne peut pas conclure qu'il est fini.
            if article["quantite"] is None:
                vide = ligne.vider
            else:
                vide = (ligne.vider or quantite is None
                        or quantite >= article["quantite"] - 0.001)

            # Ce qui dépasse ce paquet part sur les suivants: deux boîtes
            # de tomates entamées sont un seul stock de tomates, et on ne
            # peut pas exiger de savoir laquelle on a ouverte.
            if (not ligne.vider and quantite is not None
                    and article["quantite"] is not None
                    and quantite > article["quantite"] + 0.001):
                quantite = reporter_sur_les_autres(
                    con, article, quantite, articles_actifs, retires)

            if vide:
                con.execute("UPDATE stock SET consomme_le = ? WHERE id = ?",
                            (maintenant(), article["id"]))
                retires.append(article["nom"])
            elif article["quantite"] is None or quantite is None:
                pass  # rien à décompter, l'article reste tel quel
            else:
                reste = article["quantite"] - quantite
                con.execute("UPDATE stock SET quantite = ? WHERE id = ?",
                            (reste, article["id"]))
                ajustes.append(f"{article['nom']}: "
                               f"{unites.afficher(reste, article['famille'], article['nom'])}")

            con.execute(
                """INSERT INTO repas_ligne
                   (repas_id, stock_id, nom, cle, quantite, famille, approx, improvise)
                   VALUES (?, ?, ?, ?, ?, ?, 0, 0)""",
                (repas_id, article["id"], article["nom"], cle, quantite,
                 famille or article["famille"]),
            )

        con.execute(
            "UPDATE repas SET statut = 'termine', termine_le = ?, note = ? WHERE id = ?",
            (maintenant(), rendu.note, repas_id),
        )
        if repas["recette_id"]:
            con.execute("UPDATE recette SET derniere_fois = ? WHERE id = ?",
                        (aujourdhui().isoformat(), repas["recette_id"]))

        cles_du_repas = {l["cle"] for l in con.execute(
            "SELECT cle FROM repas_ligne WHERE repas_id = ?", (repas_id,)).fetchall()}
        connus = {l["cle"] for l in con.execute(
            "SELECT cle FROM aliment").fetchall()}

        essai = None
        if repas["recette_id"]:
            l = con.execute("SELECT id, titre, essai FROM recette WHERE id = ?",
                            (repas["recette_id"],)).fetchone()
            if l and l["essai"]:
                essai = {"id": l["id"], "titre": l["titre"]}

        return {"repas": repas_complet(con, repas_id), "retires": retires,
                "ajustes": ajustes, "hors_stock": ignores, "a_decider": essai,
                # liaison paresseuse: on ne demande que pour ce qui a servi
                "a_lier": sorted(cles_du_repas - connus)}


@routeur.get("/api/repas", tags=["Repas"], summary="Historique des repas")
def historique(limite: int = Query(20, ge=1, le=200)):
    with bdd.base() as con:
        lignes = con.execute(
            "SELECT * FROM repas WHERE statut = 'termine' ORDER BY termine_le DESC LIMIT ?",
            (limite,),
        ).fetchall()
        return [repas_complet(con, l["id"]) for l in lignes]
