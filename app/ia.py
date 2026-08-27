"""Accès au modèle de langage.

Trois usages, et trois seulement:
  - inventer une recette quand rien du carnet ne colle au stock;
  - trancher entre plusieurs fiches CIQUAL quand le score local hésite;
  - commenter les tendances d'une période.

Ce que le modèle ne fait jamais: produire un chiffre nutritionnel. Les
apports sont calculés depuis CIQUAL, jamais générés. Un modèle qui
invente des calories est exactement ce qu'on veut éviter.

Configuration, dans un fichier .env à côté du code:

    IA_CLE=xxxxxxxx
    IA_MODELE=mistral-large-latest      (optionnel)
    IA_URL=https://api.mistral.ai/v1/chat/completions   (optionnel)
    IA_CERT=C:/chemin/vers/ca-entreprise.pem            (optionnel)
    IA_VERIFIER=non                                     (dernier recours)

Derrière un proxy d'entreprise qui inspecte le HTTPS, Python refuse la
connexion avec "self-signed certificate in certificate chain": le proxy
re-signe le trafic avec un certificat que Python ne connaît pas, alors
que le navigateur l'accepte car il est dans le magasin de Windows. Voir
verifier_ssl() plus bas pour les trois façons de le résoudre.

Sans clé, le module se déclare simplement indisponible et le reste de
l'app continue de fonctionner: le moteur local n'a besoin de personne.
"""

import json
import os
import random
import time
from datetime import datetime
from pathlib import Path

import httpx

from app.domaine import cuisines, moteur
from app.domaine.moteur import normaliser, rang_urgence

FICHIER_ENV = Path(__file__).resolve().parent.parent / ".env"
URL_DEFAUT = "https://api.mistral.ai/v1/chat/completions"
MODELE_DEFAUT = "mistral-large-latest"
DELAI = 60.0

# Garde-fou, pas une vraie limite d'usage: un frontend qui boucle ou un
# doigt nerveux ne doivent pas vider le quota du mois en une soirée. La
# génération manuelle honnête dépasse rarement la dizaine par jour.
PLAFOND_JOUR = 60

# Codes qu'on retente: le service a hoqueté, pas refusé. 401 (clé) et 422
# (requête) ne sont pas là, les rejouer ne changerait rien.
CODES_TRANSITOIRES = {429, 500, 502, 503, 504}
ATTENTES = (1.0, 3.0)  # secondes avant les 2e et 3e tentatives


def lire_env() -> dict[str, str]:
    """Lit le .env sans dépendance supplémentaire.

    Les variables d'environnement réelles ont priorité: pratique pour
    lancer un test sans toucher au fichier.
    """
    valeurs: dict[str, str] = {}
    if FICHIER_ENV.exists():
        # utf-8-sig et non utf-8: le Bloc-notes de Windows préfixe le
        # fichier d'un BOM invisible qui, sur la première ligne, rend
        # "IA_CLE" illisible sans le moindre message d'erreur.
        for ligne in FICHIER_ENV.read_text(encoding="utf-8-sig").splitlines():
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#") or "=" not in ligne:
                continue
            cle, valeur = ligne.split("=", 1)
            valeurs[cle.strip()] = valeur.strip().strip("\"'")
    for cle in ("IA_CLE", "IA_MODELE", "IA_URL", "IA_CERT", "IA_VERIFIER"):
        if os.environ.get(cle):
            valeurs[cle] = os.environ[cle]
    return valeurs


def verifier_ssl(env: dict[str, str]):
    """Ce qu'on passe à httpx pour valider le certificat du serveur.

    Trois cas, du meilleur au pire:

    1. IA_CERT pointe sur le certificat racine de ton entreprise, exporté
       depuis le navigateur en Base64. C'est la solution propre.
    2. Le paquet truststore est installé: il fait lire à Python le magasin
       de certificats de Windows, là où le certificat de l'entreprise se
       trouve déjà. `pip install truststore` et il n'y a rien d'autre à
       faire. C'est le plus simple.
    3. IA_VERIFIER=non désactive la vérification. À n'utiliser que sur le
       réseau du bureau pour débloquer un test, jamais sur le Pi: sans
       vérification, rien ne prouve que tu parles bien à Mistral.
    """
    cert = env.get("IA_CERT")
    if cert and Path(cert).exists():
        return cert

    if env.get("IA_VERIFIER", "").strip().lower() in ("non", "no", "false", "0"):
        return False

    try:
        import ssl

        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return True


def disponible() -> bool:
    return bool(lire_env().get("IA_CLE"))


class IAIndisponible(RuntimeError):
    pass


def journaliser(usage: str, modele: str, compte: dict, duree: float,
                succes: bool = True) -> None:
    """Enregistre ce qu'a coûté un appel.

    Écrit dans la base de l'app, pas dans un fichier à part: la
    consommation fait partie de l'historique au même titre que les repas,
    et une sauvegarde du .db emporte tout.
    """
    try:
        from app import base as bdd
        with bdd.base() as con:
            con.execute(
                """INSERT INTO appel_ia (le, usage, modele, entree, sortie,
                                         secondes, succes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (datetime.now().isoformat(timespec="seconds"), usage, modele,
                 compte.get("prompt_tokens", 0), compte.get("completion_tokens", 0),
                 round(duree, 2), int(succes)),
            )
    except Exception:
        # Un journal qui casserait l'appel qu'il mesure serait absurde.
        pass


def appels_du_jour() -> int:
    """Combien d'appels au modèle depuis minuit. Zéro si la base est
    injoignable: le garde-fou ne doit jamais bloquer à tort."""
    try:
        from app import base as bdd
        debut = datetime.now().strftime("%Y-%m-%d")
        with bdd.base() as con:
            return con.execute(
                "SELECT COUNT(*) n FROM appel_ia WHERE le >= ?", (debut,)
            ).fetchone()["n"]
    except Exception:
        return 0


def demander(consigne: str, message: str, max_tokens: int = 1500,
             usage: str = "autre", temperature: float = 0.4) -> dict:
    """Un appel, une réponse JSON. Le reste du module ne fait qu'écrire
    des consignes et vérifier ce qui revient."""
    env = lire_env()
    cle = env.get("IA_CLE")
    if not cle:
        raise IAIndisponible(
            "Aucune clé configurée. Crée un fichier .env avec IA_CLE=ta_clé, "
            "obtenue gratuitement sur console.mistral.ai"
        )

    if appels_du_jour() >= PLAFOND_JOUR:
        raise IAIndisponible(
            f"Plafond de {PLAFOND_JOUR} appels par jour atteint. C'est un "
            "garde-fou contre une boucle: si l'usage est normal, relève "
            "PLAFOND_JOUR dans app/ia.py."
        )

    corps = {
        "model": env.get("IA_MODELE", MODELE_DEFAUT),
        "messages": [
            {"role": "system", "content": consigne},
            {"role": "user", "content": message},
        ],
        "response_format": {"type": "json_object"},
        # 0.4 produisait des recettes prudentes et interchangeables. Sur
        # une tâche de création, la marge de variation fait la différence
        # entre un plat et une liste de courses.
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    debut = time.monotonic()
    modele = corps["model"]

    # Une tentative, puis deux reprises espacées si le service a juste
    # hoqueté. Au-delà, on rend la main: mieux vaut redemander soi-même
    # que faire poireauter l'utilisateur devant un écran figé.
    reponse = None
    for essai, attente in enumerate((0.0, *ATTENTES)):
        if attente:
            time.sleep(attente)
        try:
            reponse = httpx.post(
                env.get("IA_URL", URL_DEFAUT),
                headers={"Authorization": f"Bearer {cle}",
                         "Content-Type": "application/json"},
                json=corps, timeout=DELAI, verify=verifier_ssl(env),
            )
        except httpx.ConnectError as erreur:
            if "CERTIFICATE_VERIFY_FAILED" in str(erreur):
                raise IAIndisponible(
                    "Certificat refusé: ton réseau inspecte le HTTPS et Python ne "
                    "reconnaît pas son certificat. Installe truststore "
                    "(pip install truststore), ou renseigne IA_CERT dans le .env "
                    "avec le certificat racine de ton entreprise."
                ) from erreur
            if essai == len(ATTENTES):
                raise IAIndisponible(f"Le service est injoignable: {erreur}") from erreur
            continue
        except httpx.RequestError as erreur:
            if essai == len(ATTENTES):
                raise IAIndisponible(f"Le service est injoignable: {erreur}") from erreur
            continue

        if reponse.status_code in CODES_TRANSITOIRES and essai < len(ATTENTES):
            continue
        break

    if reponse.status_code == 401:
        raise IAIndisponible(
            "Clé refusée par Mistral. Cause la plus fréquente: le numéro de "
            "téléphone n'est pas validé sur le compte, ce que l'offre "
            "gratuite exige avant que la moindre clé fonctionne. "
            "Lance python diagnostic_ia.py pour un diagnostic complet."
        )
    if reponse.status_code == 429:
        raise IAIndisponible("Quota atteint pour le moment, réessaie dans un instant.")
    if reponse.status_code >= 400:
        journaliser(usage, modele, {}, time.monotonic() - debut, succes=False)
        raise IAIndisponible(f"Erreur {reponse.status_code}: {reponse.text[:200]}")

    donnees = reponse.json()
    journaliser(usage, modele, donnees.get("usage") or {},
                time.monotonic() - debut)

    choix = donnees["choices"][0]
    # Réponse coupée par la limite de tokens: le JSON est tronqué, inutile
    # d'essayer de le recoller. On le dit franchement plutôt que de lever
    # une "réponse illisible" trompeuse.
    if choix.get("finish_reason") == "length":
        raise IAIndisponible(
            "La réponse a été coupée avant la fin. Relance en demandant "
            "moins de portions, ou augmente max_tokens dans app/ia.py."
        )

    brut = choix["message"]["content"]
    try:
        return json.loads(brut)
    except json.JSONDecodeError:
        # Le mode JSON est censé garantir la validité, mais on ne fait
        # jamais confiance à une garantie qu'on ne contrôle pas.
        ouvre, ferme = brut.find("{"), brut.rfind("}")
        if ouvre == -1 or ferme == -1:
            raise IAIndisponible("Réponse illisible, réessaie.")
        return json.loads(brut[ouvre:ferme + 1])


# ------------------------------------------------------------ recette

LEGENDE = ("[!!!] aujourd'hui ou dépassé · [!!] sous 2 jours · [!] cette "
           "semaine · [ ] pas pressé · (P) protéine, une seule par recette.\n"
           "Sers-toi d'abord de ce qui presse, sans t'y obliger: un plat juste "
           "qui sauve un produit vaut mieux qu'un plat bancal qui en sauve trois.")

# Ce qui compte comme protéine principale. Sert uniquement à le signaler
# au modèle: la décision reste la sienne, mais il ne peut plus dire qu'il
# ne savait pas que le saumon et les PST jouent le même rôle.
# Les protéines qui font le plat: deux d'entre elles dans la même
# assiette, c'est un déséquilibre, pas une recette.
PROTEINES_MAJEURES = {
    "poulet", "dinde", "boeuf", "porc", "agneau", "veau", "canard", "lapin",
    "saumon", "truite", "poisson", "thon", "cabillaud", "tofu", "tempeh",
    "pst", "seitan", "lardon", "jambon", "saucisse",
}

# Celles qui accompagnent sans concurrencer: l'oeuf lie une farce ou
# couronne un bibimbap, les légumineuses font corps avec les PST dans un
# chili. On les signale au modèle sans les interdire.
PROTEINES_APPOINT = {
    "oeuf", "lentille", "pois chiche", "haricot rouge", "haricot blanc",
    "haricot noir", "feve", "pois casse",
}

PROTEINES = PROTEINES_MAJEURES | PROTEINES_APPOINT


def _contient(nom: str, ensemble: set[str]) -> bool:
    mots = set(normaliser(nom).split())
    return any(set(p.split()) <= mots for p in ensemble)


def est_proteine(nom: str) -> bool:
    return _contient(nom, PROTEINES)


def est_proteine_majeure(nom: str) -> bool:
    return _contient(nom, PROTEINES_MAJEURES)


# Un marqueur par rang du barème (voir moteur.rang_urgence). Les deux
# derniers, "plus loin qu'une semaine" et "sans date", ne pressent pas.
MARQUEURS = ["[!!!]", "[!!]", "[!]", "[!]", "[ ]", "[ ]"]
SANS_URGENCE = len(moteur.PALIERS_URGENCE)   # rang à partir duquel rien ne presse


def trier_par_urgence(stock: list[dict]) -> list[dict]:
    """Le plus pressé en tête: un modèle lit une liste par le haut."""
    return sorted(stock, key=lambda a: (rang_urgence(a.get("jours_restants")),
                                        a.get("jours_restants") if a.get("jours_restants") is not None else 999,
                                        a["nom"]))


def decrire_article(article: dict) -> str:
    jours = article.get("jours_restants")
    if jours is None:
        delai = "sans date"
    elif jours < 0:
        delai = f"dépassé depuis {abs(jours)} j"
    elif jours == 0:
        delai = "aujourd'hui"
    elif jours == 1:
        delai = "demain"
    else:
        delai = f"{jours} jours"

    quantite = article.get("affichage") or "quantité non précisée"
    lieu = article.get("lieu", "")
    marque = " (P)" if est_proteine(article["nom"]) else ""
    return (f"{MARQUEURS[rang_urgence(article.get('jours_restants'))]} "
            f"{article['nom']}{marque} — {quantite} — {delai}"
            + (f" — {lieu}" if lieu else ""))


CONSIGNE_RECETTE = """Tu écris des recettes pour une application de cuisine personnelle.
Réponds en français, par un objet JSON valide et rien d'autre.

Schéma:
{"titre": str, "categorie": "plat"|"petitdej"|"collation"|"defi",
 "cuisine": str (le pays, pas le continent), "portions_base": int,
 "temps_min": int, "description": str (une phrase), "note": str (le tour de main),
 "ingredients": [{"nom": str, "quantite": number,
                  "unite": "g"|"ml"|"c. à soupe"|"c. à café"|"",
                  "partie": "plat"|"sauce"|"marinade"|"garniture"|"accompagnement",
                  "essentiel": bool}],
 "etapes": [{"titre": str, "texte": str, "secondes": int|null}]}

Exemples:
{"nom": "carotte", "quantite": 2, "unite": "", "partie": "plat", "essentiel": true}
{"titre": "La sauce", "texte": "Mélanger 3 c. à soupe de sauce soja, 1 c. à café de sucre et 4 c. à soupe d'eau.", "secondes": null}

Format:
- nom: l'aliment nu, trois mots maximum, sans taille ni découpe. "carotte",
  pas "grosse carotte en julienne". Un jus, une huile ou une farine est un
  aliment distinct de son origine: "jus de citron" n'est pas "citron".
- unite: "" pour tout ce qui se compte à la pièce, gousse d'ail et oeuf
  compris. "c. à soupe" et "c. à café" pour les condiments, comme en cuisine.
- la quantité est toujours chiffrée, et c'est le nombre d'unités, jamais
  une conversion. Deux cuillères à soupe de sauce soja s'écrivent quantite 2
  et unite "c. à soupe", jamais 30. Ne mets pas la quantité en ml quand tu
  mesures en cuillères. Sans chiffre, retire l'ingrédient.
- Ne liste ni sel, ni poivre, ni eau: écris "salez" dans l'étape.
- essentiel: false si son absence n'empêche pas le plat.
- etapes: 5 à 10, chacune répétant ses quantités. Les découpes vont dans une
  étape de mise en place. secondes uniquement quand l'étape attend.
- Chaque ingrédient listé apparaît dans au moins une étape.
- La liste et les étapes disent la même quantité, dans la même unité.

Ce qui sépare une vraie recette d'une liste d'instructions:
- Des repères sensoriels plutôt que des durées seules. "Jusqu'à ce que les
  bords brunissent et que ça sente la noisette", pas "faire revenir 5 min".
- Le pourquoi quand il change le résultat: pourquoi hors du feu, pourquoi
  sans remuer, pourquoi à couvert. Une phrase, pas un cours.
- La technique propre à la cuisine choisie, pas une méthode passe-partout
  repeinte aux épices locales. Un sofritto n'est pas un oignon revenu, une
  sauce chinoise se mélange avant d'allumer le feu.
- Une sauce complète et équilibrée: salé, acide, sucré, liant, gras.
- La note dit l'erreur que tout le monde commet sur ce plat, ou le
  raccourci qui marche. Pas une généralité.
- Ne double pas les étapes pour faire nombre: chaque étape fait avancer
  le plat.

Composition:
- Une seule protéine principale: viande, poisson, tofu, PST ou seitan. L'oeuf
  et les légumineuses peuvent l'accompagner quand la cuisine le fait vraiment.
- Assiette visée: moitié légumes, un quart protéines, un quart féculents.
- Crème, beurre, lait de coco, fromage: seulement si la cuisine les emploie.
- N'utilise que des ingrédients présents dans le stock fourni, épices,
  huiles et bouillons compris: ce qui n'est pas listé, je ne l'ai pas. Si
  le stock ne permet pas la recette que tu avais en tête, change de
  recette plutôt que de compléter la liste, sauf pour un ingrédient
  facultatif.
- N'ajoute rien au seul motif que c'est urgent.
"""


def en_exemple(recette: dict) -> str:
    """Une recette du carnet, réduite à ce qui montre le niveau attendu.

    Un exemple pèse environ 500 tokens et vaut mieux que dix consignes
    supplémentaires: le modèle voit ce qu'est une étape écrite avec des
    repères sensoriels, plutôt que de lire qu'il en faut.
    """
    ingredients = [{"nom": i["nom"], "quantite": i["quantite"],
                    "unite": i.get("unite", ""), "partie": i.get("partie", "plat"),
                    "essentiel": bool(i["essentiel"])}
                   for i in recette["ingredients"]]
    exemple = {
        "titre": recette["titre"], "categorie": recette["categorie"],
        "cuisine": recette["cuisine"], "portions_base": recette["portions_base"],
        "temps_min": recette["temps_min"], "description": recette["description"],
        "note": recette["note"], "ingredients": ingredients,
        "etapes": recette["etapes"],
    }
    return json.dumps(exemple, ensure_ascii=False)


def inventer_recette(stock: list[dict], contraintes: str, personnes: int,
                     imposes: list[str], deja_vus: list[str],
                     cuisine: str | None = None,
                     recentes: list[str] | None = None,
                     temps_max: int | None = None,
                     exemple: dict | None = None) -> dict:
    """Invente une recette utilisable avec ce qu'il y a vraiment."""
    presses, tranquilles = [], []
    for a in trier_par_urgence(stock):
        loin = rang_urgence(a.get("jours_restants")) >= SANS_URGENCE
        (tranquilles if loin else presses).append(a)

    # Les produits sans échéance n'ont pas besoin d'une ligne chacun: une
    # énumération suffit et libère la moitié du message pour ce qui compte.
    lignes = [decrire_article(a) for a in presses]
    if tranquilles:
        lignes.append("Sans urgence: " + ", ".join(
            f"{a['nom']}{' (P)' if est_proteine(a['nom']) else ''}"
            f" {a.get('affichage', '')}".rstrip()
            for a in tranquilles))

    # Les données variables seulement: les règles invariantes vivent dans
    # la consigne système, qui ne change pas d'un appel à l'autre. Séparer
    # les deux évite de répéter les mêmes phrases à deux endroits, ce qui
    # allonge le prompt et brouille la hiérarchie des consignes.
    blocs = [
        f"Invente une recette pour {personnes} personnes.",
        f"<mes_regles>\n{contraintes}\n</mes_regles>",
        f"<stock>\n{LEGENDE}\n" + ("\n".join(lignes) or "(vide)") + "\n</stock>",
        f"<origine>\n{origine(cuisine, recentes or [])}\n</origine>",
    ]
    if exemple:
        blocs.append("<exemple_du_niveau_attendu>\n" + en_exemple(exemple)
                     + "\n</exemple_du_niveau_attendu>\n"
                     "Vise ce niveau d'écriture et de technique. N'en reprends "
                     "ni le plat ni les ingrédients.")
    if temps_max:
        blocs.append(f"Temps total: {temps_max} minutes au maximum.")
    if imposes:
        blocs.append(f"À utiliser obligatoirement: {', '.join(imposes)}.")
    if deja_vus:
        blocs.append(f"Déjà dans mon carnet, ne les repropose pas: "
                     f"{', '.join(deja_vus)}.")
    return demander(CONSIGNE_RECETTE, "\n\n".join(blocs), max_tokens=3000,
                    usage="recette", temperature=0.85)


def origine(cuisine: str | None, recentes: list[str]) -> str:
    """La consigne de provenance.

    Sans elle, le modèle suit la pente de ce qu'il voit dans le stock:
    de la sauce soja et du riz au placard suffisent à le ramener en Asie
    à chaque fois, quelle que soit la protéine imposée.
    """
    if cuisine:
        # Un continent vaut consigne de région, un pays vaut consigne de pays.
        demande = cuisine.strip().lower()
        if demande in cuisines.CUISINES:
            liste = random.sample(cuisines.CUISINES[demande], 5)
            return f"Une cuisine d'{cuisine}, par exemple {', '.join(liste)}."
        return (f"Cuisine {cuisine} imposée. Adapte aromates et technique, "
                "même si mon placard vient d'ailleurs.")

    continent, proposees = cuisines.pistes(recentes)
    lignes = []
    if recentes:
        lignes.append(f"Déjà mangé récemment: {', '.join(recentes)}.")
    lignes.append(f"Direction {continent}: {', '.join(proposees)}, "
                  "ou une autre du même continent si elle colle mieux au stock.")
    lignes.append("Mon placard ne dicte pas l'origine: du beurre de cacahuète "
                  "ou de la sauce soja n'imposent rien.")
    return "\n".join(lignes)


# ------------------------------------------------------------ CIQUAL

CONSIGNE_FICHE = """Relie un aliment de cuisine à la bonne fiche de la table CIQUAL.
Réponds en JSON: {"code": "26036", "raison": "une phrase courte"}
Si aucune fiche ne convient: {"code": null, "raison": "..."}

Ordre de préférence, à égalité:
- la fiche crue plutôt que cuite, car les recettes pèsent cru;
- la fiche générique ("aliment moyen", "sans précision") plutôt qu'une variété;
- un aliment transformé (fumé, confit, en sauce) seulement si la demande l'est.
"""


def choisir_fiche(nom: str, candidates: list[dict]) -> dict:
    """Tranche entre les meilleures fiches quand le score local hésite.

    Le modèle ne cherche pas dans la table: il arbitre entre des
    candidates que le moteur local a déjà sélectionnées. C'est ce qui
    rend l'appel court, fiable et vérifiable.
    """
    liste = "\n".join(f'- {f["code"]}: {f["nom"]}' for f in candidates)
    message = f"Aliment: {nom}\n\nFiches possibles:\n{liste}"
    reponse = demander(CONSIGNE_FICHE, message, max_tokens=300, usage="aliment")

    codes = {f["code"] for f in candidates}
    if reponse.get("code") and reponse["code"] not in codes:
        # Le modèle a inventé un code: on refuse plutôt que d'enregistrer
        # une association fantaisiste.
        return {"code": None, "raison": "Code proposé hors de la liste, choix refusé."}
    return reponse


# ------------------------------------------------------------ bilan

CONSIGNE_BILAN = """Commente des habitudes alimentaires sur plusieurs jours, en français.
Réponds en JSON: {"constat": "2 à 3 phrases", "points_forts": [...],
"a_surveiller": [...], "suggestions": [...]}, deux ou trois éléments par liste.

- Les chiffres fournis sont calculés: cite-les tels quels ou pas du tout,
  n'en invente aucun.
- Raisonne en tendances sur la période, jamais sur un repas isolé: les
  quantités sont estimées.
- Des constats et des pistes concrètes, pas de note ni de jugement.
- Si des aliments n'ont pas pu être comptés, dis que le bilan est partiel.
"""


def commenter(apports: dict, contraintes: str) -> dict:
    """Lit une période de repas et en tire des tendances."""
    message = "\n".join([
        "MES RÈGLES DE CUISINE:",
        contraintes,
        "",
        f"Période: {apports['jours']} jours, {apports['repas']} repas enregistrés.",
        f"Moyenne par repas et par personne: {json.dumps(apports['moyenne_par_repas'], ensure_ascii=False)}",
        f"Aliments distincts: {apports['variete']['aliments_distincts']}",
        f"Les plus fréquents: {json.dumps(apports['variete']['les_plus_frequents'], ensure_ascii=False)}",
        f"Plats: {json.dumps([r['titre'] for r in apports['detail']], ensure_ascii=False)}",
        f"Non comptés faute de données: {json.dumps(apports['non_comptes'], ensure_ascii=False)}",
    ])
    return demander(CONSIGNE_BILAN, message, max_tokens=900, usage="bilan")
