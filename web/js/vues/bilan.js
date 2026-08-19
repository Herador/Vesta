/* L'écran du bilan: les apports de la semaine et les réglages.

   Les chiffres viennent du calcul CIQUAL, jamais d'un modèle. Le
   commentaire, lui, est facultatif. */

import { $, api, echappe, fermer, mot, nombre, panneau } from "../noyau.js";
import { commentaire, niveau } from "../reperes.js";

/* -------------------------------------------------------------- bilan */

export async function chargerBilan() {
  const zone = $("contenu-bilan");
  try {
    const a = await api("/apports?jours=7");
    if (!a.repas) {
      zone.innerHTML = `<div class="vide"><b>Pas encore de repas</b>Cuisine une recette et valide son compte rendu, le bilan se remplira tout seul.</div>`;
      return;
    }
    const m = a.moyenne_par_repas;
    zone.innerHTML = `
      <div class="chiffres">
        ${[["kcal", "kcal", Math.round(m.kcal), ""],
           ["proteines", "protéines", m.proteines, "g"],
           ["glucides", "glucides", m.glucides, "g"],
           ["lipides", "lipides", m.lipides, "g"],
           ["fibres", "fibres", m.fibres, "g"],
           ["sel", "sel", m.sel, "g"]]
          .map(([cle, l, v, u]) => {
            const note = commentaire(cle, v);
            return `<div class="chiffre ${niveau(cle, v)}"><div class="v">${
              nombre(v)}<em>${u}</em></div><div class="l">${l}</div>${
              note ? `<div class="reperes">${note}</div>` : ""}</div>`;
          }).join("")}
      </div>
      <p class="sous">${a.repas} repas sur 7 jours · ${a.variete.aliments_distincts} aliments différents</p>
      ${a.non_comptes.length ? `<div class="bilan"><span class="etiquette">Non comptés</span>
        <p style="margin:6px 0 0;font-size:13.5px">${echappe(a.non_comptes.join(", "))}</p></div>` : ""}
      <button class="btn calme" id="b-commenter" style="width:100%;margin-top:12px">Demander un commentaire</button>
      <div id="b-commentaire"></div>`;

    $("b-commenter").onclick = async (e) => {
      e.target.disabled = true;
      e.target.textContent = "Lecture en cours…";
      try {
        const r = await api("/ia/bilan?jours=7");
        const c = r.commentaire;
        $("b-commentaire").innerHTML = `
          <div class="bilan" style="margin-top:12px">
            <p style="margin:0 0 10px">${echappe(c.constat)}</p>
            ${bloc("Ce qui va bien", c.points_forts)}
            ${bloc("À surveiller", c.a_surveiller)}
            ${bloc("Pistes", c.suggestions)}
          </div>`;
        e.target.remove();
      } catch (err) {
        mot(err.message);
        e.target.disabled = false;
        e.target.textContent = "Demander un commentaire";
      }
    };
  } catch (e) {
    zone.innerHTML = `<div class="alerte">${echappe(e.message)}</div>`;
  }
}

export function bloc(titre, items) {
  if (!items || !items.length) return "";
  return `<span class="etiquette">${titre}</span><ul>${
    items.map((i) => `<li>${echappe(i)}</li>`).join("")}</ul>`;
}

/* ----------------------------------------------------------- réglages */

/* -------------------------------------------------- réglages */

export function brancherReglages() {
  $("btn-reglages").onclick = async () => {
    const r = await api("/reglages");
    const p = panneau(`
      <h2>Mes réglages</h2>
      <label class="lab" for="r-contraintes">Ma façon de cuisiner</label>
      <textarea id="r-contraintes" rows="9"></textarea>
      <label class="lab" for="r-personnes">Nombre de personnes</label>
      <input id="r-personnes" type="number" min="1" max="12">
      <div class="rangee" style="margin-top:16px">
        <button class="btn" id="r-ok" style="flex:1">Enregistrer</button>
      </div>`);
    $("r-contraintes").value = r.contraintes;
    $("r-personnes").value = r.personnes;
    p.querySelector("#r-ok").onclick = async () => {
      await api("/reglages", {
        method: "PUT",
        corps: { contraintes: $("r-contraintes").value, personnes: parseInt($("r-personnes").value, 10) },
      });
      fermer(); mot("Réglages enregistrés");
    };
  };
}
