"""Le coeur du système: reconnaître qu'un libellé désigne un aliment.

Presque tous les bugs sérieux du projet sont venus de là. Chaque cas
ci-dessous correspond à une erreur réellement rencontrée, et non à une
situation imaginée.
"""

import pytest

from app.domaine.moteur import correspond, normaliser, poids_urgence, proposer


class TestNormaliser:
    """Ramener un libellé humain à une clé comparable."""

    @pytest.mark.parametrize("ecrit, attendu", [
        ("Pavés de saumon frais", "saumon"),
        ("pavé de saumon sans peau, en cubes", "saumon"),
        ("brocoli en petites fleurettes", "brocoli"),
        ("tomates concassées", "tomate"),
        ("gousses d'ail", "ail"),
        ("2 grosses carottes", "carotte"),
        ("carotte en fines rondelles", "carotte"),
        ("aubergines moyennes", "aubergine"),
        ("champignons de Paris émincés", "champignon"),
        ("protéines de soja texturées", "pst"),
        ("pommes de terre en cubes", "pomme de terre"),
        ("feuilles de laitue", "laitue"),
    ])
    def test_reduit_a_l_aliment(self, ecrit, attendu):
        assert normaliser(ecrit) == attendu

    def test_la_negation_ne_s_inverse_pas(self):
        """Le bug le plus grave rencontré: "non salées" devenait "salées",
        et l'aliment se retrouvait lié à la fiche opposée."""
        assert "sale" not in normaliser("cacahuètes grillées non salées")

    def test_les_chiffres_utiles_sont_gardes(self):
        """La crème 12 % n'est pas la crème entière: le nombre distingue."""
        assert "12" in normaliser("crème 12%", garder_chiffres=True)


class TestCorrespond:
    """Deux libellés désignent-ils le même aliment ?"""

    @pytest.mark.parametrize("a, b", [
        ("saumon", "pavé de saumon sans peau"),
        ("brocoli", "brocoli en fleurettes"),
        ("poivron", "poivron rouge"),
        ("oignon", "oignon nouveau"),
        ("riz", "riz basmati"),
        ("champignon", "champignons de Paris émincés"),
        ("pomme de terre", "pommes de terre en cubes"),
    ])
    def test_le_meme_aliment(self, a, b):
        assert correspond(normaliser(a), normaliser(b))

    @pytest.mark.parametrize("a, b", [
        ("citron", "jus de citron"),          # une transformation
        ("citron", "citron vert"),            # un autre fruit
        ("olive", "huile d'olive"),
        ("pomme", "pomme de terre"),
        ("cacahuète", "beurre de cacahuète"),
        ("coco", "lait de coco"),
        ("blé", "farine de blé"),
        ("haricot vert", "haricot rouge"),
        ("pâtes", "pâte de crevettes"),       # homonymie du mot "pâte"
    ])
    def test_des_aliments_differents(self, a, b):
        assert not correspond(normaliser(a), normaliser(b))


class TestUrgence:
    """Ce qui périme doit remonter, sans écraser le reste."""

    def test_plus_c_est_proche_plus_ca_pese(self):
        assert poids_urgence(0) > poids_urgence(2) > poids_urgence(5) > poids_urgence(30)

    def test_sans_date_ne_presse_pas(self):
        assert poids_urgence(None) < poids_urgence(30)


def stock(nom, jours=None, cle=None):
    return {"id": abs(hash(nom)) % 10000, "nom": nom, "cle": cle or normaliser(nom),
            "jours_restants": jours}


def recette(titre, ingredients, **extra):
    return {"id": abs(hash(titre)) % 10000, "titre": titre, "favori": 0,
            "derniere_fois": None, "categorie": "plat",
            "ingredients": [{"nom": n, "cle": normaliser(n), "essentiel": e}
                            for n, e in ingredients],
            **extra}


class TestProposer:
    """Le classement des recettes selon ce qu'on a."""

    def test_ignore_les_recettes_sans_lien_avec_le_stock(self):
        pistes = proposer([stock("saumon", 1)],
                          [recette("Gratin de courge", [("courge", True)])], [])
        assert pistes == []

    def test_l_urgence_maximale_domine(self):
        """Un saumon qui périme aujourd'hui doit passer devant trois
        légumes qui tiennent encore quatre jours."""
        articles = [stock("saumon", 0), stock("carotte", 4),
                    stock("courgette", 4), stock("poivron", 4)]
        recettes = [
            recette("Saumon vapeur", [("saumon", True)]),
            recette("Poêlée de légumes", [("carotte", True), ("courgette", True),
                                          ("poivron", True)]),
        ]
        pistes = proposer(articles, recettes, [])
        assert pistes[0].recette["titre"] == "Saumon vapeur"

    def test_un_ingredient_facultatif_absent_coute_peu(self):
        articles = [stock("saumon", 1)]
        avec = proposer(articles, [recette("A", [("saumon", True), ("aneth", False)])], [])
        sans = proposer(articles, [recette("B", [("saumon", True)])], [])
        assert sans[0].score - avec[0].score < 1

    def test_les_imposes_filtrent(self):
        articles = [stock("saumon", 1), stock("poulet", 3)]
        recettes = [recette("Au saumon", [("saumon", True)]),
                    recette("Au poulet", [("poulet", True)])]
        pistes = proposer(articles, recettes, [], imposes=[articles[0]["id"]])
        assert [p.recette["titre"] for p in pistes] == ["Au saumon"]

    def test_une_recette_faite_hier_recule(self):
        from datetime import date
        articles = [stock("saumon", 1)]
        frais = recette("Jamais faite", [("saumon", True)])
        hier = recette("Faite hier", [("saumon", True)],
                       derniere_fois=date.today().isoformat())
        pistes = proposer(articles, [hier, frais], [])
        assert pistes[0].recette["titre"] == "Jamais faite"

    def test_la_phrase_nomme_ce_qui_presse(self):
        pistes = proposer([stock("saumon", 0)],
                          [recette("Saumon vapeur", [("saumon", True)])], [])
        assert "saumon" in pistes[0].pourquoi.lower()
