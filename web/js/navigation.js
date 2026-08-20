/* La barre du bas et le passage d'un écran à l'autre.

   Les écrans se chargent à la demande: inutile d'interroger le serveur
   pour un onglet que personne ne regarde. */

import { $, ONGLETS, etat } from "./noyau.js";
import { pictoOnglet } from "./pictos.js";

const chargeurs = {};

/** Chaque écran s'annonce ici au démarrage. Sans ce registre, ce module
    devrait importer tous les écrans, qui l'importent déjà: les imports
    tourneraient en rond. */
export function brancherEcran(nom, chargeur) {
  chargeurs[nom] = chargeur;
}

/* -------------------------------------------------------------- barre */

export function dessinerOnglets() {
  const nav = $("onglets");
  nav.innerHTML = "";
  const presses = etat.stock.filter(
    (a) => a.jours_restants !== null && a.jours_restants <= 1).length;

  ONGLETS.forEach((o) => {
    const b = document.createElement("button");
    b.innerHTML = `<span class="glyphe">${pictoOnglet(o.picto, 19)}</span>${o.nom}`;
    if (o.id === "stock" && presses) {
      b.insertAdjacentHTML("afterbegin", `<span class="pastille">${presses}</span>`);
    }
    if (etat.onglet === o.id) b.setAttribute("aria-current", "page");
    b.onclick = () => aller(o.id);
    nav.appendChild(b);
  });
}

export function aller(onglet) {
  etat.onglet = onglet;
  // Les aliments ne sont pas un onglet: on y entre depuis le bilan et
  // on en ressort par la flèche. Une cinquième icône en bas pour un
  // écran qu'on ouvre trois fois par an ne se justifiait pas.
  ONGLETS.forEach((o) => { $("page-" + o.id).hidden = o.id !== onglet; });
  $("page-aliments").hidden = onglet !== "aliments";
  $("ouvrir-saisie").hidden = !["stock", "carnet"].includes(onglet);
  $("ouvrir-saisie").title = onglet === "carnet" ? "Écrire une recette" : "Ajouter un article";
  dessinerOnglets();
  window.scrollTo(0, 0);
  if (chargeurs[onglet]) chargeurs[onglet]();
}

