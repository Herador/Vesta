"""Le stock: ce qu'il y a dans le frigo, le congélateur et le placard."""

from datetime import date

from fastapi import APIRouter, HTTPException

from app import base as bdd
from app.commun import aujourdhui, en_sortie, maintenant
from app.domaine import conservation, moteur, unites
from app.modeles import (Consommation, Lieu, StockEntree, StockModif,
                         StockSortie)
from app.routes.aliments import lier_ciqual

# Pas de prefix ici: les chemins portent déjà /api, ce qui les rend
# lisibles tels quels quand on cherche une route dans le code.
routeur = APIRouter()


@routeur.get("/api/stock", response_model=list[StockSortie], tags=["Stock"], summary="Lister le stock, trié par urgence")
def lister_stock(lieu: Lieu | None = None, a_sauver: bool = False):
    """Le stock encore présent, trié par urgence.

    SQLite place les NULL en premier, ce qui ferait remonter les articles
    sans date comme s'ils étaient les plus urgents. D'où le
    `date_limite IS NULL` en tête du ORDER BY.
    """
    requete = "SELECT * FROM stock WHERE consomme_le IS NULL"
    params: list = []
    if lieu:
        requete += " AND lieu = ?"
        params.append(lieu)
    requete += " ORDER BY date_limite IS NULL, date_limite, nom COLLATE NOCASE"

    with bdd.base() as con:
        articles = [en_sortie(l) for l in con.execute(requete, params).fetchall()]
    if a_sauver:
        articles = [a for a in articles
                    if a.jours_restants is not None and a.jours_restants <= 4]
    return articles


@routeur.post("/api/stock", response_model=StockSortie, status_code=201, tags=["Stock"], summary="Ajouter un article")
def ajouter(article: StockEntree):
    quantite, famille = unites.vers_base(article.quantite, article.unite)
    cle = moteur.normaliser(article.nom)

    # Sans date saisie, on en propose une d'après l'aliment et son
    # rangement: un brocoli au frigo tient six jours, une pomme de terre
    # au placard un mois. Mieux vaut un ordre de grandeur que rien.
    limite, estimee = article.date_limite, False
    if limite is None:
        limite = conservation.date_estimee(cle, article.lieu, aujourdhui())
        estimee = limite is not None

    with bdd.base() as con:
        # Un code barre encore inconnu ouvre sa fiche produit. Le scan
        # l'enrichira ensuite; sans ça, la clé étrangère faisait tomber
        # l'insertion en erreur serveur.
        if article.code_barre:
            con.execute(
                """INSERT OR IGNORE INTO produit (code_barre, nom, vu_le)
                   VALUES (?, ?, ?)""",
                (article.code_barre, article.nom.strip(), maintenant()),
            )
        cur = con.execute(
            """INSERT INTO stock (nom, cle, code_barre, quantite, famille, lieu,
                                  date_limite, date_estimee, ajoute_le)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (article.nom.strip(), cle, article.code_barre,
             quantite, famille, article.lieu,
             limite.isoformat() if limite else None, int(estimee), maintenant()),
        )
        if article.code_ciqual:
            lier_ciqual(con, moteur.normaliser(article.nom), article.code_ciqual)
        ligne = con.execute("SELECT * FROM stock WHERE id = ?", (cur.lastrowid,)).fetchone()
    return en_sortie(ligne)


@routeur.patch("/api/stock/{article_id}", response_model=StockSortie, tags=["Stock"], summary="Modifier un article")
def modifier(article_id: int, modif: StockModif):
    champs = modif.model_dump(exclude_unset=True)
    if not champs:
        raise HTTPException(400, "Rien à modifier")

    with bdd.base() as con:
        ligne = con.execute(
            "SELECT * FROM stock WHERE id = ? AND consomme_le IS NULL", (article_id,)
        ).fetchone()
        if ligne is None:
            raise HTTPException(404, "Article introuvable dans le stock actif")

        if "quantite" in champs:
            unite = champs.pop("unite", None) or unites.REFERENCE.get(ligne["famille"], "")
            champs["quantite"], champs["famille"] = unites.vers_base(champs["quantite"], unite)
        champs.pop("unite", None)
        if "nom" in champs:
            champs["cle"] = moteur.normaliser(champs["nom"])
        if isinstance(champs.get("date_limite"), date):
            champs["date_limite"] = champs["date_limite"].isoformat()
            champs["date_estimee"] = 0   # une date saisie ne se recalcule plus

        # Changer de rangement change la durée de garde.
        #
        # Passer au congélateur ou en sortir recalcule toujours, même
        # quand la date vient de l'emballage: congeler suspend l'horloge,
        # décongeler la relance pour quelques jours seulement. Entre le
        # frigo et le placard, en revanche, une date lue sur le paquet
        # reste la référence et n'est pas touchée.
        bascule_congelo = "congelo" in (champs.get("lieu"), ligne["lieu"])
        if champs.get("lieu") and champs["lieu"] != ligne["lieu"] \
                and "date_limite" not in champs \
                and (ligne["date_estimee"] or bascule_congelo):
            nouvelle = conservation.redater(
                champs.get("cle", ligne["cle"]), champs["lieu"],
                date.fromisoformat(ligne["ajoute_le"][:10]),
                date.fromisoformat(ligne["date_limite"]) if ligne["date_limite"] else None)
            if nouvelle:
                champs["date_limite"] = nouvelle.isoformat()
                champs["date_estimee"] = 1

        colonnes = ", ".join(f"{c} = ?" for c in champs)
        con.execute(f"UPDATE stock SET {colonnes} WHERE id = ?",
                    (*champs.values(), article_id))
        ligne = con.execute("SELECT * FROM stock WHERE id = ?", (article_id,)).fetchone()
    return en_sortie(ligne)


@routeur.post("/api/stock/{article_id}/consomme", response_model=StockSortie | None, tags=["Stock"], summary="Consommer, entamer ou jeter un article")
def consommer(article_id: int, info: Consommation):
    """Sort un article du stock, ou met à jour ce qu'il en reste."""
    with bdd.base() as con:
        ligne = con.execute(
            "SELECT * FROM stock WHERE id = ? AND consomme_le IS NULL", (article_id,)
        ).fetchone()
        if ligne is None:
            raise HTTPException(404, "Article introuvable dans le stock actif")

        if info.reste is not None and info.reste > 0:
            unite = info.unite or unites.REFERENCE.get(ligne["famille"], "")
            reste, famille = unites.vers_base(info.reste, unite)
            con.execute("UPDATE stock SET quantite = ?, famille = ? WHERE id = ?",
                        (reste, famille or ligne["famille"], article_id))
            return en_sortie(con.execute("SELECT * FROM stock WHERE id = ?",
                                         (article_id,)).fetchone())

        con.execute("UPDATE stock SET consomme_le = ?, jete = ? WHERE id = ?",
                    (maintenant(), int(info.jete), article_id))
    return None


@routeur.delete("/api/stock/{article_id}", status_code=204, tags=["Stock"], summary="Supprimer une saisie erronée")
def supprimer(article_id: int):
    """Suppression sèche, pour une erreur de saisie uniquement.

    Un aliment vraiment mangé passe par /consomme, qui garde l'historique.
    """
    with bdd.base() as con:
        if con.execute("DELETE FROM stock WHERE id = ?", (article_id,)).rowcount == 0:
            raise HTTPException(404, "Article introuvable")
