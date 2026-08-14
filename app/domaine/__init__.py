"""La logique métier, sans dépendance à FastAPI.

    moteur.py     apparier un stock et des recettes, noter l'urgence
    unites.py     masse, volume, pièce: conversion et affichage
    nutrition.py  lire CIQUAL et calculer des apports
    cuisines.py   les cuisines du monde, rangées par continent

Ces quatre modules s'utilisent dans un interpréteur, sans serveur. C'est
ce qui permet de les mettre à l'épreuve sur des données réelles avant
de les brancher à quoi que ce soit.
"""
