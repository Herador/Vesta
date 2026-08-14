# Format des recettes

Une recette est un objet JSON. Les fichiers vivent dans `recettes/` et
contiennent chacun une liste de recettes. L'import lit tout le dossier:

    python importer.py recettes/

## Les trois règles

**1. Un ingrédient porte un nom d'aliment, rien d'autre.**

    "carotte"                      et non  "carotte en julienne"
    "poulet"                       et non  "filet de poulet en lanières"
    "champignon de Paris"          et non  "champignons émincés"

La découpe, l'état et la quantité vont dans les étapes. C'est ce qui
permet de retrouver l'aliment dans le stock et dans la table CIQUAL.
Les noms composés restent entiers quand ils désignent un aliment
différent: `sauce soja`, `lait de coco`, `pomme de terre`, `oignon
nouveau`, `haricot vert`.

**2. Une étape dit quoi faire, avec quelle quantité, et combien de temps.**

Les quantités sont répétées dans le texte des étapes, parce que c'est là
qu'on les lit en cuisinant. `secondes` déclenche un minuteur.

**3. Les ingrédients sont regroupés par partie.**

`plat`, `sauce`, `marinade`, `garniture`, `accompagnement`. C'est
indispensable en cuisine asiatique, où la sauce se mélange à l'avance
dans un bol et se verse d'un coup: la séparer du reste évite de la
bâcler.

## Le gabarit

```json
{
  "titre": "Gong bao de PST",
  "categorie": "plat",
  "cuisine": "chinoise",
  "portions_base": 2,
  "temps_min": 25,
  "description": "Une phrase qui dit ce que c'est et ce qui fait le plat.",
  "note": "Le tour de main, la variante, ce qui se congèle.",
  "tags": ["PST", "rapide"],
  "ingredients": [
    {"nom": "PST", "quantite": 80, "unite": "g", "partie": "plat"},
    {"nom": "poivron rouge", "quantite": 1, "unite": "", "partie": "plat"},
    {"nom": "sauce soja", "quantite": 3, "unite": "càs", "partie": "sauce"},
    {"nom": "coriandre", "quantite": 10, "unite": "g", "partie": "garniture",
     "essentiel": false}
  ],
  "etapes": [
    {"titre": "La sauce", "texte": "Mélanger dans un bol 3 c. à soupe de sauce soja...", "secondes": null},
    {"titre": "Sauter", "texte": "Feu vif, 6 minutes.", "secondes": 360}
  ]
}
```

## Les champs

| champ | obligatoire | valeurs |
|---|---|---|
| `titre` | oui | unique dans tout le carnet |
| `categorie` | oui | `plat`, `petitdej`, `collation`, `defi` |
| `cuisine` | non | `chinoise`, `japonaise`, `coreenne`, `thaie`, `indienne`, `francaise`... |
| `portions_base` | oui | entier, 2 par défaut |
| `temps_min` | oui | durée totale réelle, mise en place comprise |
| `ingredients[].unite` | oui | `g`, `ml`, `càs`, `càc`, ou `""` pour une pièce |
| `ingredients[].partie` | non | `plat` par défaut |
| `ingredients[].essentiel` | non | `true` par défaut, `false` si son absence n'empêche pas le plat |
| `etapes[].secondes` | non | `null` si l'étape n'attend pas |

## Vérifier avant d'importer

    python verifier_recettes.py recettes/

Le script refuse les noms d'ingrédients composés d'adjectifs, les unités
inconnues, les ingrédients qui n'apparaissent dans aucune étape, et les
doublons de titre. Il ne juge pas la cuisine, seulement la forme.
