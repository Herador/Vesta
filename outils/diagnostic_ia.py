"""Diagnostic de la connexion au modèle.

    python -m outils.diagnostic_ia

Teste les points de rupture dans l'ordre où ils se produisent: lecture
du fichier, forme de la clé, certificat du réseau, authentification,
puis un vrai appel. Chaque étape dit ce qui ne va pas et quoi faire.

Aucune donnée n'est envoyée à part une requête minuscule, et la clé
n'est jamais affichée en entier.
"""

import json
import sys

import httpx

from app import ia

BASE = "https://api.mistral.ai/v1"


def masquer(cle: str) -> str:
    return f"{cle[:4]}…{cle[-4:]}" if len(cle) > 12 else "trop courte"


def etape(numero: int, titre: str) -> None:
    print(f"\n{numero}. {titre}")


def echec(message: str, conseil: str = "") -> None:
    print(f"   ÉCHEC: {message}")
    if conseil:
        print(f"   → {conseil}")
    sys.exit(1)


def main() -> None:
    print("Diagnostic de la connexion au modèle")
    print("=" * 42)

    # --- 1. le fichier
    etape(1, "Lecture du fichier .env")
    if not ia.FICHIER_ENV.exists():
        echec(f"{ia.FICHIER_ENV} n'existe pas.",
              "Renomme .env.exemple en .env et mets ta clé dedans.")
    brut = ia.FICHIER_ENV.read_bytes()
    print(f"   Trouvé: {ia.FICHIER_ENV} ({len(brut)} octets)")
    if brut.startswith(b"\xef\xbb\xbf"):
        print("   Note: le fichier commence par un BOM (Bloc-notes Windows).")
        print("   Sans effet ici, mais enregistre en UTF-8 sans BOM si tu peux.")

    # --- 2. la forme de la clé
    etape(2, "Forme de la clé")
    env = ia.lire_env()
    cle = env.get("IA_CLE", "")
    if not cle:
        lignes = [l.split("=")[0].strip() for l in
                  ia.FICHIER_ENV.read_text(encoding="utf-8", errors="replace").splitlines()
                  if "=" in l and not l.strip().startswith("#")]
        echec("Aucune valeur lue pour IA_CLE.",
              f"Clés vues dans le fichier: {lignes or 'aucune'}. "
              "La ligne doit être exactement IA_CLE=ta_clé, sans # devant.")

    print(f"   IA_CLE = {masquer(cle)} ({len(cle)} caractères)")
    suspects = [c for c in cle if not (c.isalnum() or c in "-_")]
    if suspects:
        echec(f"La clé contient des caractères inattendus: {set(suspects)}",
              "Retire guillemets, espaces et retours à la ligne. "
              "Recopie la clé depuis console.mistral.ai.")
    if len(cle) < 20:
        echec("La clé est anormalement courte.",
              "Tu as peut-être copié l'identifiant de la clé et non la clé "
              "elle-même. Sur console.mistral.ai, la valeur n'est affichée "
              "qu'une seule fois, à la création. Si tu l'as perdue, "
              "génère-en une nouvelle.")
    print("   Forme correcte.")

    # --- 3. le réseau
    etape(3, "Certificat du réseau")
    verify = ia.verifier_ssl(env)
    mode = {True: "vérification standard", False: "VÉRIFICATION DÉSACTIVÉE"}.get(
        verify, "magasin de certificats du système ou IA_CERT")
    print(f"   Mode: {mode}")
    if verify is False:
        print("   Attention: à retirer avant de déployer sur le Pi.")

    try:
        reponse = httpx.get(f"{BASE}/models",
                            headers={"Authorization": f"Bearer {cle}"},
                            timeout=30, verify=verify)
    except httpx.ConnectError as erreur:
        if "CERTIFICATE_VERIFY_FAILED" in str(erreur):
            echec("Le certificat du réseau est refusé.",
                  "pip install truststore, ou renseigne IA_CERT dans le .env.")
        echec(f"Connexion impossible: {erreur}",
              "Vérifie ta connexion, ou un éventuel proxy à déclarer.")
    except httpx.RequestError as erreur:
        echec(f"Requête impossible: {erreur}")
    print("   Connexion établie.")

    # --- 4. l'authentification
    etape(4, "Authentification")
    if reponse.status_code == 401:
        print(f"   Réponse du serveur: {reponse.text[:200]}")
        echec("La clé est refusée par Mistral.",
              "Trois causes, par ordre de fréquence:\n"
              "     a) Le numéro de téléphone n'est pas validé sur le compte. "
              "L'offre gratuite exige cette validation avant que la moindre "
              "clé fonctionne. Va dans console.mistral.ai, section "
              "Workspace puis Billing ou Plans, et valide ton numéro.\n"
              "     b) La clé vient d'être créée: attends deux ou trois "
              "minutes, l'activation n'est pas instantanée.\n"
              "     c) La clé appartient à un autre espace de travail, ou a "
              "été révoquée. Génère-en une nouvelle et recopie-la.")
    if reponse.status_code == 403:
        echec("Accès interdit pour cette clé.",
              "L'espace de travail n'a pas accès à l'API. Vérifie que le plan "
              "est bien activé sur console.mistral.ai.")
    if reponse.status_code == 429:
        echec("Quota atteint.", "Réessaie dans quelques minutes.")
    if reponse.status_code >= 400:
        echec(f"Erreur {reponse.status_code}: {reponse.text[:200]}")

    modeles = [m["id"] for m in reponse.json().get("data", [])]
    print(f"   Clé acceptée. {len(modeles)} modèles accessibles.")

    demande = env.get("IA_MODELE", ia.MODELE_DEFAUT)
    if modeles and demande not in modeles:
        proches = [m for m in modeles if "large" in m or "medium" in m][:5]
        print(f"   Attention: '{demande}' n'est pas dans la liste.")
        print(f"   Disponibles et adaptés: {proches}")
        print("   Renseigne IA_MODELE dans le .env avec l'un d'eux.")
    elif "large" in demande:
        print(f"   Modèle configuré: {demande}")
        print("   Attention: sur l'offre gratuite, mistral-large répond en "
              "60 à 120 s et dépasse souvent le délai (503). "
              "mistral-medium-latest répond en ~1 s pour une qualité proche.")
    else:
        print(f"   Modèle configuré: {demande}")

    # --- 5. un vrai appel
    etape(5, "Appel réel avec réponse JSON")
    try:
        resultat = ia.demander(
            'Réponds uniquement en JSON: {"ok": true, "mot": "..."}',
            "Donne-moi un mot au hasard.", max_tokens=60,
        )
    except ia.IAIndisponible as erreur:
        echec(str(erreur))
    print(f"   Réponse reçue: {json.dumps(resultat, ensure_ascii=False)[:120]}")

    # --- 6. la consommation
    etape(6, "Consommation relevée")
    try:
        from app import base as bdd
        with bdd.base() as con:
            l = con.execute(
                "SELECT usage, entree, sortie, secondes FROM appel_ia "
                "ORDER BY id DESC LIMIT 1").fetchone()
        if l:
            print(f"   Dernier appel: {l['entree']} tokens en entrée, "
                  f"{l['sortie']} en sortie, {l['secondes']} s.")
            print("   Détail complet: GET /api/ia/consommation")
        else:
            print("   Aucun appel enregistré: la table vient d'être créée.")
    except Exception as erreur:
        print(f"   Journal indisponible: {erreur}")

    print("\n" + "=" * 42)
    print("Tout fonctionne. Tu peux utiliser /api/ia/recette.")


if __name__ == "__main__":
    main()
