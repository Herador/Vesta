#!/bin/sh
# Sauvegarde quotidienne de la base.
#
# Pourquoi pas un simple `cp`: la base tourne en WAL (voir base.py). Les
# dernieres ecritures vivent alors dans un fichier -wal a cote du .db, et
# une copie brute du seul .db attrape une base incoherente ou en retard.
# `sqlite3 .backup` prend un instantane propre, meme pendant que l'app
# ecrit.
#
# Cron, tous les jours a 3h:
#   0 3 * * *  /home/pi/vesta/deploiement/sauvegarde.sh
set -eu

BASE="${VESTA_BASE:-/home/pi/vesta/donnees/garde-manger.db}"
DEST="${VESTA_SAUVEGARDES:-/home/pi/sauvegardes}"
GARDER=14   # jours d'historique conserves

mkdir -p "$DEST"
horodatage=$(date +%Y-%m-%d)
cible="$DEST/garde-manger-$horodatage.db"

sqlite3 "$BASE" ".backup '$cible'"
gzip -f "$cible"

# Purge des sauvegardes trop vieilles.
find "$DEST" -name 'garde-manger-*.db.gz' -mtime "+$GARDER" -delete

echo "Sauvegarde: $cible.gz"
