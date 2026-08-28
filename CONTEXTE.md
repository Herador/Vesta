# Contexte du projet

**Vesta** — application de gestion de garde-manger qui répond à une seule
question: *qu'est-ce que je cuisine ce soir avec ce que j'ai déjà ?*

Suit les péremptions, propose des recettes classées par urgence, guide la
cuisine étape par étape, décompte le stock une fois le plat terminé.

- **Stack**: FastAPI + SQLite + JavaScript vanilla (modules ES natifs, pas de build)
- **Cible**: Raspberry Pi 3 à la maison, PWA installée sur iPhone
- **Développement**: Windows au bureau, pas de droits administrateur
- **Contrainte absolue**: zéro coût récurrent. Tout le reste en découle.
- **Taille**: 29 fichiers Python (5 600 lignes), 12 modules JS (1 950 lignes),
  204 tests, 35 recettes
- **Lancement**: `uvicorn app.api:app --reload --host 0.0.0.0 --port 8000`
- **Langue**: tout en français, y compris le code (noms de variables,
  fonctions, commentaires). À conserver.

---

## Ce qui a été fait

### Backend (`app/`)
- **`base.py`** — schéma SQLite complet, connexions, migrations
  (`PRAGMA user_version` + `ajouter_colonne` idempotent). Variable
  d'environnement `VESTA_BASE` pour déplacer la base (les tests s'en servent).
- **`modeles.py`** — modèles Pydantic. `extra="forbid"` partout: une faute de
  frappe dans un champ doit lever une erreur, pas être ignorée en silence.
- **`commun.py`** — fuseau horaire, sérialisation du stock.
- **`api.py`** — assemblage: application, 9 sections Swagger, montage du front.
- **`ia.py`** — accès à Mistral (endpoint compatible OpenAI), prompts,
  journal de consommation de tokens. Reprise sur hoquet (429/5xx), plafond
  d'appels par jour, réponse tronquée signalée clairement.
- **`domaine/`** — logique métier sans dépendance FastAPI:
  - `moteur.py` — normalisation des libellés, correspondance entre aliments,
    notation d'urgence, moteur de suggestions
  - `unites.py` — masse / volume / pièce, conversions, affichage
  - `nutrition.py` — lecture CIQUAL, rapprochement des fiches, calcul d'apports
  - `conservation.py` — durées de garde par aliment et par lieu
  - `familles.py` — famille visuelle d'un aliment (pour les pictogrammes)
  - `cuisines.py` — 114 cuisines rangées en 6 continents
- **`routes/`** — un module par domaine: stock, suggestions, repas, recettes,
  aliments, assistant, reglages. 29 routes.

### Front (`web/`)
PWA installable, service worker, mode hors ligne pour la coquille.
- `js/noyau.js` — constantes, appels réseau, panneau modal, mise en forme
- `js/navigation.js` — barre du bas, écrans enregistrés par un registre
- `js/recette.js` — fiche, mode cuisine plein écran, compte rendu
- `js/editeur.js` — écrire/modifier/supprimer une recette
- `js/pictos.js` — 20 pictogrammes SVG dessinés à la main
- `js/reperes.js` — bornes nutritionnelles d'un repas
- `js/vues/` — stock, menu, carnet, bilan, aliments

### Fonctionnalités livrées
- Stock avec 3 lieux, dates estimées automatiquement, recalcul au changement
  de rangement (congeler prolonge, décongeler raccourcit)
- Moteur de suggestions local avec phrase d'explication
- Sélection d'ingrédients imposés (filtre suggestions **et** assistant)
- Mode cuisine plein écran: une étape à la fois, minuteurs persistants,
  Wake Lock pour garder l'écran allumé
- Bandeau « repas en cours » sur tous les écrans tant que le compte rendu
  n'est pas validé: on peut reprendre ou abandonner de n'importe où
- Compte rendu modifiable, décompte en cascade sur plusieurs paquets
- Apports nutritionnels par recette et bilan 7 jours, colorés selon les repères
- Écriture/modification/suppression de recettes depuis le téléphone
- Écran de rattachement des aliments aux fiches CIQUAL
- Assistant: génère une recette avec le stock réel, entre en essai

---

## Décisions importantes

**SQLite plutôt qu'un serveur de base.** Un fichier, aucune administration,
sauvegarde = `sqlite3 .backup` (la base tourne en WAL, une copie brute du
seul `.db` prendrait une version incohérente). Voir `deploiement/`.

**`app/domaine/` ne connaît pas FastAPI.** C'est la séparation qui compte:
ces six modules s'essaient dans un interpréteur, sur des données réelles.
C'est là que la plupart des bugs ont été trouvés.

**Pas d'étape de build côté front.** Modules ES natifs servis tels quels.
Sur un Pi, une chaîne de compilation serait un coût permanent pour rien.

**Les valeurs nutritionnelles sont calculées, jamais générées.** Elles
viennent de la table CIQUAL de l'ANSES. Le modèle de langage sert à trois
choses seulement: inventer une recette, arbitrer entre des fiches CIQUAL
présélectionnées par le moteur local, commenter des tendances.

**Ce qui vient du modèle est vérifié par du code, pas par une consigne.**
Une consigne se néglige, un contrôle non. Toute recette générée passe le
même contrôle de forme que celles écrites à la main, plus deux règles:
une seule protéine principale, rien qui ne soit dans le stock. Un défaut
de forme n'est plus un 422 direct: la recette et la liste de ses
problèmes repartent une fois au modèle, qui les corrige presque toujours
(`ia.reparer_recette`). Le 422 ne survient que si la reprise échoue.

**Les erreurs de forme bloquent, les jugements de cuisine informent.**
Une recette inaffichable est refusée (422). Un ingrédient manquant ou deux
protéines sont signalés dans un encart, et l'utilisateur décide.

**Les recettes inventées entrent en essai** (`essai = 1`). Invisibles au
carnet et aux suggestions tant qu'elles n'ont pas été cuisinées et gardées.
Purge automatique des essais abandonnés de plus d'un jour.

**Pas de liste d'aliments interdits.** On n'achète pas ce qu'on ne mange
pas: le contrôle « rien qui ne soit dans le stock » suffit, et une liste
d'interdits empêcherait de cuisiner un aliment acheté pour essayer.

**Les pictogrammes sont dessinés à la main.** Une bibliothèque chargée
depuis un CDN ne fonctionne pas sur un Pi sans internet, et une icône
absente vaut moins qu'une icône approximative.

**Le décompte n'a lieu qu'à la validation du compte rendu.** Un repas en
cours survit à la fermeture de l'app.

---

## Problèmes rencontrés et solutions

### Correspondance entre aliments (`moteur.py`)
Presque tous les bugs sérieux viennent de là. Chacun a son test.

- **La négation avalée**: « cacahuètes non salées » devenait « salées », et
  l'aliment se liait à la fiche opposée.
- **Transformations confondues avec l'aliment brut**: `citron` ~ `jus de
  citron`, `olive` ~ `huile d'olive`, `pomme` ~ `pomme de terre`,
  `cacahuète` ~ `beurre de cacahuète`. → table `TRANSFORMATIONS`: un de ces
  mots présent d'un seul côté disqualifie la correspondance.
- **Homonymie**: `pâtes` (pasta) ~ `pâte de crevettes`. → seuls les mots de
  `VARIETES` (rouge, vert, basmati…) autorisent une correspondance par
  inclusion.
- **`citron` ~ `citron vert`**: le citron vert est devenu un aliment
  distinct (`lime`) via `SYNONYMES`.
- **Pluriels**: les tables sont écrites en français courant (`pois chiche`),
  les clés comparées ont perdu leur pluriel (`poi chiche`). → `familles.py` et
  `conservation.py` normalisent leurs propres entrées au chargement.
- **`frais` retiré à tort** des qualificatifs: « pavés de saumon frais » ne se
  réduisait plus à `saumon`.

### Nutrition (`nutrition.py`)
- **Colonne CIQUAL mal reconnue**: « Energie, N x facteur Jones, **avec
  fibres** » se faisait passer pour la colonne fibres → 806 g de fibres pour
  du saumon.
- **Légumineuses en conserve comptées sèches**: 314 kcal/100 g au lieu de
  108, facteur 3 sur un chili. → alias vers les fiches appertisées.
- **Les épices signalées comme manquantes** alors qu'elles sont écartées
  volontairement: donnait l'impression d'un bilan troué.
- **Cru vs cuit**: les recettes pèsent **cru**, donc la fiche crue est la
  bonne. Prendre la fiche cuite pour du riz ferait perdre 56 % des calories
  (160 g cru = 560 kcal, la fiche cuite donnerait 248). À égalité, le code
  préfère toujours le cru. Ne pas changer sans réécrire les quantités du
  carnet en poids cuit.

### Assistant (`ia.py`)
- **Biais d'origine**: toutes les recettes étaient asiatiques. Trois causes
  cumulées: la phrase « asiatique en particulier » dans les réglages par
  défaut, un stock de test entièrement asiatique, et une liste « ne propose
  pas » triée par identifiant donc dominée par un seul continent.
  → tirage d'un continent au hasard, puis d'un pays dedans.
- **Recettes « flemmardes »**: température à 0,4 (trop prudent), consigne
  demandant d'être concis, aucun exemple. → température 0,85, consigne sur
  les repères sensoriels, et **une recette du carnet injectée en exemple**
  à chaque demande (jamais une recette générée, sinon le niveau ne remonte
  pas).
- **Quantités en millilitres avec unité cuillère**: « 30 càs » de sauce soja
  pour 2 cuillères, systématique sur les cuisines à sauces. Longtemps traité
  par la seule consigne; revenu en force avec `mistral-medium` (plus faible
  que `-large`). Deux garde-fous ajoutés: `controler_mesure` refuse une
  cuillère au-delà de 8 (càs) / 12 (càc), et le refus déclenche la reprise
  décrite plus haut. `nettoyer_recette` met 1 quand le chiffre manque.
- **Fautes de frappe du modèle** (« corianadre » dans la liste, « coriandre »
  dans l'étape): l'ingrédient passait pour absent. Tolérance à une coquille
  (`difflib`) dans le contrôle « apparaît dans une étape ».
- **Ingrédient imposé**: on passe la clé (`poulet`) et non le libellé du
  stock (`Filet de poulet`), sinon le modèle écrit « filet de poulet » que
  le contrôle rejette.
- **Abus du facultatif**: beurre de cacahuète marqué facultatif dans une
  recette de tofu à l'arachide. → contrôle `titre_trahi()`: si un mot du
  titre ne se retrouve que dans un ingrédient facultatif, la recette est
  refusée.

### Front
- **Le service worker servait un cache périmé**: les modifications
  n'apparaissaient pas dans Chrome alors qu'elles étaient visibles dans
  l'éditeur. → stratégie réseau-d'abord + mise à jour automatique du SW
  (`skipWaiting` + `controllerchange` + rechargement unique).
- **Deux règles CSS sous des noms différents** (`pied-colle` /
  `actions-collees`) pour la même chose: c'est l'ancienne qui s'appliquait.
  Leçon: quand un style semble ignoré, interroger le DOM plutôt que relire
  le code.
- **`prompt()` bloqué** dans une PWA installée: le bouton « ajouter un
  ingrédient » ne faisait rien. → champ de saisie.
- **Recette inventée supprimée trop tôt**: `etat.repas` était remis à zéro
  avant `fermerCuisine()`, qui croyait la recette jamais cuisinée et
  l'effaçait. Les boutons « Je la garde » / « Non, on oublie » tombaient
  ensuite sur un 404. → paramètre `abandonnable`.
- **Panneau ouvert derrière le mode cuisine** (z-index) → couches nommées
  dans les variables CSS.

### Divers
- **Windows sans `tzdata`** → crash au démarrage, repli sur l'heure locale.
- **Proxy d'entreprise (SSL)** → support de `truststore`, `IA_CERT`,
  `IA_VERIFIER=non`.
- **BOM du Bloc-notes dans `.env`** → lecture en `utf-8-sig`.
- **Swagger remplissait `"string"`** dans les champs sans exemple, ce qui
  cassait une clé étrangère (500). → fiche produit créée à la volée +
  gestionnaire `IntegrityError` → 409 + exemples réalistes dans les modèles.
- **`import *` masquait les noms non définis** de pyflakes → imports
  explicites partout.

---

## État actuel

**Ce qui marche**
- 204 tests passent (`python -m pytest`), sans réseau ni base de production
- pyflakes propre sur `app/`, `outils/`, `tests/`
- CI GitHub Actions: pyflakes + pytest à chaque push et PR
- Parcours complet vérifié au navigateur: stock → suggestions → mode cuisine
  → compte rendu → décompte
- Assistant fonctionnel avec Mistral (offre gratuite, `mistral-medium-latest` ;
  `mistral-large` répond en 60-120 s sur l'offre gratuite et dépasse le délai)

**Ce qui est en place mais peu utilisé**
- Le rattachement CIQUAL: 69 aliments liés automatiquement, 30 en attente de
  confirmation. L'écran existe désormais mais la liste n'a pas encore été
  parcourue.
- Le journal de consommation de tokens (`GET /api/ia/consommation`).

**Limites connues**
- Pas de HTTPS → pas de scan de code barre, pas de notifications.
  `localhost` fait exception (contexte sécurisé), donc le scan est
  développable et testable sur le PC.
- Le déploiement sur le Pi n'a pas encore été fait. Tailscale non installé
  (pas de droits administrateur au bureau).
- Un aliment compté en volume dans une recette et en masse au stock ne peut
  pas être décompté (densité inconnue): l'app pose la question plutôt que
  d'inventer.
- Les recettes du matin ont été retirées du carnet en attendant une vraie
  notion de moment de la journée.

**Conventions à respecter**
- Code, commentaires et messages en français
- Les commentaires expliquent le *pourquoi*, pas le *quoi*
- Un test par bug corrigé, qui décrit le cas réel rencontré
- Ne pas empiler de couches: si quelque chose casse, corriger la cause

---

## Prochaines étapes

**1. Déploiement sur le Raspberry Pi** (le plus bloquant)
- Fichiers prêts dans `deploiement/` : unité systemd, script de
  sauvegarde, marche à suivre Tailscale. Reste à les poser sur le Pi.
- La sauvegarde passe par `sqlite3 .backup` : la base tourne en WAL,
  une copie brute du seul `.db` attrape une version incohérente.
- Le service écoute sur `127.0.0.1`, l'accès distant passe par
  `tailscale serve --bg 8000`.
- Le HTTPS débloque le service worker complet et la caméra
- Changements de schéma appliqués au démarrage (`app/base.py`, `MIGRATIONS`)

**2. Liste de courses**
Ferme la boucle: stock → recettes → ce qui manque → courses → stock.
Aujourd'hui l'app dit « il te manque du citron » et s'arrête là.
Entièrement local, aucune dépendance.

**3. Scan de code barre + Open Food Facts**
Développable sur `localhost` dès maintenant. La table `produit` existe déjà
et se remplit à la volée quand un code barre inconnu est saisi.

**4. Confirmer les rattachements CIQUAL**
~30 aliments en attente. Ceux sans fiche CIQUAL (pâte de sésame, etc.)
peuvent désormais être saisis à la main ou marqués « non compté » depuis
l'écran des aliments. Un légume compté à la pièce (concombre, avocat) a
maintenant un poids moyen dans `unites.EQUIVALENCES` et entre dans le bilan.

**5. Plus tard**
- Réintégrer les petits déjeuners avec une notion de moment de la journée
- Statistiques de gaspillage (l'historique est déjà enregistré)
- Notifications la veille des dates limites (nécessite HTTPS)
- Collecte de paires (stock, recette, verdict) en vue d'un éventuel
  ajustement local. Nécessiterait une machine à 16 Go minimum; la
  distillation depuis Mistral est déconseillée tant que la qualité de la
  source n'est pas satisfaisante.
