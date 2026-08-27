"""Couche base de données: connexion SQLite et schéma.

Un seul fichier .db à côté du code. Pour sauvegarder l'app entière,
il suffit de copier ce fichier.

Les quantités sont toujours stockées dans l'unité de référence de leur
famille, gramme, millilitre ou pièce, jamais dans l'unité saisie.
Voir unites.py.
"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

# La base vit à la racine du projet, pas dans le paquet: elle est
# une donnée, pas du code, et une sauvegarde se résume à la copier.
RACINE = Path(__file__).resolve().parent.parent
CHEMIN_BASE = RACINE / "garde-manger.db"


def chemin_base() -> Path:
    """Où vit la base.

    La variable VESTA_BASE permet de la déplacer sans toucher au code:
    les tests s'en servent pour travailler sur une base jetable, et un
    déploiement peut la ranger ailleurs que dans le dossier du projet.
    """
    ailleurs = os.environ.get("VESTA_BASE")
    return Path(ailleurs) if ailleurs else CHEMIN_BASE

SCHEMA = """
PRAGMA journal_mode = WAL;

-- Cache local d'Open Food Facts: un produit scanné une fois est
-- reconnu instantanément ensuite, même hors ligne.
CREATE TABLE IF NOT EXISTS produit (
    code_barre TEXT PRIMARY KEY,
    nom        TEXT NOT NULL,
    marque     TEXT,
    categorie  TEXT,
    image_url  TEXT,
    vu_le      TEXT NOT NULL
);

-- Le stock. Une ligne consommée n'est jamais supprimée, elle est datée:
-- c'est ce qui permettra les statistiques de gaspillage.
CREATE TABLE IF NOT EXISTS stock (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nom         TEXT NOT NULL,
    cle         TEXT NOT NULL,
    code_barre  TEXT REFERENCES produit(code_barre),
    quantite    REAL,
    famille     TEXT,
    lieu        TEXT NOT NULL DEFAULT 'frigo',
    date_limite TEXT,
    -- Une date calculée se recalcule quand l'article change de lieu; une
    -- date lue sur l'emballage, jamais.
    date_estimee INTEGER NOT NULL DEFAULT 0,
    ajoute_le   TEXT NOT NULL,
    consomme_le TEXT,
    jete        INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_stock_actif ON stock(consomme_le, date_limite);

-- Le carnet. `etapes` contient un tableau JSON de {titre, texte, secondes}.
CREATE TABLE IF NOT EXISTS recette (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    titre         TEXT NOT NULL UNIQUE,
    categorie     TEXT,
    cuisine       TEXT,
    portions_base INTEGER NOT NULL DEFAULT 2,
    temps_min     INTEGER,
    description   TEXT,
    note          TEXT,
    etapes        TEXT,
    source        TEXT NOT NULL DEFAULT 'carnet',
    -- Une recette inventée entre en essai: elle sert à cuisiner ce soir,
    -- mais n'encombre ni le carnet ni les suggestions tant que tu n'as
    -- pas dit qu'elle valait le coup.
    essai         INTEGER NOT NULL DEFAULT 0,
    favori        INTEGER NOT NULL DEFAULT 0,
    derniere_fois TEXT,
    cree_le       TEXT NOT NULL
);

-- Quantités exprimées pour `portions_base` de la recette.
-- `essentiel = 0` pour ce qui est remplaçable ou décoratif: son absence
-- ne doit pas disqualifier la recette.
CREATE TABLE IF NOT EXISTS ingredient_recette (
    recette_id INTEGER NOT NULL REFERENCES recette(id) ON DELETE CASCADE,
    cle        TEXT NOT NULL,
    nom        TEXT NOT NULL,
    quantite   REAL,
    famille    TEXT,
    unite      TEXT,
    partie     TEXT NOT NULL DEFAULT 'plat',
    essentiel  INTEGER NOT NULL DEFAULT 1,
    ordre      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (recette_id, cle, partie)
);

CREATE INDEX IF NOT EXISTS idx_ing_cle ON ingredient_recette(cle);

-- Un repas en cours survit à la fermeture de l'app. Le stock n'est
-- décompté qu'à la validation du compte rendu.
CREATE TABLE IF NOT EXISTS repas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    recette_id  INTEGER REFERENCES recette(id) ON DELETE SET NULL,
    titre       TEXT NOT NULL,
    portions    INTEGER NOT NULL DEFAULT 2,
    statut      TEXT NOT NULL DEFAULT 'en_cours',
    commence_le TEXT NOT NULL,
    termine_le  TEXT,
    note        TEXT
);

CREATE TABLE IF NOT EXISTS repas_ligne (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    repas_id  INTEGER NOT NULL REFERENCES repas(id) ON DELETE CASCADE,
    stock_id  INTEGER REFERENCES stock(id) ON DELETE SET NULL,
    nom       TEXT NOT NULL,
    cle       TEXT NOT NULL,
    quantite  REAL,
    famille   TEXT,
    approx    INTEGER NOT NULL DEFAULT 0,
    improvise INTEGER NOT NULL DEFAULT 0
);

-- La table CIQUAL de l'ANSES, importée une fois pour toutes. Environ
-- 3500 aliments génériques, en français, hors ligne. C'est la référence
-- pour tout ce qui n'a pas de code barre: un poivron, un pavé de saumon.
CREATE TABLE IF NOT EXISTS ciqual (
    code      TEXT PRIMARY KEY,
    nom       TEXT NOT NULL,
    cle       TEXT NOT NULL,
    groupe    TEXT,
    sousgroupe TEXT,
    pertinent INTEGER NOT NULL DEFAULT 1,
    generique INTEGER NOT NULL DEFAULT 0,
    kcal      REAL,
    proteines REAL,
    glucides  REAL,
    sucres    REAL,
    lipides   REAL,
    satures   REAL,
    fibres    REAL,
    sel       REAL
);

CREATE INDEX IF NOT EXISTS idx_ciqual_cle ON ciqual(cle);

-- L'association entre TES aliments et une composition pour 100 g.
-- `confirme = 0` signale un rapprochement automatique que tu n'as pas
-- encore validé: l'app peut alors demander confirmation plutôt que de
-- faire passer une approximation pour une certitude.
CREATE TABLE IF NOT EXISTS aliment (
    cle       TEXT PRIMARY KEY,
    libelle   TEXT,
    source    TEXT NOT NULL DEFAULT 'ciqual',
    reference TEXT,
    confirme  INTEGER NOT NULL DEFAULT 0,
    kcal      REAL,
    proteines REAL,
    glucides  REAL,
    sucres    REAL,
    lipides   REAL,
    satures   REAL,
    fibres    REAL,
    sel       REAL
);

-- Consommation de l'API, relevée depuis chaque réponse. La console du
-- fournisseur agrège à sa façon et avec du retard: ce journal-ci est
-- exact, local, et survit à un changement de fournisseur.
CREATE TABLE IF NOT EXISTS appel_ia (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    le         TEXT NOT NULL,
    usage      TEXT NOT NULL,
    modele     TEXT,
    entree     INTEGER NOT NULL DEFAULT 0,
    sortie     INTEGER NOT NULL DEFAULT 0,
    secondes   REAL,
    succes     INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_appel_date ON appel_ia(le);

CREATE TABLE IF NOT EXISTS reglage (
    cle    TEXT PRIMARY KEY,
    valeur TEXT NOT NULL
);
"""

# Comment je cuisine. Ce qui n'y figure pas est déduit du stock: les
# aliments que je n'aime pas, je ne les achète pas, donc ils n'y sont
# pas. Et si j'en achète un jour pour essayer, je veux pouvoir cuisiner
# avec, ce qu'une liste d'interdits m'empêcherait.
CONTRAINTES_DEFAUT = """Je cuisine pour 2 personnes, le soir.
Assiette: moitié légumes, un quart protéines, un quart féculents pesés 50 à 70 g crus par personne. Huile mesurée à la cuillère, crème 3 cuillères à soupe maximum.
Style: cuisine du monde, du goût, jamais de plat fade."""


def colonnes(con, table: str) -> set[str]:
    return {ligne["name"] for ligne in con.execute(f"PRAGMA table_info({table})")}


def ajouter_colonne(con, table: str, colonne: str, definition: str) -> None:
    """ALTER TABLE idempotent: ne fait rien si la colonne est déjà là.

    SCHEMA crée toujours les tables dans leur forme du jour; une base
    déjà en place, elle, a besoin qu'on lui ajoute après coup les
    colonnes venues plus tard. On vérifie donc avant d'ajouter, ce qui
    rend une migration rejouable sur une base neuve comme ancienne.
    """
    if colonne not in colonnes(con, table):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {colonne} {definition}")


# Les changements de schéma que `SCHEMA` ne peut pas faire seul: ajout de
# colonne à une table existante, remplissage d'une valeur. Chaque entrée
# est (numéro, fonction). `PRAGMA user_version` retient le dernier
# numéro appliqué, donc on ne rejoue rien inutilement. Exemple:
#   (1, lambda con: ajouter_colonne(con, "recette", "moment", "TEXT")),
MIGRATIONS: list = [
]


def migrer(con) -> None:
    version = con.execute("PRAGMA user_version").fetchone()[0]
    for numero, appliquer in MIGRATIONS:
        if numero > version:
            appliquer(con)
    cible = MIGRATIONS[-1][0] if MIGRATIONS else 0
    if cible > version:
        con.execute(f"PRAGMA user_version = {cible}")


def connexion() -> sqlite3.Connection:
    con = sqlite3.connect(chemin_base())
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


@contextmanager
def base():
    """Ouvre une connexion, valide si tout va bien, ferme dans tous les cas."""
    con = connexion()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def initialiser() -> None:
    with base() as con:
        con.executescript(SCHEMA)
        migrer(con)
        for cle, valeur in (
            ("contraintes", CONTRAINTES_DEFAUT),
            ("personnes", "2"),

        ):
            con.execute(
                "INSERT OR IGNORE INTO reglage (cle, valeur) VALUES (?, ?)",
                (cle, valeur),
            )
