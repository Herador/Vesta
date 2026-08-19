"""L'assistant, sans jamais appeler le vrai service.

Un faux serveur local renvoie ce qu'on lui dit de renvoyer. Ça permet de
vérifier les deux choses qui comptent: ce qu'on envoie au modèle, et ce
qu'on fait de sa réponse, y compris quand elle est mauvaise.
"""

import copy
import http.server
import json
import socketserver
import threading

import pytest

RECETTE = {
    "titre": "Poulet du soir", "categorie": "plat", "cuisine": "portugaise",
    "portions_base": 2, "temps_min": 30,
    "description": "Un plat inventé pour les tests.", "note": "Sans importance.",
    "ingredients": [
        {"nom": "poulet", "quantite": 300, "unite": "g", "partie": "plat",
         "essentiel": True},
        {"nom": "carotte", "quantite": 2, "unite": "", "partie": "plat",
         "essentiel": True},
    ],
    "etapes": [
        {"titre": "Couper", "texte": "Couper 2 carottes en rondelles fines.",
         "secondes": None},
        {"titre": "Cuire", "texte": "Saisir 300 g de poulet six minutes.",
         "secondes": 360},
        {"titre": "Servir", "texte": "Servir bien chaud dans des assiettes.",
         "secondes": None},
    ],
}


@pytest.fixture
def faux_service(monkeypatch):
    """Un serveur qui répond ce qu'on lui met dans `reponse`."""
    etat = {"reponse": RECETTE, "recu": None}

    class Poignee(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            taille = int(self.headers["Content-Length"])
            etat["recu"] = json.loads(self.rfile.read(taille))
            corps = json.dumps({
                "choices": [{"message": {"content": json.dumps(etat["reponse"],
                                                               ensure_ascii=False)}}],
                "usage": {"prompt_tokens": 900, "completion_tokens": 400},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

        def log_message(self, *args):
            pass

    serveur = socketserver.TCPServer(("127.0.0.1", 0), Poignee)
    port = serveur.server_address[1]
    threading.Thread(target=serveur.serve_forever, daemon=True).start()

    monkeypatch.setenv("IA_CLE", "essai")
    monkeypatch.setenv("IA_URL", f"http://127.0.0.1:{port}/v1/chat/completions")
    yield etat
    serveur.shutdown()


@pytest.fixture
def stock_garni(client):
    for nom, quantite, unite, lieu in [
        ("Poulet", 400, "g", "frigo"), ("Carotte", 4, "", "frigo"),
        ("Riz", 1, "kg", "placard"),
    ]:
        client.post("/api/stock", json={"nom": nom, "quantite": quantite,
                                        "unite": unite, "lieu": lieu})


class TestGeneration:

    def test_une_recette_valide_entre_en_essai(self, client, faux_service, stock_garni):
        """Elle est cuisinable, mais n'encombre ni le carnet ni les
        suggestions tant qu'on ne l'a pas gardée."""
        reponse = client.post("/api/ia/recette", json={"portions": 2})
        assert reponse.status_code == 200
        rid = reponse.json()["recette"]["id"]

        assert rid not in [r["id"] for r in client.get("/api/recettes").json()]
        assert client.get(f"/api/recettes/{rid}").status_code == 200

    def test_un_format_casse_est_refuse(self, client, faux_service, stock_garni):
        faux_service["reponse"] = {"titre": "x", "categorie": "plat",
                                   "ingredients": [], "etapes": []}
        reponse = client.post("/api/ia/recette", json={"portions": 2})
        assert reponse.status_code == 422

    def test_deux_proteines_sont_signalees_sans_bloquer(self, client, faux_service,
                                                        stock_garni):
        """Un jugement de cuisine informe, il ne refuse pas: c'est à
        l'utilisateur de décider s'il fait le plat."""
        client.post("/api/stock", json={"nom": "Saumon", "quantite": 300,
                                        "unite": "g", "lieu": "frigo"})
        deux = copy.deepcopy(RECETTE)
        deux["ingredients"].append({"nom": "saumon", "quantite": 300, "unite": "g",
                                    "partie": "plat", "essentiel": True})
        deux["etapes"][1]["texte"] = "Saisir 300 g de poulet et 300 g de saumon."
        faux_service["reponse"] = deux

        reponse = client.post("/api/ia/recette", json={"portions": 2})
        assert reponse.status_code == 200
        assert reponse.json()["remarques"], "les deux protéines doivent être dites"

    def test_un_ingredient_absent_du_stock_est_signale(self, client, faux_service,
                                                       stock_garni):
        invente = copy.deepcopy(RECETTE)
        invente["ingredients"].append({"nom": "citronnelle", "quantite": 2,
                                       "unite": "", "partie": "plat",
                                       "essentiel": True})
        invente["etapes"][0]["texte"] += " Ajouter 2 citronnelles écrasées."
        faux_service["reponse"] = invente

        reponse = client.post("/api/ia/recette", json={"portions": 2})
        assert reponse.status_code == 200
        assert "citronnelle" in reponse.json()["manquants"]

    def test_le_stock_part_trie_avec_ses_marqueurs(self, client, faux_service,
                                                   stock_garni, dans):
        client.post("/api/stock", json={"nom": "Saumon", "quantite": 300,
                                        "unite": "g", "lieu": "frigo",
                                        "date_limite": dans(0)})
        client.post("/api/ia/recette", json={"portions": 2, "enregistrer": False})
        envoye = faux_service["recu"]["messages"][1]["content"]
        assert "[!!!] Saumon" in envoye

    def test_le_temps_demande_est_transmis(self, client, faux_service, stock_garni):
        client.post("/api/ia/recette", json={"portions": 2, "temps_max": 120,
                                             "enregistrer": False})
        assert "120 minutes" in faux_service["recu"]["messages"][1]["content"]

    def test_la_consommation_est_relevee(self, client, faux_service, stock_garni):
        client.post("/api/ia/recette", json={"portions": 2, "enregistrer": False})
        releve = client.get("/api/ia/consommation").json()
        assert releve["appels"] == 1
        assert releve["tokens"]["entree"] == 900


class TestApresLeRepas:

    def test_garder_une_recette_essayee(self, client, faux_service, stock_garni):
        rid = client.post("/api/ia/recette",
                          json={"portions": 2}).json()["recette"]["id"]
        repas = client.post("/api/repas",
                            json={"recette_id": rid, "portions": 2}).json()
        bilan = client.post(f"/api/repas/{repas['id']}/terminer",
                            json={"lignes": []}).json()

        assert bilan["a_decider"]["id"] == rid
        client.post(f"/api/recettes/{rid}/garder")
        assert rid in [r["id"] for r in client.get("/api/recettes").json()]

    def test_oublier_une_recette_essayee(self, client, faux_service, stock_garni):
        rid = client.post("/api/ia/recette",
                          json={"portions": 2}).json()["recette"]["id"]
        client.delete(f"/api/recettes/{rid}")
        assert client.get(f"/api/recettes/{rid}").status_code == 404


class TestSansCle:

    def test_les_routes_repondent_503(self, client, monkeypatch, stock_garni):
        """L'assistant est facultatif: le reste doit continuer de marcher."""
        monkeypatch.delenv("IA_CLE", raising=False)
        monkeypatch.setattr("app.ia.FICHIER_ENV",
                            __import__("pathlib").Path("/introuvable/.env"))
        assert client.post("/api/ia/recette", json={"portions": 2}).status_code == 503
        assert client.get("/api/stock").status_code == 200
        assert client.get("/api/suggestions").status_code == 200
