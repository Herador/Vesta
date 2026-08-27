# Vesta

Une application de gestion de frigo qui répond à une seule question:
**qu'est-ce que je cuisine ce soir avec ce que j'ai déjà ?**

Elle suit ce qui périme, propose des recettes classées par urgence,
guide la cuisine étape par étape, puis décompte le stock une fois le
plat terminé. Elle tourne sur un Raspberry Pi à la maison et s'installe
sur l'écran d'accueil d'un téléphone.

Contrainte de départ: **zéro coût récurrent**. Pas d'abonnement, pas
d'hébergement, pas de service payant. Tout ce qui suit en découle.

---

## Ce que ça fait

**Le stock.** Chaque article porte un lieu, une quantité et une date.
Les quantités sont stockées dans une unité canonique et réaffichées dans
l'unité qui parle: 2 kg moins 20 g donnent 1,98 kg. Sans date saisie,
l'application en estime une d'après l'aliment et son rangement; changer
un article de place la recalcule, parce que congeler suspend l'horloge
et décongeler la relance.

**Les suggestions.** Un moteur local apparie le stock et le carnet, note
chaque recette selon ce qu'elle sauve et ce qui manque, et explique son
choix en une phrase. Aucun appel réseau, aucun coût, fonctionne hors
ligne.

**La cuisine.** Un mode plein écran présente une étape à la fois, avec
des minuteurs qui survivent au changement d'étape et un écran qui ne
s'éteint pas. Un repas commencé reste accessible depuis un bandeau
présent sur tous les écrans, jusqu'à ce qu'on valide le compte rendu.

**Le compte rendu.** À la fin, les quantités prévues sont modifiables et
on peut ajouter ce qu'on a improvisé. C'est seulement à la validation
que le stock bouge.

**Les apports.** Calculés depuis la table CIQUAL de l'ANSES, jamais
générés. Affichés sur chaque recette et cumulés sur la semaine. Chaque
total dit ce qu'il n'a pas pu compter.

**Les aliments.** Un écran relie ce qu'on cuisine aux fiches de l'ANSES.
Les rapprochements automatiques y restent en attente jusqu'à ce qu'on les
ait regardés: un aliment mal relié fausse le bilan en silence, et c'est
comme ça que des haricots en conserve se retrouvaient comptés secs.

**L'assistant.** Facultatif. Il invente une recette avec le stock réel,
en s'appuyant sur une recette du carnet comme modèle de niveau. Ce qu'il
produit passe les mêmes contrôles que ce qu'on écrit à la main.

---

## Comment c'est fait

    app/                 le serveur
      base.py            schéma SQLite et connexions
      modeles.py         formes des requêtes et des réponses
      commun.py          ce que plusieurs routes partagent
      api.py             assemblage: application, routeurs, front
      ia.py              accès au modèle de langage
      domaine/           logique métier, sans dépendance à FastAPI
        moteur.py        apparier stock et recettes, noter l'urgence
        unites.py        masse, volume, pièce
        nutrition.py     lire CIQUAL, calculer des apports
        conservation.py  combien de temps ça se garde, et où
        familles.py      à quelle famille appartient un aliment
        cuisines.py      les cuisines du monde par continent
      routes/            une route par domaine fonctionnel

    web/                 la PWA
      index.html
      style.css
      js/
        noyau.js         constantes, réseau, panneau, mise en forme
        navigation.js    barre du bas, passage d'un écran à l'autre
        pictos.js        les pictogrammes, dessinés à la main
        recette.js       fiche, mode cuisine, compte rendu
        editeur.js       écrire une recette
        vues/            stock, menu, carnet, bilan

    outils/              scripts d'exploitation
    donnees/recettes/    le carnet, 35 recettes en JSON
    docs/                format des recettes

**La séparation qui compte** est celle de `app/domaine/`. Ces six
modules ne savent rien du web: on les essaie dans un interpréteur, sur
des données réelles, avant de brancher quoi que ce soit. C'est là que
les vrais problèmes se sont révélés, comme la confusion entre `citron`
et `jus de citron`, ou entre des haricots secs et des haricots en boîte.

**Le front n'a pas d'étape de build.** Modules ES natifs, servis tels
quels. Sur un Raspberry Pi, une chaîne de compilation serait un coût
permanent pour un bénéfice nul.

---

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate          # .venv\Scripts\activate sur Windows
pip install -r requirements.txt
```

Charger les recettes, puis la table de composition téléchargée sur
[ciqual.anses.fr](https://ciqual.anses.fr):

```bash
python -m outils.importer_recettes
python -m outils.importer_ciqual Table_Ciqual_2025.xlsx
```

Lancer:

```bash
uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```

L'application est sur `http://127.0.0.1:8000`, la documentation des
routes sur `/docs`.

Pour l'assistant, copier `.env.exemple` en `.env` et y mettre une clé
[console.mistral.ai](https://console.mistral.ai). En cas de souci:

```bash
python -m outils.diagnostic_ia
```

Un jeu d'essai, pour voir l'application peuplée sans saisir son frigo:

```bash
python -m outils.peupler_stock --vider
```

---

## Écrire une recette

Le format est décrit dans [docs/FORMAT_RECETTES.md](docs/FORMAT_RECETTES.md).
Trois règles: un ingrédient porte un nom d'aliment nu, une étape dit
quoi faire avec quelles quantités, et les ingrédients sont groupés par
partie, ce qui compte particulièrement pour les sauces asiatiques.

Un vérificateur contrôle la forme avant l'import:

```bash
python -m outils.verifier_recettes
```

Il refuse les adjectifs de taille dans les noms, les unités inconnues,
et les ingrédients qui n'apparaissent dans aucune étape.

L'application permet aussi d'écrire, modifier et supprimer une recette
directement depuis le téléphone.

---

## Les tests

```bash
pip install -r requirements-dev.txt
python -m pytest
python -m pyflakes app outils tests
```

188 tests, sans réseau ni base de production: chacun travaille sur une
base jetable, et l'assistant est remplacé par un faux serveur local. La
CI (`.github/workflows/tests.yml`) rejoue les deux à chaque push.

Ils ne cherchent pas à couvrir des lignes, mais des **erreurs déjà
commises**. Chaque cas correspond à un bug rencontré pendant le
développement:

- `citron` confondu avec `jus de citron`, et `pâtes` avec `pâte de crevettes`
- la négation avalée: "cacahuètes non salées" devenait "salées"
- la colonne CIQUAL "Energie, avec fibres" prise pour les fibres, qui
  donnait 806 g de fibres au saumon
- les haricots en conserve comptés comme des haricots secs, trois fois
  trop caloriques
- les pluriels: `pois chiche` ne rencontrait jamais `poi chiche`, et ces
  aliments perdaient leur durée de conservation
- un article sans quantité, comme le sel, disparaissant du stock après
  un repas
- la liste des ingrédients et les étapes qui se contredisent: dix
  cuillères à café de miel d'un côté, dix grammes de l'autre

Écrire ces tests en a d'ailleurs révélé quatre autres: "pavés de saumon
frais" qui n'était plus reconnu comme du saumon, et trois contrôles du
vérificateur qui ne se déclenchaient jamais parce qu'ils normalisaient
les mots avant de les chercher, ce qui les effaçait.

---

## Choix techniques

**SQLite plutôt qu'un serveur de base.** Un fichier, aucune
administration, et une sauvegarde qui tient en une commande
(`sqlite3 .backup`, la base tournant en WAL).

**Les valeurs nutritionnelles sont calculées, jamais générées.** Un
modèle qui invente des calories est exactement ce qu'il fallait éviter.
Le modèle sert à trois choses: inventer une recette, arbitrer entre des
fiches CIQUAL que le moteur local a présélectionnées, et commenter des
tendances sur plusieurs jours.

**Ce qui vient du modèle est vérifié.** Une recette générée passe le
même contrôle de forme que celles écrites à la main. S'y ajoutent deux
règles de cuisine: une seule protéine principale, et rien qui ne soit
dans le stock. Le second point est un contrôle et pas une consigne,
parce qu'une consigne se néglige.

**Les erreurs de forme bloquent, les jugements de cuisine informent.**
Une recette inaffichable est refusée; un ingrédient manquant ou deux
protéines sont signalés dans un encart, et on décide.

**Les recettes inventées entrent en essai.** Elles n'apparaissent ni au
carnet ni aux suggestions tant qu'on ne les a pas cuisinées et gardées.
Celles qu'on abandonne sont effacées.

**Les pictogrammes sont dessinés à la main.** Une bibliothèque d'icônes
chargée depuis un CDN ne fonctionne pas sur un Pi sans internet, et une
icône absente vaut moins qu'une icône approximative. Vingt tracés SVG
dans un fichier, moins lourds qu'une requête réseau.

---

## Déploiement

Tout est dans [deploiement/](deploiement/) : un service systemd pour le
redémarrage automatique, une sauvegarde quotidienne (`sqlite3 .backup`,
et non une copie de fichier : la base tourne en WAL), et Tailscale pour
l'accès HTTPS depuis le téléphone, y compris hors du domicile. Le HTTPS
n'est pas un luxe : sans lui, ni service worker complet ni accès à la
caméra.

---

## Ce qui reste à faire

- Le scan de code barre, avec Open Food Facts pour reconnaître les
  produits industriels. Il attend le HTTPS.
- Les notifications la veille des dates limites.
- Une liste de courses construite depuis ce qui manque aux recettes.
