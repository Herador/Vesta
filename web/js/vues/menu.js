/* L'écran des suggestions, et l'assistant qui invente une recette. */

import { $, TEMPS, api, etat, mot } from "../noyau.js";
import { ouvrirRecette } from "../recette.js";

/* --------------------------------------------------------- suggestions */

export async function chargerIdees() {
  const zone = $("liste-idees");
  zone.innerHTML = `<div class="charge"><span>On regarde ce qui presse</span></div>`;
  const pistes = await api("/suggestions?limite=8");

  const cuisines = [...new Set(pistes.map((p) => p.recette.cuisine).filter(Boolean))].sort();
  const f = $("filtres-idees");
  f.innerHTML = "";
  [["tout", "Tout"], ...cuisines.map((c) => [c, c])].forEach(([cle, nom]) => {
    const b = document.createElement("button");
    b.className = "puce";
    b.textContent = nom;
    b.setAttribute("aria-pressed", etat.filtreIdees === cle);
    b.onclick = () => { etat.filtreIdees = cle; chargerIdees(); };
    f.appendChild(b);
  });

  const visibles = pistes.filter(
    (p) => etat.filtreIdees === "tout" || p.recette.cuisine === etat.filtreIdees);

  zone.innerHTML = "";
  if (!visibles.length) {
    zone.innerHTML = `<div class="vide"><b>Rien ne ressort</b>Ajoute des articles au stock, ou demande à l'assistant plus bas.</div>`;
    return;
  }

  visibles.forEach((p) => {
    const b = document.createElement("button");
    b.className = "piste";
    b.innerHTML = `<h3></h3><div class="pourquoi"></div><div class="infos"></div>`;
    b.querySelector("h3").textContent = p.recette.titre;
    b.querySelector(".pourquoi").textContent = p.pourquoi;
    const infos = b.querySelector(".infos");
    const jeton = (texte, classe = "") => {
      const s = document.createElement("span");
      s.className = "jeton " + classe;
      s.textContent = texte;
      infos.appendChild(s);
    };
    if (p.recette.temps_min) jeton(p.recette.temps_min + " min");
    if (p.recette.cuisine) jeton(p.recette.cuisine);
    if (p.manquants.length) jeton("manque " + p.manquants.join(", "), "manque");
    b.onclick = () => ouvrirRecette(p.recette.id);
    zone.appendChild(b);
  });
}

/* -------------------------------------------------------- assistant */

export async function chargerCuisines() {
  try {
    const { continents } = await api("/ia/cuisines");
    const select = $("ia-cuisine");
    Object.entries(continents).forEach(([continent, liste]) => {
      const groupe = document.createElement("optgroup");
      groupe.label = continent;
      const tout = document.createElement("option");
      tout.value = continent;
      tout.textContent = "Au hasard en " + continent;
      groupe.appendChild(tout);
      liste.forEach((c) => {
        const o = document.createElement("option");
        o.value = c; o.textContent = c;
        groupe.appendChild(o);
      });
      select.appendChild(groupe);
    });
  } catch { /* assistant non configuré */ }
}

export function dessinerTemps() {
  const zone = $("ia-temps");
  zone.innerHTML = "";
  TEMPS.forEach((t) => {
    const b = document.createElement("button");
    b.className = "puce";
    b.textContent = t.nom;
    b.setAttribute("aria-pressed", etat.tempsIA === t.v);
    b.onclick = () => { etat.tempsIA = t.v; dessinerTemps(); };
    zone.appendChild(b);
  });
}

$("ia-lancer").onclick = async () => {
  const bouton = $("ia-lancer");
  bouton.disabled = true;
  bouton.textContent = "L'assistant cherche…";
  try {
    const corps = { portions: 2 };
    if ($("ia-cuisine").value) corps.cuisine = $("ia-cuisine").value;
    if (etat.tempsIA) corps.temps_max = etat.tempsIA;
    const r = await api("/ia/recette", { method: "POST", corps });
    if (r.retires_du_stock_absent && r.retires_du_stock_absent.length) {
      mot("Écarté faute de stock: " + r.retires_du_stock_absent.join(", "));
    }
    ouvrirRecette(r.recette.id);
  } catch (e) {
    mot(e.message);
  } finally {
    bouton.disabled = false;
    bouton.textContent = "Invente-moi quelque chose";
  }
};

