"""Les formes des requêtes et des réponses.

Un modèle par usage plutôt qu'un modèle par table: ce qui entre et ce
qui sort n'ont pas les mêmes contraintes. StockEntree accepte "kg",
StockSortie renvoie des grammes et un libellé prêt à afficher.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Lieu = Literal["frigo", "congelo", "placard"]


class Entree(BaseModel):
    """Base de tous les corps de requête.

    `extra="forbid"` refuse les champs inconnus. Sans cette ligne, une
    faute de frappe comme `id` au lieu de `stock_id` est ignorée en
    silence et la requête ne fait rien, sans le moindre message. Mieux
    vaut une erreur immédiate qu'un décompte qui n'a pas eu lieu.
    """
    model_config = ConfigDict(extra="forbid")


class StockEntree(Entree):
    """Un article qui entre au stock.

    Les exemples remplissent Swagger avec des valeurs réalistes: les
    "string" par défaut produisaient des requêtes invalides.
    """
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{
        "nom": "Pavés de saumon", "quantite": 300, "unite": "g",
        "lieu": "frigo", "date_limite": "2026-08-18",
    }]})

    nom: str = Field(min_length=1, max_length=80, examples=["Pavés de saumon"])
    quantite: float | None = Field(default=None, ge=0, examples=[300])
    unite: str = Field(default="", examples=["g"],
                       description='g, kg, ml, l, càs, càc, ou "" pour une pièce')
    code_barre: str | None = Field(default=None, examples=[None],
                                   description="Laisse vide sans scan.")
    code_ciqual: str | None = Field(default=None, examples=[None],
                                    description="Code de la fiche CIQUAL, "
                                                "venant de l'autocomplétion.")
    lieu: Lieu = "frigo"
    date_limite: date | None = Field(default=None, examples=["2026-08-18"])


class StockModif(Entree):
    nom: str | None = Field(default=None, min_length=1, max_length=80)
    quantite: float | None = Field(default=None, ge=0)
    unite: str | None = None
    lieu: Lieu | None = None
    date_limite: date | None = None


class StockSortie(BaseModel):
    id: int
    nom: str
    cle: str
    code_barre: str | None
    quantite: float | None
    famille: str | None
    affichage: str
    genre: str        # famille visuelle: poisson, legume, laitage...
    lieu: str
    date_limite: date | None
    date_estimee: bool
    jours_restants: int | None
    etat: Literal["urgent", "bientot", "frais", "sans_date"]
    ajoute_le: str


class Consommation(Entree):
    reste: float | None = Field(default=None, ge=0)
    unite: str = ""
    jete: bool = False


class Reglages(Entree):
    contraintes: str
    personnes: int = Field(ge=1, le=12)


class IngredientEntree(Entree):
    nom: str = Field(min_length=1, max_length=80, examples=["carotte"])
    quantite: float | None = Field(default=None, examples=[2])
    unite: str = Field(default="", examples=[""])
    partie: str = Field(default="plat", examples=["plat"],
                        description="plat, sauce, marinade, garniture ou accompagnement")
    essentiel: bool = True


class EtapeEntree(Entree):
    titre: str = Field(min_length=1, max_length=80)
    texte: str = Field(min_length=1)
    secondes: int | None = Field(default=None, ge=0, le=36000)


class RecetteEntree(Entree):
    titre: str = Field(min_length=2, max_length=120, examples=["Poêlée de tofu"])
    categorie: str | None = "plat"
    cuisine: str | None = Field(default=None, max_length=40, examples=["chinoise"])
    portions_base: int = Field(default=2, ge=1, le=12)
    temps_min: int | None = Field(default=None, ge=1, le=600)
    description: str | None = None
    note: str | None = None
    ingredients: list[IngredientEntree] = Field(min_length=1)
    etapes: list[EtapeEntree] = []


class RepasEntree(Entree):
    recette_id: int
    portions: int = Field(default=2, ge=1, le=12)


class LigneFinale(Entree):
    stock_id: int | None = None
    nom: str = Field(min_length=1, max_length=80)
    quantite: float | None = Field(default=None, ge=0)
    unite: str = ""
    vider: bool = False  # tout ce qui restait est parti


class CompteRendu(Entree):
    lignes: list[LigneFinale] = []
    note: str | None = None
