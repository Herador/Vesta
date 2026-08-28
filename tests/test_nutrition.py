"""La nutrition et le classement des aliments.

Ce sont les chiffres que l'application affiche comme des faits: ils ne
peuvent pas être approximatifs sans qu'on le dise.
"""

import pytest

from app.domaine import familles, nutrition
from app.domaine.moteur import normaliser


class TestNettoyer:
    """La table CIQUAL n'écrit pas que des nombres."""

    @pytest.mark.parametrize("brut, attendu", [
        ("183", 183.0),
        ("20,4", 20.4),
        ("< 0,5", 0.5),        # la borne haute, faute de mieux
        ("traces", 0.0),
        ("-", None),           # absent: mieux vaut rien qu'un zéro faux
        ("", None),
        (None, None),
    ])
    def test_lecture_des_cellules(self, brut, attendu):
        assert nutrition.nettoyer(brut) == attendu


class TestColonnes:
    """Reconnaître les colonnes malgré des intitulés changeants."""

    def test_ne_confond_pas_energie_et_fibres(self):
        """Bug réel: la colonne "Energie, N x facteur Jones, avec fibres"
        contient le mot fibres et se faisait passer pour elle. Le saumon
        affichait 806 g de fibres."""
        entetes = [
            "alim_code", "alim_nom_fr",
            "Energie,\nRèglement\nUE N°\n1169\n2011 (kcal\n100 g)",
            "Energie, N x\nfacteur\nJones, avec\nfibres (kJ\n100 g)",
            "Fibres alimentaires (g\n100 g)",
        ]
        trouvees = nutrition.associer_colonnes(entetes)
        assert trouvees["fibres"] == 4
        assert trouvees["kcal"] == 2


def fiche(code, nom, **valeurs):
    base = {"code": code, "nom": nom, "cle": nutrition.cle_ciqual(nom),
            "pertinent": 1, "generique": 0, "kcal": 100}
    return {**base, **valeurs}


class TestChercher:
    """Choisir la bonne fiche parmi celles qui contiennent les mots."""

    @pytest.fixture
    def fiches(self):
        return [
            fiche("1", "Saumon, élevage, cru"),
            fiche("2", "Saumon, cuit à la vapeur"),
            fiche("3", "Saumon fumé"),
            fiche("4", "Huile de saumon", kcal=900),
            fiche("5", "Poivron, vert, jaune ou rouge, cru", generique=1),
            fiche("6", "Poivron vert, cru"),
            fiche("7", "Citron, zeste, cru", kcal=None),
            fiche("8", "Citron, chair sans peau, cru"),
        ]

    def test_le_cru_avant_le_cuit(self, fiches):
        """Les recettes pèsent cru: c'est la fiche crue qui vaut."""
        assert nutrition.chercher(fiches, "saumon", 1)[0]["code"] == "1"

    def test_le_fume_est_signale_quand_on_ne_l_a_pas_demande(self, fiches):
        """Chercher "saumon" ne doit jamais rattacher du saumon fumé sans
        prévenir. Le demander explicitement, en revanche, est légitime."""
        surprise = [f for f in nutrition.chercher(fiches, "saumon", 5)
                    if f["code"] == "3"]
        assert surprise and surprise[0]["transforme"] is True

        voulu = nutrition.chercher(fiches, "saumon fumé", 5)
        assert voulu[0]["code"] == "3" and voulu[0]["transforme"] is False

    def test_le_generique_avant_la_variete(self, fiches):
        assert nutrition.chercher(fiches, "poivron", 1)[0]["code"] == "5"

    def test_une_fiche_sans_energie_recule(self, fiches):
        """Le zeste de citron n'a pas de kcal: inutile pour un bilan."""
        assert nutrition.chercher(fiches, "citron", 1)[0]["code"] == "8"


class TestApports:
    """Additionner, et dire ce qu'on n'a pas pu compter."""

    @pytest.fixture
    def compositions(self):
        return {"saumon": {"kcal": 183, "proteines": 20.4, "lipides": 11.4,
                           "glucides": 0, "sucres": 0, "satures": 2.3,
                           "fibres": 0, "sel": 0.12}}

    def test_calcul_pour_deux(self, compositions):
        lignes = [{"nom": "Saumon", "cle": "saumon", "quantite": 400, "famille": "masse"}]
        calcul = nutrition.apports(lignes, compositions, portions=2)
        assert calcul["total"]["kcal"] == pytest.approx(732, abs=1)
        assert calcul["par_personne"]["kcal"] == pytest.approx(366, abs=1)

    def test_un_aliment_inconnu_est_signale(self, compositions):
        lignes = [{"nom": "Muesli germé", "cle": "muesli germe", "quantite": 60,
                   "famille": "masse"}]
        calcul = nutrition.apports(lignes, compositions, 2)
        assert calcul["couverture"]["complet"] is False
        assert calcul["couverture"]["ignores"][0]["nom"] == "Muesli germé"

    def test_les_epices_ne_troublent_pas_le_bilan(self, compositions):
        """Elles sont écartées volontairement: les signaler ferait croire
        à un bilan troué."""
        lignes = [{"nom": "Cumin", "cle": "cumin", "quantite": 5, "famille": "masse"}]
        calcul = nutrition.apports(lignes, compositions, 2)
        assert calcul["couverture"]["ignores"] == []

    def test_une_piece_convertie_est_marquee_approximative(self, compositions):
        lignes = [{"nom": "Saumon", "cle": "saumon", "quantite": 2, "famille": "piece"}]
        calcul = nutrition.apports(lignes, compositions, 2)
        assert "Saumon" in calcul["couverture"]["approximatifs"]

    def test_un_legume_compte_a_la_piece_est_bien_pris_en_compte(self):
        """Le concombre à la pièce, lié mais absent de EQUIVALENCES, ne
        se convertissait pas en grammes et disparaissait du bilan."""
        compo = {"concombre": {"kcal": 11, "proteines": 0.6, "lipides": 0.1,
                               "glucides": 1.9, "sucres": 1.4, "satures": 0,
                               "fibres": 0.9, "sel": 0}}
        lignes = [{"nom": "Concombre", "cle": "concombre", "quantite": 0.5,
                   "famille": "piece"}]
        calcul = nutrition.apports(lignes, compo, 2)
        assert calcul["couverture"]["ignores"] == []
        assert calcul["total"]["kcal"] > 0


class TestFamilles:
    """Le pictogramme d'un aliment."""

    @pytest.mark.parametrize("aliment, attendu", [
        ("Pavés de saumon", "poisson"),
        ("Filet de poulet", "viande"),
        ("Champignons de Paris", "champignon"),
        ("Pak choï", "feuille"),
        ("Crème 12%", "laitage"),
        ("Carottes", "racine"),
        ("Pois chiches", "legumineuse"),
        ("Petits pois", "legumineuse"),
        ("Pâtes", "cereale"),
        ("Pain complet", "pain"),
        ("Noix", "graine"),
        ("Origan", "epice"),
    ])
    def test_classement(self, aliment, attendu):
        assert familles.famille(normaliser(aliment)) == attendu

    @pytest.mark.parametrize("aliment, attendu", [
        ("Sauce soja", "condiment"),          # une sauce avant un soja
        ("Huile de sésame", "condiment"),     # une huile avant une graine
        ("Confiture de fraise", "sucre"),     # un sucre avant un fruit
        ("Jus de citron", "condiment"),
    ])
    def test_le_mot_de_tete_l_emporte(self, aliment, attendu):
        assert familles.famille(normaliser(aliment)) == attendu
