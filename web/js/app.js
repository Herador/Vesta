/* Le point d'entrée: on branche les écrans, puis on démarre.

   Chaque écran s'enregistre auprès de la navigation plutôt que d'être
   appelé par elle: c'est ce qui permet d'en ajouter un sans toucher au
   reste. */

import { $, api, etat, mot } from "./noyau.js";
import { aller, brancherEcran, dessinerOnglets } from "./navigation.js";
import { chargerStock, ouvrirSaisie } from "./vues/stock.js";
import { chargerIdees, chargerCuisines, dessinerTemps } from "./vues/menu.js";
import { chargerCarnet } from "./vues/carnet.js";
import { brancherReglages, chargerBilan } from "./vues/bilan.js";
import { chargerAliments } from "./vues/aliments.js";
import { editerRecette } from "./editeur.js";

brancherEcran("idees", chargerIdees);
brancherEcran("carnet", chargerCarnet);
brancherEcran("bilan", chargerBilan);
brancherEcran("aliments", chargerAliments);

$("btn-aliments").onclick = () => aller("aliments");
$("aliments-retour").onclick = () => aller("bilan");

$("ouvrir-saisie").onclick = () =>
  etat.onglet === "carnet" ? editerRecette(null) : ouvrirSaisie();

async function demarrer() {
  dessinerTemps();
  brancherReglages();
  dessinerOnglets();
  // Le carnet sert au compteur de l'accueil: on le compte une fois,
  // sans attendre que l'utilisateur ouvre l'onglet.
  api("/recettes").then((r) => {
    etat.nbRecettes = r.length;
    if (etat.onglet === "stock") chargerStock();
  }).catch(() => {});

  await chargerStock();
  chargerCuisines();

  // Un repas laissé en plan doit se retrouver: on cuisine, on pose le
  // téléphone, on y revient une heure plus tard.
  try {
    const encours = await api("/repas/en-cours");
    if (encours) {
      etat.repas = encours;
      mot(`${encours.titre} est en cours`);
    }
  } catch { /* sans conséquence */ }

  brancherServiceWorker();
}

/* Le service worker se met à jour tout seul.

   Sans ce qui suit, une nouvelle version restait en attente jusqu'à ce
   que tous les onglets soient fermés: on modifiait le code, on
   rechargeait, et rien ne changeait. Le plus déroutant étant que
   l'aperçu de l'éditeur, lui, montrait bien la modification. */
function brancherServiceWorker() {
  if (!("serviceWorker" in navigator)) return;

  navigator.serviceWorker.register("/sw.js").then((enregistrement) => {
    enregistrement.update();
    // Une version arrivée pendant la session prend la main aussitôt.
    enregistrement.addEventListener("updatefound", () => {
      const neuf = enregistrement.installing;
      if (!neuf) return;
      neuf.addEventListener("statechange", () => {
        if (neuf.state === "installed" && navigator.serviceWorker.controller) {
          neuf.postMessage({ action: "prendre-la-main" });
        }
      });
    });
  }).catch(() => {});

  // Quand la relève est faite, on recharge une fois pour repartir sur la
  // version fraîche. Le garde-fou évite la boucle de rechargements.
  let rechargeFaite = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (rechargeFaite) return;
    rechargeFaite = true;
    location.reload();
  });
}

demarrer();
