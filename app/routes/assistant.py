"""L'assistant: génération de recettes et commentaires.

Facultatif de bout en bout. Sans clé configurée, ces routes répondent
503 et le reste de l'application fonctionne à l'identique: le moteur de
suggestion n'a besoin de personne.
"""

import json
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query

from app import base as bdd
from app.commun import aujourdhui, en_sortie, maintenant, stock_actif
from app.domaine import moteur, unites
from app.modeles import *

# Pas de prefix ici: les chemins portent déjà /api, ce qui les rend
# lisibles tels quels quand on cherche une route dans le code.
routeur = APIRouter()


from app import ia
from app.domaine import cuisines, nutrition
from app.routes.recettes import charger_recettes
from app.routes.aliments import (apports_periode, cles_utilisees, lier_ciqual,
                                 toutes_les_fiches)
from outils.verifier_recettes import nettoyer_recette, verifier_recette


# ------------------------------------------------------------------ IA
#
# Tout ce qui suit est facultatif. Sans clé configurée, ces endpoints
# répondent 503 et le reste de l'app continue: le moteur local, lui,
# n'a besoin de personne.

class InventionEntree(Entree):
    portions: int = Field(default=2, ge=1, le=12)
    imposes: list[int] = []
    cuisine: str | None = Field(default=None, max_length=40)
    temps_max: int | None = Field(default=None, ge=5, le=300)
    enregistrer: bool = True


@routeur.get("/api/ia/consommation", tags=["Assistant"], summary="Tokens consommés")
def consommation(jours: int = Query(30, ge=1, le=365)):
    """Combien de tokens l'app a consommés, et pour quoi.

    Compté depuis les réponses de l'API elle-même, donc exact. Le coût
    affiché n'est indicatif que si tu passes un jour sur une offre
    payante: sur l'offre gratuite il vaut zéro, mais il donne l'ordre de
    grandeur de ce que vaudrait ton usage.
    """
    depuis = (aujourdhui() - timedelta(days=jours - 1)).isoformat()

    with bdd.base() as con:
        total = con.execute(
            """SELECT COUNT(*) n, COALESCE(SUM(entree), 0) e,
                      COALESCE(SUM(sortie), 0) s,
                      COALESCE(AVG(secondes), 0) d,
                      COALESCE(SUM(1 - succes), 0) echecs
               FROM appel_ia WHERE le >= ?""", (depuis,)).fetchone()
        par_usage = con.execute(
            """SELECT usage, COUNT(*) n, SUM(entree) e, SUM(sortie) s
               FROM appel_ia WHERE le >= ? GROUP BY usage ORDER BY n DESC""",
            (depuis,)).fetchall()
        par_jour = con.execute(
            """SELECT substr(le, 1, 10) jour, COUNT(*) n,
                      SUM(entree) e, SUM(sortie) s
               FROM appel_ia WHERE le >= ? GROUP BY jour ORDER BY jour DESC""",
            (depuis,)).fetchall()

    entree, sortie = total["e"], total["s"]
    return {
        "periode_jours": jours,
        "appels": total["n"],
        "echecs": total["echecs"],
        "duree_moyenne_s": round(total["d"], 2),
        "tokens": {"entree": entree, "sortie": sortie, "total": entree + sortie},
        "cout_indicatif_eur": round(entree / 1e6 * 2 + sortie / 1e6 * 6, 4),
        "par_usage": [dict(l) for l in par_usage],
        "par_jour": [dict(l) for l in par_jour],
    }


@routeur.get("/api/ia/cuisines", tags=["Assistant"], summary="Les cuisines du monde, par continent")
def lister_cuisines():
    """La taxonomie, pour alimenter un menu déroulant dans l'app."""
    return {"continents": cuisines.CUISINES}


@routeur.get("/api/ia/etat", tags=["Assistant"], summary="L'assistant est-il configuré")
def etat_ia():
    return {"disponible": ia.disponible(),
            "modele": ia.lire_env().get("IA_MODELE", ia.MODELE_DEFAUT)}


@routeur.post("/api/ia/recette", tags=["Assistant"], summary="Inventer une recette")
def inventer_recette(entree: InventionEntree):
    """Invente une recette quand rien du carnet ne convient.

    Le résultat passe par le même contrôle de format que les recettes
    écrites à la main. Une recette mal formée est refusée, pas rattrapée:
    mieux vaut redemander que polluer le carnet.
    """
    with bdd.base() as con:
        articles = [en_sortie(l).model_dump() for l in stock_actif(con)]
        reglages = {l["cle"]: l["valeur"]
                    for l in con.execute("SELECT cle, valeur FROM reglage").fetchall()}
        # Échantillon aléatoire et non les derniers par identifiant: les
        # recettes sont importées fichier par fichier, donc les derniers
        # identifiants appartiennent tous au même continent. Le modèle
        # évitait alors ce continent entier.
        deja = [l["titre"] for l in con.execute(
            "SELECT titre FROM recette ORDER BY RANDOM() LIMIT 12").fetchall()]

        # Ce qui a été cuisiné récemment, pour varier les origines.
        # Les repas terminés, mais aussi les recettes déjà générées:
        # au début tu n'as pas encore cuisiné, et sans ce second terme
        # rien n'empêcherait la dixième proposition sénégalaise.
        recentes = [l["cuisine"] for l in con.execute(
            """SELECT r.cuisine FROM repas p JOIN recette r ON r.id = p.recette_id
               WHERE p.statut = 'termine' AND r.cuisine IS NOT NULL
               ORDER BY p.termine_le DESC LIMIT 6"""
        ).fetchall()]
        recentes += [l["cuisine"] for l in con.execute(
            """SELECT cuisine FROM recette WHERE source = 'ia' AND cuisine IS NOT NULL
               ORDER BY id DESC LIMIT 6"""
        ).fetchall()]
        recentes = list(dict.fromkeys(recentes))[:8]

    if not articles:
        raise HTTPException(400, "Le stock est vide, il n'y a rien à cuisiner.")

    # Rien n'est imposé sans que tu le demandes. Les dates partent quand
    # même au modèle, marquées par leur urgence: il sait ce qui presse et
    # décide lui-même si ça a un sens de le cuisiner ensemble.
    imposes = [a["nom"] for a in articles if a["id"] in entree.imposes]

    try:
        brute = ia.inventer_recette(articles, reglages["contraintes"],
                                    entree.portions, imposes, deja,
                                    entree.cuisine, recentes, entree.temps_max)
    except ia.IAIndisponible as erreur:
        raise HTTPException(503, str(erreur))

    recette = verifier_recettes.nettoyer_recette(brute)
    soucis = verifier_recettes.verifier_recette(recette)

    # La consigne interdit deux protéines dans la même assiette, mais une
    # consigne n'est pas une garantie: on vérifie. Les protéines de
    # garniture ou non essentielles ne comptent pas, un oeuf posé sur un
    # riz sauté n'est pas un second plat.
    principales = [i["nom"] for i in recette["ingredients"]
                   if ia.est_proteine_majeure(i["nom"]) and i["essentiel"]
                   and i["partie"] in ("plat", "marinade")]
    if len(principales) > 1:
        soucis.append("deux protéines principales dans la même assiette: "
                      + ", ".join(principales))

    # Rien d'inventé: chaque ingrédient doit exister dans le stock. Ce
    # contrôle remplace toute liste d'interdits, puisqu'on n'achète pas
    # ce qu'on ne mange pas. Une consigne se néglige, un contrôle non.
    #
    # Mais un ingrédient facultatif absent ne disqualifie rien: il est
    # simplement retiré. Refuser toute la recette pour une coriandre de
    # finition serait absurde, et c'est justement ce que "essentiel:
    # false" veut dire.
    absents = hors_stock(recette["ingredients"], articles)
    manquants_essentiels = [i["nom"] for i in absents if i["essentiel"]]
    retires = [i["nom"] for i in absents if not i["essentiel"]]

    if manquants_essentiels:
        soucis.append("absents de mon stock: " + ", ".join(manquants_essentiels))
    if retires:
        noms = {i["nom"] for i in absents if not i["essentiel"]}
        recette["ingredients"] = [i for i in recette["ingredients"]
                                  if i["nom"] not in noms]
    if soucis:
        raise HTTPException(422, {"message": "Recette mal formée, relance la demande.",
                                  "problemes": soucis[:6], "brut": brute})

    recette["continent"] = cuisines.continent_de(recette.get("cuisine"))

    if not entree.enregistrer:
        return {"recette": recette, "autour_de": imposes,
                "retires_du_stock_absent": retires, "enregistree": False}

    with bdd.base() as con:
        # Le titre est unique en base. Un seul suffixe ne suffit pas: à la
        # troisième génération du même plat, l'insertion échouait en 500.
        base_titre, suffixe = recette["titre"], 2
        while con.execute("SELECT id FROM recette WHERE titre = ?",
                          (recette["titre"],)).fetchone():
            recette["titre"] = f"{base_titre} ({suffixe})"
            suffixe += 1
        cur = con.execute(
            """INSERT INTO recette (titre, categorie, cuisine, portions_base, temps_min,
                                    description, note, etapes, source, essai, cree_le)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ia', 1, ?)""",
            (recette["titre"], recette["categorie"], recette.get("cuisine"),
             recette["portions_base"], recette["temps_min"], recette["description"],
             recette.get("note"),
             json.dumps(recette["etapes"], ensure_ascii=False), maintenant()),
        )
        for ordre, i in enumerate(recette["ingredients"]):
            quantite, famille = unites.vers_base(i["quantite"], i["unite"])
            con.execute(
                """INSERT OR REPLACE INTO ingredient_recette
                   (recette_id, cle, nom, quantite, famille, unite, partie, essentiel, ordre)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (cur.lastrowid, moteur.normaliser(i["nom"]), i["nom"], quantite, famille,
                 i["unite"], i["partie"], int(i["essentiel"]), ordre),
            )
        return {"recette": charger_recettes(con, cur.lastrowid)[0],
                "autour_de": imposes, "retires_du_stock_absent": retires,
                "enregistree": True}


@routeur.post("/api/ia/aliment/{cle}", tags=["Assistant"], summary="Faire trancher un rattachement")
def trancher_aliment(cle: str):
    """Demande au modèle de choisir la bonne fiche CIQUAL.

    Le modèle n'a pas accès à la table: il arbitre entre les candidates
    que le moteur local a déjà retenues, et un code hors liste est
    refusé. C'est ce qui rend le résultat vérifiable.
    """
    with bdd.base() as con:
        fiches = toutes_les_fiches(con)
        origines = cles_utilisees(con, avec_carnet=True)
        nom = origines.get(cle, {}).get("nom", cle)
        candidates = nutrition.chercher_large(fiches, nom, cle, 10)

    if not candidates:
        raise HTTPException(404, f"Aucune fiche CIQUAL ne correspond à '{nom}'.")

    try:
        choix = ia.choisir_fiche(nom, candidates)
    except ia.IAIndisponible as erreur:
        raise HTTPException(503, str(erreur))

    if not choix.get("code"):
        return {"cle": cle, "lie": False, "raison": choix.get("raison", "")}

    with bdd.base() as con:
        fiche = lier_ciqual(con, cle, choix["code"], confirme=1)
    return {"cle": cle, "lie": True, "libelle": fiche["nom"],
            "raison": choix.get("raison", "")}


@routeur.get("/api/ia/bilan", tags=["Assistant"], summary="Commentaire sur mes habitudes")
def bilan_ia(jours: int = Query(7, ge=2, le=90)):
    """Un commentaire de tendances sur la période.

    Les chiffres viennent du calcul CIQUAL; le modèle ne fait que les
    lire. Il n'en produit aucun.
    """
    apports = apports_periode(jours)
    if not apports.get("repas"):
        raise HTTPException(400, "Aucun repas enregistré sur la période.")

    with bdd.base() as con:
        contraintes = con.execute(
            "SELECT valeur FROM reglage WHERE cle = 'contraintes'").fetchone()["valeur"]
    try:
        return {"periode": {"jours": jours, "repas": apports["repas"]},
                "chiffres": apports["moyenne_par_repas"],
                "commentaire": ia.commenter(apports, contraintes)}
    except ia.IAIndisponible as erreur:
        raise HTTPException(503, str(erreur))
