"""Ce que plusieurs routeurs partagent.

Volontairement maigre: dès qu'une fonction ne sert qu'à un seul
routeur, elle vit dans ce routeur.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app import base as bdd
from app.modeles import StockSortie
from app.domaine import unites

try:
    # Sur Linux et Mac, la base des fuseaux vient du système.
    # Sur Windows elle n'existe pas: il faut le paquet tzdata.
    FUSEAU = ZoneInfo("Europe/Paris")
except Exception:
    FUSEAU = None


def horloge() -> datetime:
    """L'heure de Paris, ou à défaut l'heure locale de la machine.

    Un Raspberry Pi tourne souvent en UTC. Sans ce fuseau, tout ce qui
    est ajouté entre minuit et deux heures du matin serait daté de la
    veille.
    """
    return datetime.now(FUSEAU) if FUSEAU else datetime.now()


def aujourdhui() -> date:
    return horloge().date()


def maintenant() -> str:
    return horloge().isoformat(timespec="seconds")


def etat_de(jours: int | None) -> str:
    if jours is None:
        return "sans_date"
    if jours <= 1:
        return "urgent"
    if jours <= 4:
        return "bientot"
    return "frais"


def en_sortie(ligne) -> StockSortie:
    limite = date.fromisoformat(ligne["date_limite"]) if ligne["date_limite"] else None
    jours = (limite - aujourdhui()).days if limite else None
    return StockSortie(
        id=ligne["id"], nom=ligne["nom"], cle=ligne["cle"],
        code_barre=ligne["code_barre"], quantite=ligne["quantite"],
        famille=ligne["famille"],
        affichage=unites.afficher(ligne["quantite"], ligne["famille"], ligne["nom"]),
        lieu=ligne["lieu"], date_limite=limite, jours_restants=jours,
        etat=etat_de(jours), ajoute_le=ligne["ajoute_le"],
    )


def stock_actif(con) -> list:
    return con.execute("SELECT * FROM stock WHERE consomme_le IS NULL").fetchall()


def lire_basiques(con) -> list[str]:
    """Plus de liste séparée: ce qui est toujours au placard y est aussi
    en stock, saisi sans quantité. Un ingrédient absent du stock est donc
    vraiment manquant, et ça se voit."""
    return []
