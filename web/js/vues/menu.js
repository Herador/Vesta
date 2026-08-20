/* L'écran des suggestions, et l'assistant qui invente une recette. */

import { $, TEMPS, api, echappe, etat, fermer, mot, panneau } from "../noyau.js";
import { picto } from "../pictos.js";
import { ouvrirRecette } from "../recette.js";

/* Ce que tu veux absolument cuisiner. La consigne vaut pour les deux:
   le moteur local ne propose que des recettes qui l'utilisent, et
   l'assistant en fait le coeur de ce qu'il invente. */

export function dessinerAutour() {
  const zone = $("autour");
  const choisis = etat.stock.filter((a) => etat.imposes.includes(a.id));
  zone.innerHTML = "";

  const bouton = document.createElement("button");
  bouton.className = "puce";
  bouton.textContent = choisis.length ? "Changer" : "+ Cuisiner un ingrédient précis";
  bouton.onclick = ouvrirChoixAutour;

  choisis.forEach((a) => {
    const b = document.createElement("button");
    b.className = "puce";
    b.setAttribute("aria-pressed", "true");
    b.textContent = a.nom + "  ×";
    b.onclick = () => {
      etat.imposes = etat.imposes.filter((id) => id !== a.id);
      dessinerAutour(); chargerIdees();
    };
    zone.appendChild(b);
  });
  zone.appendChild(bouton);
}

function ouvrirChoixAutour() {
  const p = panneau(`
    <span class="etiquette">Autour de quoi</span>
    <h2 style="margin-top:6px">Qu'est-ce que tu veux passer ?</h2>
    <p class="sous">Les suggestions et l'assistant s'appuieront dessus. Le plus
      pressé est en haut.</p>
    <div class="liste" id="ch-liste"></div>
    <div class="actions-collees">
      <button class="btn" id="ch-ok">C'est parti</button>
      <button class="btn calme" id="ch-vider">Ne rien imposer</button>
    </div>`);

  const choix = new Set(etat.imposes);
  const liste = $("ch-liste");
  etat.stock.forEach((a) => {
    const el = document.createElement("button");
    el.className = "article " + a.etat;
    el.style.width = "100%";
    el.innerHTML = `<div class="compte">${picto(a.genre, 21)}</div>
      <div class="corps"><div class="nom"></div><div class="meta"></div></div>
      <div class="action"></div>`;
    const j = a.jours_restants;
    el.querySelector(".action").textContent = j === null ? "—" : j < 0 ? j+"j." : j === 0 ? "auj." : j+"j.";
    // el.querySelector(".u").textContent =
    //   j === null ? "—" : j < 0 ? j+"j." : j === 0 ? "auj." : j+"j." ;
    el.querySelector(".nom").textContent = a.nom;
    el.querySelector(".meta").textContent = [a.affichage, a.lieu].filter(Boolean).join("  ·  ");
    const marque = () => {
      // el.querySelector(".action").textContent = choix.has(a.id) ? "✓" : "";
      el.classList.toggle("sel", choix.has(a.id));
    };
    marque();
    el.onclick = () => { choix.has(a.id) ? choix.delete(a.id) : choix.add(a.id); marque(); };
    liste.appendChild(el);
  });

  p.querySelector("#ch-ok").onclick = () => {
    etat.imposes = [...choix];
    fermer(); dessinerAutour(); chargerIdees();
  };
  p.querySelector("#ch-vider").onclick = () => {
    etat.imposes = [];
    fermer(); dessinerAutour(); chargerIdees();
  };
}

/* --------------------------------------------------------- suggestions */

export async function chargerIdees() {
  const zone = $("liste-idees");
  zone.innerHTML = `<div class="charge"><span>On regarde ce qui presse</span></div>`;
  dessinerAutour();
  const filtre = etat.imposes.length ? `&imposes=${etat.imposes.join(",")}` : "";
  const pistes = await api(`/suggestions?limite=8${filtre}`);

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
    zone.innerHTML = etat.imposes.length
      ? `<div class="vide"><b>Aucune recette du carnet</b>Rien n'utilise tout ce que tu as choisi. Demande à l'assistant plus bas, il en inventera une.</div>`
      : `<div class="vide"><b>Rien ne ressort</b>Ajoute des articles au stock, ou demande à l'assistant plus bas.</div>`;
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
    if (etat.imposes.length) corps.imposes = etat.imposes;
    if ($("ia-cuisine").value) corps.cuisine = $("ia-cuisine").value;
    if (etat.tempsIA) corps.temps_max = etat.tempsIA;
    const r = await api("/ia/recette", { method: "POST", corps });
    // Ce qui manque et ce qui cloche accompagnent la recette au lieu de
    // la faire refuser: c'est à toi de voir si tu l'achètes ou si tu
    // passes à la suivante.
    etat.remarques[r.recette.id] = {
      manquants: r.manquants || [], remarques: r.remarques || [],
    };
    ouvrirRecette(r.recette.id);
  } catch (e) {
    mot(e.message);
  } finally {
    bouton.disabled = false;
    bouton.textContent = "Invente-moi quelque chose";
  }
};

