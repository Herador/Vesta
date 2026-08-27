"""Les quantités et les durées: masse, volume, pièce, et combien de temps.

Une erreur ici se voit tard et coûte cher: un stock faux, ou un aliment
qui ne remonte jamais dans les suggestions.
"""

from datetime import date, timedelta

import pytest

from app.domaine import conservation, unites
from app.domaine.moteur import normaliser


class TestVersBase:
    """Tout se range dans l'unité de référence de sa famille."""

    @pytest.mark.parametrize("quantite, unite, valeur, famille", [
        (2, "kg", 2000, "masse"),
        (300, "g", 300, "masse"),
        (1, "l", 1000, "volume"),
        (3, "càs", 45, "volume"),
        (1, "càc", 5, "volume"),
        (2, "", 2, "piece"),
    ])
    def test_conversion(self, quantite, unite, valeur, famille):
        assert unites.vers_base(quantite, unite) == (valeur, famille)

    @pytest.mark.parametrize("unite", ["gousse", "tranche", "brin", "pièce", "pc"])
    def test_les_facons_humaines_de_compter_une_piece(self, unite):
        """Un modèle écrit spontanément "1 gousse d'ail": autant
        l'accepter plutôt que de rejeter une recette pour si peu."""
        assert unites.vers_base(1, unite) == (1, "piece")

    @pytest.mark.parametrize("unite", [
        "c. à soupe", "c. à soupe.", "cuillère à soupe", "cuillères à soupe",
        "CÀS", "c.a.s",
    ])
    def test_la_cuillere_a_soupe_ecrite_en_toutes_lettres(self, unite):
        """Le modèle rend "c. à soupe"; le vérificateur ne connaissait que
        "càs" et refusait la recette comme unité inconnue."""
        assert unites.normaliser_unite(unite) == "càs"
        assert unites.vers_base(2, unite) == (30, "volume")

    def test_une_pincee_ne_se_decompte_pas(self):
        assert unites.vers_base(1, "pincée") == (None, None)


class TestAfficher:
    """Le retour vers l'unité qui parle."""

    def test_le_cas_qui_a_motive_le_systeme(self):
        """Deux kilos de PST moins vingt grammes."""
        valeur, famille = unites.vers_base(2, "kg")
        assert unites.afficher(valeur - 20, famille) == "1,98 kg"

    @pytest.mark.parametrize("valeur, famille, nom, attendu", [
        (300, "masse", "", "300 g"),
        (1500, "masse", "", "1,5 kg"),
        (750, "volume", "", "750 ml"),
        (2000, "volume", "", "2 l"),
        (1, "piece", "poivron", "1 poivron"),
        (3, "piece", "poivron", "3 poivrons"),
        (2, "piece", "ail", "2 ail"),          # invariable, pas "2 ails"
    ])
    def test_affichage(self, valeur, famille, nom, attendu):
        assert unites.afficher(valeur, famille, nom) == attendu

    def test_les_cuilleres_restent_des_cuilleres(self):
        """Une recette écrite en cuillères se relit en cuillères: 45 ml
        de crème est juste, mais illisible en cuisine. La conversion vers
        les millilitres ne sert qu'au calcul des apports."""
        assert unites.afficher_dans(45, "càs", "crème", "volume") == "3 c. à soupe"
        assert unites.afficher_dans(5, "càc", "huile", "volume") == "1 c. à café"

    def test_l_echelle_garde_l_unite_d_origine(self):
        """Une recette pour deux portée à trois: 4,5 cuillères, pas 67,5 ml."""
        assert unites.afficher_dans(67.5, "càs", "crème", "volume") == "4,5 c. à soupe"


class TestConvertir:
    """Passer d'une famille à l'autre, quand c'est possible."""

    def test_une_piece_vaut_un_poids_moyen(self):
        valeur, approx = unites.convertir(2, "piece", "masse", "oeuf")
        assert valeur == 110 and approx is True

    def test_sans_equivalence_on_n_invente_pas(self):
        assert unites.convertir(2, "piece", "masse", "ananas confit") == (None, False)

    def test_le_volume_ne_se_convertit_pas(self):
        """La densité est inconnue: mieux vaut ne rien dire."""
        assert unites.convertir(100, "volume", "masse", "huile") == (None, False)


class TestConservation:
    """Combien de temps ça se garde, et où."""

    @pytest.mark.parametrize("aliment, lieu", [
        ("Petits pois", "congelo"),
        ("Pois chiches", "placard"),
        ("Tomates cerises", "frigo"),
        ("Fruits rouges", "congelo"),
        ("Champignons de Paris", "frigo"),
    ])
    def test_les_pluriels_trouvent_leur_entree(self, aliment, lieu):
        """Les tables sont écrites au pluriel, les clés comparées ne le
        sont plus: ces aliments retombaient sur la durée par défaut."""
        duree = conservation.duree(normaliser(aliment), lieu)
        assert duree != conservation.PAR_DEFAUT[lieu]

    def test_le_froid_prolonge(self):
        cle = normaliser("Pavés de saumon")
        assert (conservation.duree(cle, "congelo")
                > conservation.duree(cle, "frigo") * 10)

    def test_un_aliment_inconnu_recoit_la_duree_du_lieu(self):
        assert conservation.duree("machin inconnu", "frigo") == conservation.PAR_DEFAUT["frigo"]

    def test_le_sel_n_a_pas_de_date(self):
        assert conservation.duree("sel", "placard") is None

    def test_congeler_puis_decongeler(self):
        """Congeler suspend l'horloge, décongeler la relance pour
        quelques jours: la date d'origine ne revient pas."""
        cle, hier = normaliser("Filet de poulet"), date.today() - timedelta(days=1)
        congele = conservation.redater(cle, "congelo", hier, date.today())
        assert (congele - date.today()).days > 200
        ressorti = conservation.redater(cle, "frigo", hier, congele)
        assert (ressorti - date.today()).days <= 3
