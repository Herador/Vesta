# Déploiement sur le Raspberry Pi

Trois choses à mettre en place : le service qui redémarre tout seul, la
sauvegarde quotidienne, l'accès HTTPS depuis le téléphone.

## 1. Le code

```bash
git clone <dépôt> /home/pi/vesta
cd /home/pi/vesta
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
mkdir -p donnees
.venv/bin/python -m outils.importer_recettes
.venv/bin/python -m outils.importer_ciqual Table_Ciqual_2025.xlsx
```

La base vit dans `donnees/garde-manger.db` (variable `VESTA_BASE`), à
l'écart du code : une mise à jour par `git pull` ne la touche jamais.

## 2. Le service

```bash
sudo cp deploiement/vesta.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vesta
systemctl status vesta
```

Le service écoute sur `127.0.0.1:8000` **et pas** `0.0.0.0` : l'accès
distant passe par Tailscale, qui parle au service en local. Rien n'est
exposé au réseau du domicile.

## 3. La sauvegarde

```bash
chmod +x deploiement/sauvegarde.sh
crontab -e
# ajouter :
0 3 * * *  /home/pi/vesta/deploiement/sauvegarde.sh
```

`sauvegarde.sh` utilise `sqlite3 .backup` et non une copie de fichier :
la base tourne en WAL, une copie brute du seul `.db` attrape une version
incohérente ou en retard. Restauration : `gunzip` le fichier voulu et
le remettre à la place de `garde-manger.db`, service arrêté.

## 4. Le HTTPS (Tailscale)

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
sudo tailscale serve --bg 8000
```

`tailscale serve` termine le TLS et transmet en clair au service local.
Le HTTPS débloque le service worker complet et l'accès à la caméra
(scan de code-barre).

## Mettre à jour

```bash
cd /home/pi/vesta
git pull
.venv/bin/pip install -r requirements.txt
sudo systemctl restart vesta
```

Les changements de schéma sont appliqués au démarrage (voir
`app/base.py`, `MIGRATIONS`). Une sauvegarde tourne de toute façon la
nuit, mais un `sauvegarde.sh` à la main avant une grosse mise à jour ne
coûte rien.
