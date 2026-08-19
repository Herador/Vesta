"""Le contrôle de forme d'une recette.

C'est la porte d'entrée du carnet: ce qui passe ici sera affiché, mis à
l'échelle et décompté. Une recette mal formée casse les trois.
"""

import copy
import json
from pathlib import Path

import pytest

from outils.verifier_recettes import (nettoyer_recette, verifier_ingredient,
                                      verifier_recette)

RACINE = Path(__file__).resolve().parent.parent


class TestIngredient:

    @pytest.mark.parametrize("nom", [
        "carotte", "pomme de terre", "sauce soja", "jus de citron vert",
        "poivron rouge", "champignon de Paris",
    ])
    def test_les_noms_acceptes(self, nom):
        assert verifier_ingredient(
            {"nom": nom, "quantite": 2, "unite": "", "partie": "plat"}) == []

    @pytest.mark.parametrize("nom", [
        "grosses carottes en julienne",   # une taille et une découpe
        "carotte moyenne",                # une taille
        "oignons émincés",                # une préparation
    ])
    def test_les_noms_refuses(self, nom):
        assert verifier_ingredient(
            {"nom": nom, "quantite": 2, "unite": "", "partie": "plat"}) != []

    def test_une_quantite_est_obligatoire(self):
        soucis = verifier_ingredient(
            {"nom": "carotte", "quantite": None, "unite": "", "partie": "plat"})
        assert any("quantité" in s for s in soucis)

    def test_une_unite_inconnue_est_refusee(self):
        soucis = verifier_ingredient(
            {"nom": "carotte", "quantite": 2, "unite": "poignée", "partie": "plat"})
        assert any("unité" in s for s in soucis)


class TestNettoyer:
    """Rattraper ce qui est rattrapable avant de contrôler."""

    def test_le_sel_et_le_poivre_sortent_de_la_liste(self):
        propre = nettoyer_recette({
            "titre": "Essai", "categorie": "plat", "description": "d",
            "portions_base": 2, "temps_min": 20,
            "ingredients": [
                {"nom": "carotte", "quantite": 2, "unite": ""},
                {"nom": "sel", "quantite": None, "unite": ""},
                {"nom": "poivre", "quantite": None, "unite": ""},
            ],
            "etapes": [{"titre": "a", "texte": "Couper les carottes et saler."}],
        })
        assert [i["nom"] for i in propre["ingredients"]] == ["carotte"]

    def test_une_gousse_devient_une_piece(self):
        """Un modèle écrit "1 gousse d'ail": c'est récupérable, donc
        récupéré plutôt que refusé."""
        propre = nettoyer_recette({
            "titre": "Essai", "categorie": "plat", "description": "d",
            "portions_base": 2, "temps_min": 20,
            "ingredients": [{"nom": "ail", "quantite": 1, "unite": "gousse"}],
            "etapes": [{"titre": "a", "texte": "Hacher l'ail finement."}],
        })
        assert propre["ingredients"][0]["unite"] == ""

    def test_les_minutes_deviennent_des_secondes(self):
        propre = nettoyer_recette({
            "titre": "Essai", "categorie": "plat", "description": "d",
            "portions_base": 2, "temps_min": 20,
            "ingredients": [{"nom": "riz", "quantite": 150, "unite": "g"}],
            "etapes": [{"titre": "a", "texte": "Cuire le riz.", "secondes": 600}],
        })
        assert propre["etapes"][0]["secondes"] == 600


class TestRecette:

    @pytest.fixture
    def valide(self, recette_simple):
        return copy.deepcopy(recette_simple)

    def test_une_recette_correcte_passe(self, valide):
        assert verifier_recette(valide) == []

    def test_il_faut_au_moins_trois_etapes(self, valide):
        valide["etapes"] = valide["etapes"][:2]
        assert verifier_recette(valide) != []

    def test_un_ingredient_absent_des_etapes_est_signale(self, valide):
        """L'oubli le plus fréquent quand on écrit une recette."""
        valide["ingredients"].append(
            {"nom": "citron", "quantite": 1, "unite": "", "partie": "garniture"})
        soucis = verifier_recette(valide)
        assert any("citron" in s for s in soucis)

    def test_un_champ_manquant_est_signale(self, valide):
        del valide["description"]
        assert any("description" in s for s in verifier_recette(valide))


class TestCarnetLivre:
    """Le carnet fourni doit rester conforme à son propre format."""

    def test_toutes_les_recettes_passent_le_controle(self):
        soucis = {}
        for fichier in sorted((RACINE / "donnees" / "recettes").glob("*.json")):
            for recette in json.loads(fichier.read_text(encoding="utf-8")):
                problemes = verifier_recette(recette)
                if problemes:
                    soucis[recette["titre"]] = problemes
        assert soucis == {}

    def test_aucun_titre_en_double(self):
        titres = [r["titre"]
                  for f in (RACINE / "donnees" / "recettes").glob("*.json")
                  for r in json.loads(f.read_text(encoding="utf-8"))]
        assert len(titres) == len(set(titres))

    def test_une_seule_proteine_principale_par_recette(self):
        """La règle qu'on impose à l'assistant vaut aussi pour nous."""
        from app.ia import est_proteine_majeure
        fautives = {}
        for fichier in (RACINE / "donnees" / "recettes").glob("*.json"):
            for recette in json.loads(fichier.read_text(encoding="utf-8")):
                principales = [i["nom"] for i in recette["ingredients"]
                               if est_proteine_majeure(i["nom"])
                               and i.get("essentiel", True)
                               and i.get("partie", "plat") in ("plat", "marinade")]
                if len(principales) > 1:
                    fautives[recette["titre"]] = principales
        assert fautives == {}
