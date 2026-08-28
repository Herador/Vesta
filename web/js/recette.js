/* Tout ce qui touche à une recette qu'on va cuisiner.

   Trois moments dans un seul module parce qu'ils se passent le relais
   sans interruption: la fiche qu'on lit, le mode cuisine plein écran, et
   le compte rendu qui décompte le stock. Les séparer les obligerait à
   s'appeler en rond. */

import { $, api, echappe, etat, fermer, format, mot, nombre, panneau, uniteDe }
  from "./noyau.js";
import { chargerStock } from "./vues/stock.js";
import { aller } from "./navigation.js";
import { editerRecette } from "./editeur.js";
import { commentaire, niveau } from "./reperes.js";

/* --------------------------------------------------- vue de cuisine */

let portions = 2;
let verrouEcran = null;

export async function ouvrirRecette(id, avecPortions) {
  portions = avecPortions || portions;
  const r = await api(`/recettes/${id}?portions=${portions}`);
  etat.recetteOuverte = r;
  const vue = $("vue-cuisine");

  const parties = {};
  r.ingredients.forEach((i) => {
    (parties[i.partie] ||= []).push(i);
  });
  const ORDRE = ["plat", "marinade", "sauce", "accompagnement", "garniture"];
  const NOMS = {
    plat: "Le plat", marinade: "La marinade", sauce: "La sauce",
    accompagnement: "L'accompagnement", garniture: "La finition",
  };

  vue.innerHTML = `
    <div class="cuisine">
      <div class="page">
        <div class="entete-cuisine">
          <button class="rond" id="c-retour" aria-label="Retour">‹</button>
          <span class="etiquette" style="flex:1">${echappe(r.cuisine || r.categorie)}${
            r.temps_min ? " · " + r.temps_min + " min" : ""}${
            r.essai ? " · essai" : ""}</span>
          <button class="rond" id="c-modifier" aria-label="Modifier la recette">✎</button>
        </div>
        <h1 style="font-size:26px;margin:18px 0 6px">${echappe(r.titre)}</h1>
        <p class="sous">${echappe(r.description || "")}</p>

        <div class="portions">
          <button class="rond" id="c-moins" aria-label="Moins">−</button>
          <span class="val" id="c-val"></span>
          <button class="rond" id="c-plus" aria-label="Plus">+</button>
        </div>

        <div id="c-avis"></div>
        <div id="c-ingredients"></div>

        <div id="c-apports"></div>

        <h2 style="margin-top:26px">La marche à suivre</h2>
        <div id="c-etapes"></div>

        ${r.note ? `<div class="bilan" style="margin-top:18px">
          <span class="etiquette">Le détail qui compte</span>
          <p style="margin:6px 0 0;font-size:14px">${echappe(r.note)}</p></div>` : ""}
      </div>
      <div class="barre-cuisine" id="c-barre"></div>
    </div>`;

  const avis = etat.remarques[r.id];
  if (avis && (avis.manquants.length || avis.remarques.length)) {
    $("c-avis").innerHTML = `<div class="avis">
      ${avis.manquants.length ? `<div><span class="etiquette">À acheter</span>
        <p>${echappe(avis.manquants.join(", "))}</p></div>` : ""}
      ${avis.remarques.length ? `<div><span class="etiquette">À savoir</span>
        <p>${echappe(avis.remarques.join(" "))}</p></div>` : ""}
    </div>`;
  }

  const zoneIng = $("c-ingredients");
  ORDRE.filter((p) => parties[p]).forEach((p) => {
    const bloc = document.createElement("div");
    bloc.className = "partie";
    bloc.innerHTML = `<h3>${NOMS[p]}</h3>`;
    parties[p].forEach((i) => {
      const l = document.createElement("div");
      l.className = "ing" + (i.essentiel ? "" : " facultatif");
      l.innerHTML = `<span class="n"></span><span class="q"></span>`;
      l.querySelector(".n").textContent = i.nom + (i.essentiel ? "" : " (facultatif)");
      // Le nom est déjà en face: "1 ail" deviendrait "ail … 1 ail".
      l.querySelector(".q").textContent =
        i.famille === "piece" ? nombre(i.quantite) : i.affichage;
      bloc.appendChild(l);
    });
    zoneIng.appendChild(bloc);
  });

  const zoneEtapes = $("c-etapes");
  (r.etapes || []).forEach((e, i) => {
    const el = document.createElement("div");
    el.className = "etape";
    el.innerHTML = `<div class="num">${i + 1}</div>
      <div style="flex:1"><div class="t"></div><div class="txt"></div></div>`;
    el.querySelector(".t").textContent = e.titre;
    el.querySelector(".txt").textContent = e.texte;
    if (e.secondes) {
      const t = document.createElement("button");
      t.className = "minuteur";
      t.dataset.total = e.secondes;
      t.textContent = "⏱ " + format(e.secondes);
      t.onclick = (ev) => { ev.stopPropagation(); basculerMinuteur(t); };
      el.querySelector("div:last-child").appendChild(t);
    }
    el.onclick = (ev) => {
      if (!ev.target.closest(".minuteur")) el.classList.toggle("faite");
    };
    zoneEtapes.appendChild(el);
  });

  chargerApports(id, portions);

  $("c-val").textContent = portions + (portions > 1 ? " personnes" : " personne");
  $("c-moins").onclick = () => { if (portions > 1) ouvrirRecette(id, portions - 1); };
  $("c-plus").onclick = () => { if (portions < 12) ouvrirRecette(id, portions + 1); };
  $("c-retour").onclick = fermerCuisine;
  $("c-modifier").onclick = () => editerRecette(r);
  dessinerBarreCuisine(id);
  garderEcranAllume();
}

/* ------------------------------------------------- mode cuisine plein écran */

let modeCuisine = null;

export function lancerModeCuisine(recette) {
  const etapes = recette.etapes || [];
  if (!etapes.length) return mot("Cette recette n'a pas d'étapes détaillées.");
  modeCuisine = { recette, index: 0, faites: new Set(), minuteurs: {} };
  dessinerModeCuisine();
  garderEcranAllume();
}

function dessinerModeCuisine() {
  const { recette, index, faites } = modeCuisine;
  const etapes = recette.etapes;
  const e = etapes[index];
  const dernier = index === etapes.length - 1;

  const zone = document.createElement("div");
  zone.className = "plein";
  zone.innerHTML = `
    <div class="plein-haut">
      <button class="rond" id="p-quitter" aria-label="Quitter le mode cuisine">✕</button>
      <span class="titre">${echappe(recette.titre)}</span>
      <button class="rond" id="p-ingredients" aria-label="Voir les ingrédients">☰</button>
    </div>
    <div class="jauge">${etapes.map((_, i) =>
      `<i class="${faites.has(i) ? "faite" : i === index ? "ici" : ""}"></i>`).join("")}</div>
    <div class="plein-corps">
      <div class="rang">Étape ${index + 1} sur ${etapes.length}</div>
      <h2></h2>
      <p></p>
    </div>
    <div class="plein-bas">
      <button class="rond" id="p-prec" aria-label="Étape précédente"${
        index === 0 ? " disabled" : ""}>‹</button>
      <button class="btn" id="p-suivant">${
        dernier ? "J'ai fini de cuisiner" : "Étape suivante"}</button>
    </div>`;

  document.getElementById("vue-plein")?.remove();
  zone.id = "vue-plein";
  document.body.appendChild(zone);

  zone.querySelector("h2").textContent = e.titre;
  zone.querySelector("p").textContent = e.texte;

  if (e.secondes) {
    const t = document.createElement("button");
    t.className = "minuteur";
    t.dataset.total = e.secondes;
    const reste = modeCuisine.minuteurs[index];
    t.textContent = "⏱ " + format(reste ?? e.secondes);
    if (reste !== undefined) t.dataset.reste = reste;
    t.onclick = () => basculerMinuteur(t, index);
    zone.querySelector(".plein-corps").appendChild(t);
  }

  zone.querySelector("#p-quitter").onclick = quitterModeCuisine;
  zone.querySelector("#p-ingredients").onclick = () => rappelIngredients(recette);
  zone.querySelector("#p-prec").onclick = () => {
    if (modeCuisine.index > 0) { modeCuisine.index -= 1; dessinerModeCuisine(); }
  };
  zone.querySelector("#p-suivant").onclick = () => {
    modeCuisine.faites.add(modeCuisine.index);
    if (dernier) { quitterModeCuisine(); ouvrirCompteRendu(); }
    else { modeCuisine.index += 1; dessinerModeCuisine(); }
  };
}

function quitterModeCuisine() {
  document.getElementById("vue-plein")?.remove();
  modeCuisine = null;
}

function rappelIngredients(recette) {
  const p = panneau(`<h2>Les ingrédients</h2>
    <p class="sous">Pour ${recette.portions} personne${recette.portions > 1 ? "s" : ""}</p>
    <div class="rappel" id="r-liste"></div>
    <button class="btn calme" id="r-ok" style="width:100%;margin-top:14px">Retour à la recette</button>`);
  const liste = $("r-liste");
  recette.ingredients.forEach((i) => {
    const l = document.createElement("div");
    l.className = "ing" + (i.essentiel ? "" : " facultatif");
    l.innerHTML = `<span class="n"></span><span class="q"></span>`;
    l.querySelector(".n").textContent = i.nom;
    l.querySelector(".q").textContent =
      i.famille === "piece" ? nombre(i.quantite) : i.affichage;
    liste.appendChild(l);
  });
  p.querySelector("#r-ok").onclick = fermer;
}

export function dessinerBarreCuisine(recetteId) {
  const barre = $("c-barre");
  if (!barre) return;
  const enCours = etat.repas && etat.repas.recette_id === recetteId;
  barre.innerHTML = enCours
    ? `<button class="btn calme" id="c-mode" style="flex:1">Mode cuisine</button>
       <button class="btn" id="c-fini" style="flex:1">J'ai fini</button>`
    : `<button class="btn" id="c-demarrer">Commencer la recette</button>`;
  if (enCours) {
    $("c-mode").onclick = () => lancerModeCuisine(etat.recetteOuverte);
    $("c-fini").onclick = ouvrirCompteRendu;
  } else {
    $("c-demarrer").onclick = () => demarrerRepas(recetteId);
  }
}

/* Ce que vaut une assiette. Les chiffres viennent de la table CIQUAL,
   jamais d'une estimation: quand un ingrédient n'y est pas rattaché, on
   le dit plutôt que de compléter au jugé. */
async function chargerApports(id, portions) {
  const zone = $("c-apports");
  if (!zone) return;
  try {
    const a = await api(`/recettes/${id}/apports?portions=${portions}`);
    const m = a.par_personne;
    if (!m.kcal) return (zone.innerHTML = "");

    const ignores = a.couverture.ignores.map((i) => i.nom);
    zone.innerHTML = `
      <div class="partie">
        <h3>Par personne</h3>
        <div class="chiffres">
          ${[["kcal", "kcal", Math.round(m.kcal), ""],
             ["proteines", "protéines", m.proteines, "g"],
             ["glucides", "glucides", m.glucides, "g"],
             ["lipides", "lipides", m.lipides, "g"],
             ["fibres", "fibres", m.fibres, "g"],
             ["sel", "sel", m.sel, "g"]]
            .map(([cle, l, v, u]) => {
              const mot = commentaire(cle, v);
              return `<div class="chiffre ${niveau(cle, v)}"><div class="v">${
                nombre(v)}<em>${u}</em></div><div class="l">${l}</div>${
                mot ? `<div class="reperes">${mot}</div>` : ""}</div>`;
            }).join("")}
        </div>
        ${ignores.length ? `<p class="sous" style="margin:2px 0 0">Sans ${
          echappe(ignores.join(", "))}, que je ne sais pas encore compter.</p>` : ""}
      </div>`;
  } catch {
    zone.innerHTML = "";   // table CIQUAL non importée: on n'affiche rien
  }
}

export async function fermerCuisine(abandonnable = true) {
  const r = etat.recetteOuverte;
  $("vue-cuisine").innerHTML = "";
  relacherEcran();

  // Une recette inventée qu'on n'a pas cuisinée ne mérite pas de rester
  // en base: elle serait invisible et personne ne la retrouverait.
  //
  // `abandonnable` vaut faux quand on sort d'un repas terminé: à ce
  // moment-là `etat.repas` a déjà été remis à zéro, et sans ce garde-fou
  // on effaçait la recette juste avant de demander si on la garde.
  if (abandonnable && r && r.essai
      && !(etat.repas && etat.repas.recette_id === r.id)) {
    await api(`/recettes/${r.id}`, { method: "DELETE" }).catch(() => {});
    mot("Essai abandonné. Relance l'assistant quand tu veux.");
  }
  etat.recetteOuverte = null;
  // Un repas peut rester en cours quand on ferme la vue: le bandeau
  // prend le relais pour qu'on puisse y revenir.
  rafraichirEncours();
}



function basculerMinuteur(btn, indexEtape) {
  if (btn._iv) {
    clearInterval(btn._iv); btn._iv = null;
    btn.classList.remove("tourne");
    btn.textContent = "⏱ " + format(parseInt(btn.dataset.reste || btn.dataset.total, 10));
    return;
  }
  let reste = parseInt(btn.dataset.reste || btn.dataset.total, 10);
  btn.classList.add("tourne"); btn.classList.remove("fini");
  btn._iv = setInterval(() => {
    reste -= 1;
    btn.dataset.reste = reste;
    // Le minuteur survit au passage à l'étape suivante: on lance souvent
    // une cuisson puis on enchaîne sur autre chose.
    if (modeCuisine && indexEtape !== undefined) modeCuisine.minuteurs[indexEtape] = reste;
    btn.textContent = "⏱ " + format(Math.max(reste, 0));
    if (reste <= 0) {
      clearInterval(btn._iv); btn._iv = null;
      delete btn.dataset.reste;
      btn.classList.remove("tourne"); btn.classList.add("fini");
      btn.textContent = "✓ C'est prêt";
      if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
    }
  }, 1000);
}

/* L'écran ne doit pas s'éteindre pendant qu'on cuisine, les mains sales. */
export async function garderEcranAllume() {
  try {
    if ("wakeLock" in navigator) verrouEcran = await navigator.wakeLock.request("screen");
  } catch { /* refusé ou non supporté: sans conséquence */ }
}
export function relacherEcran() {
  if (verrouEcran) { verrouEcran.release().catch(() => {}); verrouEcran = null; }
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && $("vue-cuisine").innerHTML) garderEcranAllume();
});

/* -------------------------------------------------------------- repas */

/* Le bandeau « repas en cours ».

   Un repas commencé et pas validé survit à la fermeture de l'app. Sans
   ce bandeau, il devenait pourtant introuvable dès qu'on quittait la
   vue de cuisine, et le serveur refusait tout nouveau repas (409). Il
   reste donc affiché sur tous les écrans tant que le compte rendu n'a
   pas été validé. */
export function rafraichirEncours() {
  const zone = $("encours");
  if (!zone) return;
  const r = etat.repas;
  document.body.classList.toggle("a-un-repas", !!r);

  if (!r) { zone.hidden = true; zone.innerHTML = ""; return; }

  zone.hidden = false;
  zone.innerHTML = `
    <div class="quoi">
      <b></b><span>Repas en cours, rien n'est encore décompté</span>
    </div>
    <button class="laisser" id="enc-laisser">Abandonner</button>
    <button class="reprendre" id="enc-reprendre">Reprendre</button>`;
  zone.querySelector("b").textContent = r.titre;
  $("enc-reprendre").onclick = () => {
    if (r.recette_id) ouvrirRecette(r.recette_id, r.portions);
    else mot("La recette de ce repas n'existe plus, mieux vaut l'abandonner.");
  };
  $("enc-laisser").onclick = () => confirmerAbandon(r);
}

function confirmerAbandon(repas) {
  const p = panneau(`
    <span class="etiquette">Abandonner le repas</span>
    <h2 style="margin-top:6px">${echappe(repas.titre)}</h2>
    <p class="sous">Rien ne sera retiré du stock. Le repas est simplement effacé.</p>
    <div class="rangee" style="margin-top:16px">
      <button class="btn" id="ab-oui" style="flex:1">Oui, abandonner</button>
    </div>
    <button class="btn calme" id="ab-non" style="width:100%;margin-top:8px">Non, le garder</button>`);
  p.querySelector("#ab-non").onclick = fermer;
  p.querySelector("#ab-oui").onclick = async () => {
    await api(`/repas/${repas.id}`, { method: "DELETE" }).catch(() => {});
    etat.repas = null;
    fermer();
    rafraichirEncours();
    mot("Repas abandonné");
  };
}

export async function demarrerRepas(recetteId) {
  try {
    etat.repas = await api("/repas", {
      method: "POST", corps: { recette_id: recetteId, portions } });
    // On reste sur les étapes: c'est le moment où on cuisine, pas celui
    // où on compte ce qu'on a utilisé.
    dessinerBarreCuisine(recetteId);
    rafraichirEncours();
    lancerModeCuisine(etat.recetteOuverte);
  } catch (e) {
    if (e.message.includes("déjà en cours")) {
      etat.repas = await api("/repas/en-cours");
      dessinerBarreCuisine(recetteId);
      rafraichirEncours();
      mot("Un repas était déjà en cours, on le reprend.");
    } else mot(e.message);
  }
}

const FAMILLE_UNITE = { g: "masse", ml: "volume", "càs": "volume", "càc": "volume" };
const UNITE_FAMILLE = { masse: "g", volume: "ml", piece: "" };
const sansAccents = (s) =>
  s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

export function ouvrirCompteRendu() {
  const r = etat.repas;
  const p = panneau(`
    <span class="etiquette">Ce que tu as utilisé</span>
    <h2 style="margin-top:6px">${echappe(r.titre)}</h2>
    <p class="sous">Corrige les quantités si elles ont bougé, puis retire tout ça du stock.</p>

    <div class="cr-corps">
      <div id="cr-lignes"></div>

      <div class="cr-ajout">
        <label class="lab" for="cr-nom">Tu as ajouté autre chose ?</label>
        <div class="cr-nom-wrap">
          <input id="cr-nom" placeholder="poivron rouge" autocomplete="off">
          <div class="cr-suggest" id="cr-suggest" hidden></div>
        </div>
        <div class="cr-mesure-ajout">
          <input id="cr-qte" class="cr-qte" inputmode="decimal" placeholder="1" aria-label="Quantité">
          <div class="cr-unites" id="cr-unites" role="group" aria-label="Unité">
            <button type="button" data-u="" class="on">pièce</button>
            <button type="button" data-u="g">g</button>
            <button type="button" data-u="ml">ml</button>
            <button type="button" data-u="càs">c. à s.</button>
            <button type="button" data-u="càc">c. à c.</button>
          </div>
        </div>
        <button class="btn calme" id="cr-ajout-btn">Ajouter à la liste</button>
      </div>
    </div>

    <div class="cr-pied">
      <button class="btn" id="cr-valider">Retirer du stock</button>
      <button class="btn calme" id="cr-plus-tard">Je le ferai plus tard</button>
    </div>`);
  p.classList.add("panneau-cr");

  const zone = $("cr-lignes");
  const dessiner = () => {
    zone.innerHTML = "";
    r.lignes.forEach((l, i) => {
      // L'unité choisie l'emporte: une crème ajoutée en cuillères ne
      // doit pas se relire en millilitres.
      const unite = l.unite !== undefined
        ? (l.unite || "pc")
        : (uniteDe(l.famille) || (l.famille === "piece" ? "pc" : ""));
      // Deux paquets du même aliment sont un seul stock: quand on prend
      // tout, c'est le total qui part, pas seulement le paquet visé.
      const total = (l.disponible !== undefined && l.disponible !== null)
        ? l.disponible : null;

      const el = document.createElement("div");
      el.className = "cr-ligne" + (l.vider ? " videe" : "");
      el.innerHTML = `
        <div class="cr-tete">
          <span class="n"><span class="nom"></span></span>
          <span class="champ"><input inputmode="decimal" aria-label="Quantité utilisée"><em></em></span>
          <button class="sup" aria-label="Retirer de la liste">✕</button>
        </div>
        <div class="cr-bas">
          <button class="tout" aria-pressed="${!!l.vider}">${
            l.vider ? "Tout pris" : "J'ai tout pris"}</button>
        </div>`;

      el.querySelector(".nom").textContent = l.nom + (l.approx ? " ~" : "");
      el.querySelector("em").textContent = unite;

      if (l.paquets > 1 && total !== null) {
        el.querySelector(".n").insertAdjacentHTML("beforeend",
          `<span class="appoint">${nombre(total)} ${unite} en stock` +
          `, sur ${l.paquets} paquets</span>`);
      }

      const champ = el.querySelector("input");
      // Les conversions pièce vers gramme tombent juste rarement:
      // 0,5555555 brocoli n'aide personne à corriger quoi que ce soit.
      champ.value = nombre(l.quantite);
      champ.disabled = !!l.vider;
      champ.oninput = () => {
        const v = parseFloat(champ.value.replace(",", "."));
        r.lignes[i].quantite = Number.isFinite(v) ? v : null;
      };

      // Retirer la ligne: on n'a finalement pas utilisé cet ingrédient,
      // ou il ne vient pas du stock. Rien ne sera décompté.
      el.querySelector(".sup").onclick = () => {
        r.lignes.splice(i, 1);
        dessiner();
      };

      // "J'ai tout pris": on vide l'article, et la quantité affichée
      // passe à ce qu'il y avait vraiment en stock (4 pc de laitue
      // deviennent 6 si le frigo en contenait 6). Un second appui annule.
      el.querySelector(".tout").onclick = () => {
        const cible = r.lignes[i];
        cible.vider = !cible.vider;
        if (cible.vider) {
          cible.quantiteAvant = cible.quantite;
          if (total !== null) cible.quantite = total;
        } else if (cible.quantiteAvant !== undefined) {
          cible.quantite = cible.quantiteAvant;
        }
        dessiner();
      };

      zone.appendChild(el);
    });
  };
  dessiner();

  // L'unité: une rangée de pastilles, pas un menu déroulant natif qu'on
  // ne peut pas mettre au thème.
  let uAjout = "";
  const barreUnites = p.querySelector("#cr-unites");
  const choisirUnite = (u) => {
    uAjout = u;
    barreUnites.querySelectorAll("button").forEach(
      (b) => b.classList.toggle("on", b.dataset.u === u));
  };
  barreUnites.querySelectorAll("button").forEach(
    (b) => { b.onclick = () => choisirUnite(b.dataset.u); });

  // Suggestion depuis le stock: on tape « pou », on voit « Poulet » avec
  // ce qu'il en reste, et le choisir relie la ligne au bon article.
  let refAjout = null;
  const champNom = $("cr-nom");
  const boite = $("cr-suggest");
  const fermerSuggest = () => { boite.hidden = true; boite.innerHTML = ""; };

  champNom.oninput = () => {
    refAjout = null;
    const q = sansAccents(champNom.value.trim());
    const dejaLa = new Set(r.lignes.map((l) => l.cle).filter(Boolean));
    const trouve = q ? (etat.stock || []).filter(
      (a) => sansAccents(a.nom).includes(q) && !dejaLa.has(a.cle)).slice(0, 6) : [];
    if (!trouve.length) return fermerSuggest();

    boite.innerHTML = "";
    trouve.forEach((a) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "cr-sug";
      b.innerHTML = `<span></span><em>${echappe(a.affichage || "")}</em>`;
      b.querySelector("span").textContent = a.nom;
      b.onmousedown = (e) => e.preventDefault();   // garde le focus le temps du clic
      b.onclick = () => {
        champNom.value = a.nom;
        refAjout = a;
        choisirUnite(UNITE_FAMILLE[a.famille] ?? "");
        fermerSuggest();
        $("cr-qte").focus();
      };
      boite.appendChild(b);
    });
    boite.hidden = false;
    boite.scrollIntoView({ block: "nearest" });
  };
  champNom.addEventListener("blur", () => setTimeout(fermerSuggest, 120));

  const ajouter = () => {
    const nom = $("cr-nom").value.trim();
    if (!nom) return $("cr-nom").focus();
    const q = parseFloat($("cr-qte").value.replace(",", "."));
    const ligne = {
      nom, quantite: Number.isFinite(q) ? q : null,
      unite: uAjout, famille: FAMILLE_UNITE[uAjout] || "piece",
      stock_id: null, improvise: true,
    };
    // Choisi dans le stock: on relie la ligne à l'article, et on annonce
    // le total pour que « tout pris » enchaîne sur les autres paquets.
    if (refAjout && sansAccents(refAjout.nom) === sansAccents(nom)) {
      ligne.stock_id = refAjout.id;
      ligne.cle = refAjout.cle;
      ligne.famille = refAjout.famille || ligne.famille;
      const memes = (etat.stock || []).filter(
        (a) => a.cle === refAjout.cle && a.famille === refAjout.famille);
      if (memes.length && memes.every((a) => a.quantite != null)) {
        ligne.disponible = Math.round(
          memes.reduce((s, a) => s + a.quantite, 0) * 100) / 100;
        ligne.paquets = memes.length;
      }
    }
    r.lignes.push(ligne);
    $("cr-nom").value = ""; $("cr-qte").value = "";
    refAjout = null;
    fermerSuggest();
    dessiner();
    $("cr-nom").focus();
  };
  p.querySelector("#cr-ajout-btn").onclick = ajouter;
  ["cr-nom", "cr-qte"].forEach((id) =>
    $(id).addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); ajouter(); }
    }));
  p.querySelector("#cr-plus-tard").onclick = fermer;
  p.querySelector("#cr-valider").onclick = async () => {
    const lignes = r.lignes.map((l) => {
      const total = (l.disponible !== undefined && l.disponible !== null)
        ? l.disponible : null;
      // Tout pris sur plusieurs paquets: on envoie le total sans "vider",
      // pour que le serveur enchaîne d'un paquet à l'autre. Sur un seul
      // paquet, "vider" suffit et ne dépend d'aucune quantité connue.
      const cascade = l.vider && total !== null && l.paquets > 1;
      return {
        stock_id: l.stock_id || null,
        nom: l.nom,
        quantite: l.vider
          ? (total !== null ? total : null)
          : (Number.isFinite(l.quantite) ? l.quantite : null),
        // `unite` est celle qu'on a choisie en ajoutant un ingrédient, ou
        // celle du stock pour les lignes de la recette.
        unite: l.unite !== undefined ? l.unite : uniteDe(l.famille),
        vider: !!l.vider && !cascade,
      };
    });
    const bilan = await api(`/repas/${r.id}/terminer`, { method: "POST", corps: { lignes } });
    etat.repas = null;
    rafraichirEncours();
    fermer();
    await fermerCuisine(false);   // la recette vient d'être cuisinée
    await chargerStock();
    aller("stock");
    const n = bilan.retires.length;
    mot(n === 0 ? "Stock à jour"
      : n === 1 ? `Stock à jour, ${bilan.retires[0]} est épuisé`
      : `Stock à jour, ${n} articles épuisés`);
    if (bilan.a_decider) demanderSiOnGarde(bilan.a_decider);
  };
}

export function demanderSiOnGarde(recette) {
  const p = panneau(`
    <span class="etiquette">Recette inventée</span>
    <h2 style="margin-top:6px">${echappe(recette.titre)}</h2>
    <p class="sous">Tu viens de la cuisiner. Elle mérite d'entrer au carnet ?</p>
    <div class="rangee" style="margin-top:16px">
      <button class="btn" id="g-oui" style="flex:1">Je la garde</button>
    </div>
    <button class="btn calme" id="g-non" style="width:100%;margin-top:8px">Non, on oublie</button>`);
  p.querySelector("#g-oui").onclick = async () => {
    await api(`/recettes/${recette.id}/garder`, { method: "POST" });
    fermer(); mot("Ajoutée au carnet");
  };
  p.querySelector("#g-non").onclick = async () => {
    await api(`/recettes/${recette.id}`, { method: "DELETE" });
    fermer(); mot("Oubliée");
  };
}


