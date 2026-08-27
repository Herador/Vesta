"""Le socle base de données: migrations de schéma.

Sur le Pi, la base survit aux mises à jour du code. Ajouter une colonne
doit donc marcher sur une base déjà en place sans casser une base neuve,
et sans rien rejouer deux fois.
"""

from app import base as bdd


def test_ajouter_colonne_est_idempotent():
    with bdd.base() as con:
        bdd.ajouter_colonne(con, "recette", "essai_bidon", "INTEGER DEFAULT 0")
        # un second passage ne doit pas lever "duplicate column name"
        bdd.ajouter_colonne(con, "recette", "essai_bidon", "INTEGER DEFAULT 0")
        assert "essai_bidon" in bdd.colonnes(con, "recette")


def test_migrer_pose_la_version_cible(monkeypatch):
    marque = []
    monkeypatch.setattr(bdd, "MIGRATIONS",
                        [(1, lambda con: marque.append(1)),
                         (2, lambda con: marque.append(2))])
    with bdd.base() as con:
        con.execute("PRAGMA user_version = 0")
        bdd.migrer(con)
        assert marque == [1, 2]
        assert con.execute("PRAGMA user_version").fetchone()[0] == 2

        # rejoué: plus rien à appliquer
        marque.clear()
        bdd.migrer(con)
        assert marque == []
