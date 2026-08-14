"""Le garde-manger: gestion du stock, des recettes et des repas.

Le paquet est organisé par responsabilité:

    app/base.py       la base de données et son schéma
    app/modeles.py    les formes des requêtes et des réponses
    app/commun.py     ce que plusieurs routeurs partagent
    app/api.py        l'assemblage: application, routeurs, front
    app/ia.py         les prompts pour l'utilisation de l'ia
    app/domaine/      la logique métier, sans dépendance à FastAPI
    app/routes/       une route par domaine fonctionnel

La séparation qui compte est celle de `domaine/`: le moteur de
suggestion, les unités et la nutrition ne savent rien du web. On peut
les essayer dans un interpréteur, et les tester sans serveur.
"""

__version__ = "0.4"
