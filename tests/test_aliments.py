"""Le rattachement des aliments aux fiches de l'ANSES.

C'est de lui que dépendent tous les chiffres du bilan. Un aliment non
relié en est absent, ce qui se voit; un aliment mal relié les fausse en
silence, ce qui ne se voit pas. D'où l'étape de confirmation.
"""

import pytest


def ajouter(client, nom, quantite=300, unite="g", **extra):
    return client.post("/api/stock", json={"nom": nom, "quantite": quantite,
                                           "unite": unite, "lieu": "frigo",
                                           **extra}).json()


@pytest.fixture
def ciqual(client):
    """Quelques fiches, insérées directement: importer la vraie table
    prendrait dix secondes par test."""
    import app.base as bdd
    from app.domaine.nutrition import cle_ciqual
    fiches = [
        ("11000", "Ail, cru", 109), ("20009", "Carotte, crue", 30),
        ("20057", "Brocoli, cru", 32), ("19501", "Fromage blanc, nature", 80),
        ("19024", "Yaourt à la grecque nature", 130),
        ("12015", "Haricot rouge, sec", 314),
        ("12016", "Haricot rouge, appertisé, égoutté", 108),
    ]
    with bdd.base() as con:
        for code, nom, kcal in fiches:
            con.execute(
                """INSERT INTO ciqual (code, nom, cle, groupe, pertinent, generique,
                                       kcal, proteines, glucides, sucres, lipides,
                                       satures, fibres, sel)
                   VALUES (?, ?, ?, 'essai', 1, 0, ?, 2, 5, 1, 1, 0.2, 2, 0.1)""",
                (code, nom, cle_ciqual(nom), kcal))
    return fiches


class TestRecherche:

    def test_trouve_par_les_mots_exacts(self, client, ciqual):
        trouvees = client.get("/api/aliments/recherche?q=brocoli").json()
        assert trouvees[0]["nom"] == "Brocoli, cru"

    def test_le_repli_sur_le_mot_principal(self, client, ciqual):
        """La recherche exacte veut tous les mots: "yaourt grec" ne
        rencontrait pas "Yaourt à la grecque", et la page restait vide."""
        trouvees = client.get("/api/aliments/recherche?q=yaourt grec").json()
        assert trouvees and "grecque" in trouvees[0]["nom"]

    def test_rien_quand_il_n_y_a_rien(self, client, ciqual):
        assert client.get("/api/aliments/recherche?q=machin inexistant").json() == []

    def test_sans_table_importee(self, client):
        assert client.get("/api/aliments/recherche?q=brocoli").status_code == 409


class TestRattachement:

    def test_rattacher_a_la_saisie(self, client, ciqual):
        """Le chemin le plus direct: on choisit la fiche en ajoutant
        l'article, et le rattachement est immédiatement confirmé."""
        ajouter(client, "Brocoli", 1, "", code_ciqual="20057")
        lies = {a["cle"]: a for a in client.get("/api/aliments").json()}
        assert lies["brocoli"]["libelle"] == "Brocoli, cru"
        assert lies["brocoli"]["confirme"] == 1

    def test_rattacher_apres_coup(self, client, ciqual):
        ajouter(client, "Carottes", 4, "")
        assert client.put("/api/aliments/carotte",
                          json={"code_ciqual": "20009"}).status_code == 200
        lies = {a["cle"]: a for a in client.get("/api/aliments").json()}
        assert lies["carotte"]["confirme"] == 1

    def test_corriger_un_rattachement(self, client, ciqual):
        """Le cas des haricots comptés secs au lieu d'égouttés: un
        facteur trois sur les calories, invisible sans cet écran."""
        ajouter(client, "Haricots rouges", 240, "g", code_ciqual="12015")
        client.put("/api/aliments/haricot rouge", json={"code_ciqual": "12016"})
        lies = {a["cle"]: a for a in client.get("/api/aliments").json()}
        assert lies["haricot rouge"]["kcal"] == 108


class TestConfirmation:

    def test_un_rapprochement_automatique_attend(self, client, ciqual):
        """Il sert au calcul, mais reste signalé tant qu'on ne l'a pas
        regardé: c'est toute la raison d'être de l'écran."""
        ajouter(client, "Ail", 1, "")
        client.post("/api/aliments/tout-lier")

        attente = {a["cle"]: a for a in client.get("/api/aliments/a-confirmer").json()}
        assert "ail" in attente
        assert attente["ail"]["actuel"]["confirme"] == 0
        assert attente["ail"]["propositions"], "il faut des fiches à proposer"

    def test_tout_confirmer_vide_la_liste(self, client, ciqual):
        ajouter(client, "Ail", 1, "")
        ajouter(client, "Carottes", 4, "")
        client.post("/api/aliments/tout-lier")
        client.post("/api/aliments/tout-confirmer")

        restants = client.get("/api/aliments/a-confirmer").json()
        assert all(not a["actuel"] for a in restants)

    def test_ce_qui_n_a_pas_de_fiche_reste_signale(self, client, ciqual):
        """Sans proposition, l'aliment attend qu'on le relie à la main
        plutôt que de disparaître silencieusement du bilan."""
        ajouter(client, "Kimchi", 200, "g")
        client.post("/api/aliments/tout-lier")
        client.post("/api/aliments/tout-confirmer")

        attente = [a["cle"] for a in client.get("/api/aliments/a-confirmer").json()]
        assert "kimchi" in attente

    def test_un_condiment_negligeable_n_encombre_pas_la_liste(self, client, ciqual):
        """Le gochujang, les épices et le bouillon sont écartés du calcul
        de toute façon: les faire figurer donnerait du travail inutile."""
        ajouter(client, "Gochujang", 100, "g")
        attente = [a["cle"] for a in client.get("/api/aliments/a-confirmer").json()]
        assert "gochujang" not in attente
