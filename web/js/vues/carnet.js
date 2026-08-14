/* L'écran du carnet: parcourir et filtrer les recettes gardées. */

import { $, api, etat } from "../noyau.js";
import { ouvrirRecette } from "../recette.js";

/* ------------------------------------------------------------ carnet */

export async function chargerCarnet() {
  etat.carnet = await api("/recettes");
  const zone = $("liste-carnet");
  const cuisines = [...new Set(etat.carnet.map((r) => r.cuisine).filter(Boolean))].sort();

  $("resume-carnet").textContent = `${etat.carnet.length} recettes`;
  const f = $("filtres-carnet");
  f.innerHTML = "";
  [["tout", "Tout"], ...cuisines.map((c) => [c, c])].forEach(([cle, nom]) => {
    const b = document.createElement("button");
    b.className = "puce";
    b.textContent = nom;
    b.setAttribute("aria-pressed", etat.filtreCarnet === cle);
    b.onclick = () => { etat.filtreCarnet = cle; chargerCarnet(); };
    f.appendChild(b);
  });

  const visibles = etat.carnet
    .filter((r) => etat.filtreCarnet === "tout" || r.cuisine === etat.filtreCarnet)
    .sort((a, b) => a.titre.localeCompare(b.titre));

  zone.innerHTML = "";
  visibles.forEach((r) => {
    const b = document.createElement("button");
    b.className = "piste";
    b.innerHTML = `<h3></h3><div class="pourquoi"></div><div class="infos"></div>`;
    b.querySelector("h3").textContent = r.titre;
    b.querySelector(".pourquoi").textContent = r.description || "";
    const infos = b.querySelector(".infos");
    [r.temps_min && r.temps_min + " min", r.cuisine, r.source === "ia" && "inventée"]
      .filter(Boolean).forEach((t) => {
        const s = document.createElement("span");
        s.className = "jeton"; s.textContent = t; infos.appendChild(s);
      });
    b.onclick = () => ouvrirRecette(r.id);
    zone.appendChild(b);
  });
}

