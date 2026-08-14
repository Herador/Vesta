"""Les routes, un module par domaine fonctionnel.

Chaque module expose un `routeur` que app/api.py assemble. L'ordre de
montage compte: les routes précises avant les routes à paramètre, sinon
`/api/aliments/recherche` serait capturé par `/api/aliments/{cle}`.
"""
