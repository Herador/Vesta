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
import { editerRecette } from "./editeur.js";

brancherEcran("idees", chargerIdees);
brancherEcran("carnet", chargerCarnet);
brancherEcran("bilan", chargerBilan);

$("ouvrir-saisie").onclick = () =>
  etat.onglet === "carnet" ? editerRecette(null) : ouvrirSaisie();

async function demarrer() {
  dessinerTemps();
  brancherReglages();
  dessinerOnglets();
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

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
}

demarrer();
