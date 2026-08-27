"""Les parcours de bout en bout, tels que l'application les emprunte.

Ces tests passent par HTTP: ils vérifient non seulement le calcul, mais
aussi ce que l'application reçoit vraiment.
"""

import pytest


def ajouter(client, nom, quantite=None, unite="", lieu="frigo", date_limite=None):
    corps = {"nom": nom, "quantite": quantite, "unite": unite, "lieu": lieu}
    if date_limite:
        corps["date_limite"] = date_limite
    reponse = client.post("/api/stock", json=corps)
    assert reponse.status_code == 201, reponse.text
    return reponse.json()


class TestStock:

    def test_ajouter_et_relire(self, client):
        article = ajouter(client, "Pavés de saumon", 400, "g")
        assert article["affichage"] == "400 g"
        assert article["genre"] == "poisson"
        assert client.get("/api/stock").json()[0]["nom"] == "Pavés de saumon"

    def test_le_tri_met_l_urgent_en_tete(self, client, dans):
        ajouter(client, "Riz", 1, "kg", "placard")
        ajouter(client, "Brocoli", 1, "", "frigo", dans(6))
        ajouter(client, "Saumon", 300, "g", "frigo", dans(1))
        ordre = [a["nom"] for a in client.get("/api/stock").json()]
        assert ordre[0] == "Saumon"
        assert ordre[-1] == "Riz"   # sans date, donc en dernier

    def test_entamer_un_article(self, client):
        """Le cas qui a motivé tout le système d'unités."""
        pst = ajouter(client, "PST", 2, "kg", "placard")
        reste = client.post(f"/api/stock/{pst['id']}/consomme",
                            json={"reste": 1980, "unite": "g"}).json()
        assert reste["affichage"] == "1,98 kg"

    def test_une_date_est_estimee_a_defaut(self, client):
        brocoli = ajouter(client, "Brocoli", 1, "", "frigo")
        assert brocoli["date_estimee"] is True
        assert 3 <= brocoli["jours_restants"] <= 10

    def test_congeler_prolonge_meme_une_date_lue_sur_le_paquet(self, client, dans):
        poulet = ajouter(client, "Filet de poulet", 400, "g", "frigo", dans(3))
        assert poulet["date_estimee"] is False
        congele = client.patch(f"/api/stock/{poulet['id']}",
                               json={"lieu": "congelo"}).json()
        assert congele["jours_restants"] > 100

    def test_un_code_barre_inconnu_ne_casse_rien(self, client):
        """Il ouvre sa fiche produit au lieu de faire échouer l'insertion."""
        reponse = client.post("/api/stock", json={
            "nom": "Yaourt", "quantite": 4, "unite": "",
            "lieu": "frigo", "code_barre": "3033490004743"})
        assert reponse.status_code == 201

    def test_un_champ_inconnu_est_refuse(self, client):
        """Une faute de frappe ignorée en silence est pire qu'une erreur."""
        article = ajouter(client, "Saumon", 300, "g")
        reponse = client.post(f"/api/stock/{article['id']}/consomme",
                              json={"id": article["id"], "quantite": 100})
        assert reponse.status_code == 422


class TestRecettes:

    def test_ecrire_relire_modifier_supprimer(self, client, recette_simple):
        creee = client.post("/api/recettes", json=recette_simple)
        assert creee.status_code == 201
        rid = creee.json()["id"]

        modifiee = client.put(f"/api/recettes/{rid}",
                              json={**recette_simple, "titre": "Plat modifié"})
        assert modifiee.status_code == 200
        assert modifiee.json()["titre"] == "Plat modifié"

        assert client.delete(f"/api/recettes/{rid}").status_code == 204
        assert client.get(f"/api/recettes/{rid}").status_code == 404

    def test_un_titre_en_double_donne_409(self, client, recette_simple):
        client.post("/api/recettes", json=recette_simple)
        assert client.post("/api/recettes", json=recette_simple).status_code == 409

    def test_la_mise_a_l_echelle(self, client, recette_simple):
        rid = client.post("/api/recettes", json=recette_simple).json()["id"]
        pour_quatre = client.get(f"/api/recettes/{rid}?portions=4").json()
        poulet = [i for i in pour_quatre["ingredients"] if i["nom"] == "poulet"][0]
        assert poulet["quantite"] == 600

    def test_les_apports_d_une_recette(self, client, recette_simple):
        rid = client.post("/api/recettes", json=recette_simple).json()["id"]
        apports = client.get(f"/api/recettes/{rid}/apports?portions=2")
        assert apports.status_code == 200
        assert "par_personne" in apports.json()


class TestSuggestions:

    def test_ce_qui_presse_remonte(self, client, dans, recette_simple):
        ajouter(client, "Poulet", 400, "g", "frigo", dans(1))
        ajouter(client, "Carotte", 3, "", "frigo", dans(15))
        ajouter(client, "Riz", 1, "kg", "placard")
        client.post("/api/recettes", json=recette_simple)

        pistes = client.get("/api/suggestions").json()
        assert pistes and pistes[0]["recette"]["titre"] == "Plat d'essai"
        assert "poulet" in pistes[0]["pourquoi"].lower()

    def test_sans_stock_aucune_piste(self, client, recette_simple):
        client.post("/api/recettes", json=recette_simple)
        assert client.get("/api/suggestions").json() == []


class TestRepas:
    """Le cycle complet: démarrer, corriger, décompter."""

    @pytest.fixture
    def prepare(self, client, dans, recette_simple):
        poulet = ajouter(client, "Poulet", 400, "g", "frigo", dans(2))
        carotte = ajouter(client, "Carotte", 4, "", "frigo", dans(10))
        riz = ajouter(client, "Riz", 1, "kg", "placard")
        rid = client.post("/api/recettes", json=recette_simple).json()["id"]
        return {"recette": rid, "poulet": poulet, "carotte": carotte, "riz": riz}

    def test_le_stock_ne_bouge_pas_au_demarrage(self, client, prepare):
        client.post("/api/repas", json={"recette_id": prepare["recette"], "portions": 2})
        poulet = [a for a in client.get("/api/stock").json() if a["nom"] == "Poulet"][0]
        assert poulet["quantite"] == 400

    def test_un_seul_repas_a_la_fois(self, client, prepare):
        client.post("/api/repas", json={"recette_id": prepare["recette"], "portions": 2})
        second = client.post("/api/repas",
                             json={"recette_id": prepare["recette"], "portions": 2})
        assert second.status_code == 409

    def test_abandonner_un_repas_libere_la_place(self, client, prepare):
        """Un repas commencé et pas validé bloquait tout nouveau repas.
        On doit pouvoir l'abandonner (le bandeau « repas en cours » le
        propose) et en relancer un autre."""
        repas = client.post("/api/repas",
                            json={"recette_id": prepare["recette"], "portions": 2}).json()
        assert client.get("/api/repas/en-cours").json()["id"] == repas["id"]

        assert client.delete(f"/api/repas/{repas['id']}").status_code == 204
        assert client.get("/api/repas/en-cours").json() is None

        relance = client.post("/api/repas",
                              json={"recette_id": prepare["recette"], "portions": 2})
        assert relance.status_code == 201

        poulet = [a for a in client.get("/api/stock").json() if a["nom"] == "Poulet"][0]
        assert poulet["quantite"] == 400   # rien décompté par l'abandon

    def test_le_compte_rendu_decompte(self, client, prepare):
        repas = client.post("/api/repas",
                            json={"recette_id": prepare["recette"], "portions": 2}).json()
        bilan = client.post(f"/api/repas/{repas['id']}/terminer", json={"lignes": [
            {"stock_id": prepare["poulet"]["id"], "nom": "Poulet",
             "quantite": 300, "unite": "g"},
            {"stock_id": prepare["riz"]["id"], "nom": "Riz",
             "quantite": 150, "unite": "g"},
        ]}).json()

        stock = {a["nom"]: a for a in client.get("/api/stock").json()}
        assert stock["Poulet"]["quantite"] == 100
        assert stock["Riz"]["quantite"] == 850
        assert bilan["retires"] == []

    def test_un_article_epuise_sort_du_stock(self, client, prepare):
        repas = client.post("/api/repas",
                            json={"recette_id": prepare["recette"], "portions": 2}).json()
        client.post(f"/api/repas/{repas['id']}/terminer", json={"lignes": [
            {"stock_id": prepare["poulet"]["id"], "nom": "Poulet", "vider": True},
        ]})
        assert "Poulet" not in [a["nom"] for a in client.get("/api/stock").json()]

    def test_un_ingredient_improvise_est_retrouve_par_son_nom(self, client, prepare):
        """On attrape souvent quelque chose qu'on a déjà: ça doit
        décompter, pas atterrir dans les ingrédients hors stock."""
        repas = client.post("/api/repas",
                            json={"recette_id": prepare["recette"], "portions": 2}).json()
        bilan = client.post(f"/api/repas/{repas['id']}/terminer", json={"lignes": [
            {"nom": "Carotte", "quantite": 2, "unite": ""},
        ]}).json()
        assert bilan["hors_stock"] == []
        carotte = [a for a in client.get("/api/stock").json() if a["nom"] == "Carotte"][0]
        assert carotte["quantite"] == 2

    def test_la_quantite_s_affiche_meme_sans_unite_en_stock(self, client, prepare,
                                                            recette_simple):
        """L'huile et les épices sont au stock sans quantité connue. La
        recette dit quand même combien en mettre: on l'affiche, dans
        l'unité du stock, même si on ne pourra rien décompter."""
        client.post("/api/stock", json={"nom": "Huile", "quantite": None,
                                        "unite": "", "lieu": "placard"})
        avec = {**recette_simple, "titre": "Avec huile",
                "ingredients": recette_simple["ingredients"]
                + [{"nom": "huile", "quantite": 30, "unite": "ml", "partie": "plat"}],
                "etapes": [{**e} for e in recette_simple["etapes"]]}
        avec["etapes"][1]["texte"] += " Ajouter 2 c. à soupe d'huile."
        rid = client.post("/api/recettes", json=avec).json()["id"]

        repas = client.post("/api/repas",
                            json={"recette_id": rid, "portions": 2}).json()
        huile = [l for l in repas["lignes"] if l["nom"] == "Huile"][0]
        assert huile["affichage"] == "30 ml"

    def test_deux_paquets_du_meme_aliment_forment_un_seul_stock(self, client,
                                                               prepare, dans):
        """Deux boîtes de riz sont un stock de riz: on annonce le total,
        et le décompte enchaîne de l'une à l'autre."""
        ajouter(client, "Riz", 400, "g", "placard")   # un second paquet

        repas = client.post("/api/repas",
                            json={"recette_id": prepare["recette"], "portions": 2}).json()
        riz = [l for l in repas["lignes"] if l["cle"] == "riz"][0]
        assert riz["paquets"] == 2
        assert riz["disponible"] == 1400          # 1 kg plus 400 g

        client.post(f"/api/repas/{repas['id']}/terminer", json={"lignes": [
            {"stock_id": riz["stock_id"], "nom": "Riz", "quantite": 1200, "unite": "g"},
        ]})
        restants = [a for a in client.get("/api/stock").json() if a["cle"] == "riz"]
        assert len(restants) == 1
        assert restants[0]["quantite"] == 200      # 1400 moins 1200

    def test_un_article_sans_quantite_ne_disparait_pas(self, client, prepare):
        """Les épices n'ont pas de quantité connue: on ne peut pas
        conclure qu'elles sont finies."""
        sel = ajouter(client, "Sel", None, "", "placard")
        repas = client.post("/api/repas",
                            json={"recette_id": prepare["recette"], "portions": 2}).json()
        client.post(f"/api/repas/{repas['id']}/terminer", json={"lignes": [
            {"stock_id": sel["id"], "nom": "Sel", "quantite": 1, "unite": "càc"},
        ]})
        assert "Sel" in [a["nom"] for a in client.get("/api/stock").json()]


class TestService:

    def test_l_application_repond(self, client):
        assert client.get("/api/sante").json()["etat"] == "ok"

    def test_le_front_est_servi(self, client):
        assert client.get("/").status_code == 200
        assert client.get("/js/app.js").status_code == 200

    def test_une_route_api_inconnue_donne_404(self, client):
        """Sans garde, le catch-all des fichiers statiques renvoyait
        l'index.html en 200 et masquait une faute de frappe dans un appel."""
        r = client.get("/api/sgestions")
        assert r.status_code == 404
        assert "text/html" not in r.headers.get("content-type", "")

    def test_l_assistant_se_declare_indisponible_sans_cle(self, client, monkeypatch):
        """La clé peut venir de l'environnement ou du fichier .env: il
        faut couper les deux, sinon le test passe chez celui qui n'a pas
        de clé et échoue chez celui qui en a une."""
        from pathlib import Path
        monkeypatch.delenv("IA_CLE", raising=False)
        monkeypatch.setattr("app.ia.FICHIER_ENV", Path("/introuvable/.env"))
        assert client.get("/api/ia/etat").json()["disponible"] is False
