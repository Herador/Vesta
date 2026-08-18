/* L'écran du frigo: lister, ajouter, corriger, sortir du stock. */

import { $, LIEUX, UNITES, api, echappe, etat, fermer, mot, panneau }
  from "../noyau.js";
import { aller, dessinerOnglets } from "../navigation.js";
import { picto } from "../pictos.js";

/* -------------------------------------------------------------- stock */

/** Le décompte tel qu'il s'affiche à droite d'une ligne: "3j", "auj.". */
export function compteCourt(a) {
  const j = a.jours_restants;
  if (j === null) return "—";
  if (j < 0) return `-${Math.abs(j)}j`;
  if (j === 0) return "auj.";
  return `${j}j`;
}

export function libelleJours(a) {
  if (a.jours_restants === null) return { n: "—", u: "" };
  const j = a.jours_restants;
  if (j < 0) return { n: Math.abs(j), u: "dépassé" };
  if (j === 0) return { n: 0, u: "auj." };
  return { n: j, u: j === 1 ? "jour" : "jours" };
}

export async function chargerStock() {
  etat.stock = await api("/stock");
  dessinerStock();
  dessinerOnglets();
}

/** Bonsoir, bonjour: l'app s'ouvre surtout le soir, mais pas toujours. */
function salutation() {
  const h = new Date().getHours();
  if (h < 6) return "Bonne nuit";
  if (h < 12) return "Bonjour";
  if (h < 18) return "Bon après-midi";
  return "Bonsoir";
}

/* La carte de tête: ce qui presse le plus, en grand, avec le geste qui
   va avec. C'est la seule chose à lire quand on ouvre l'app en rentrant.
   Quand rien ne presse, elle change de ton plutôt que de disparaître. */
function dessinerUne() {
  const zone = $("une");
  const presses = etat.stock
    .filter((a) => a.jours_restants !== null && a.jours_restants <= 2)
    .sort((a, b) => a.jours_restants - b.jours_restants);

  if (!etat.stock.length) return (zone.innerHTML = "");

  const el = document.createElement("button");
  if (presses.length) {
    const a = presses[0];
    const autres = presses.length - 1;
    el.className = "une";
    el.innerHTML = `
      <div class="quoi">${a.jours_restants <= 0 ? "À passer aujourd'hui" : "À passer demain"}</div>
      <h2></h2>
      <div class="detail"></div>
      <span class="agir">Voir les idées →</span>`;
    el.querySelector("h2").textContent = a.nom;
    el.querySelector(".detail").textContent =
      [a.affichage, autres > 0 ? `et ${autres} autre${autres > 1 ? "s" : ""} qui suivent` : null]
        .filter(Boolean).join("  ·  ");
    el.onclick = () => {
      etat.imposes = [a.id];
      aller("idees");
    };
  } else {
    el.className = "une calme-fond";
    el.innerHTML = `
      <div class="quoi">Rien ne presse</div>
      <h2>Tout est sous contrôle</h2>
      <div class="detail">Prends une idée au hasard dans le carnet</div>
      <span class="agir">Voir le menu →</span>`;
    el.onclick = () => aller("idees");
  }
  zone.innerHTML = "";
  zone.appendChild(el);
}

function dessinerCompteurs() {
  const presses = etat.stock.filter(
    (a) => a.jours_restants !== null && a.jours_restants <= 4).length;
  $("compteurs").innerHTML = `
    <div class="compteur"><div class="v">${etat.stock.length}</div><div class="l">articles</div></div>
    <div class="compteur approche"><div class="v">${presses}</div><div class="l">à sauver</div></div>
    <div class="compteur calme"><div class="v">${etat.nbRecettes || "—"}</div><div class="l">recettes</div></div>`;
}

export function dessinerStock() {
  const presses = etat.stock.filter(
    (a) => a.jours_restants !== null && a.jours_restants <= 2).length;
  $("salut").textContent = salutation();
  $("resume-stock").textContent = etat.stock.length === 0
    ? "Rien en stock pour le moment"
    : `${etat.stock.length} articles` + (presses ? `, ${presses} à passer bientôt` : "");
  dessinerUne();
  dessinerCompteurs();

  const f = $("filtres");
  f.innerHTML = "";
  [["tout", "Tout"], ["a_sauver", "À sauver"], ["frigo", "Frigo"],
   ["congelo", "Congélo"], ["placard", "Placard"]].forEach(([cle, nom]) => {
    const b = document.createElement("button");
    b.className = "puce";
    b.textContent = nom;
    b.setAttribute("aria-pressed", etat.filtre === cle);
    b.onclick = () => { etat.filtre = cle; dessinerStock(); };
    f.appendChild(b);
  });

  const visibles = etat.stock.filter((a) => {
    if (etat.filtre === "tout") return true;
    if (etat.filtre === "a_sauver") return a.jours_restants !== null && a.jours_restants <= 4;
    return a.lieu === etat.filtre;
  });

  const L = $("liste-stock");
  L.innerHTML = "";
  if (!visibles.length) {
    L.innerHTML = etat.stock.length
      ? `<div class="vide"><b>Rien sous ce filtre</b>Choisis un autre rayon.</div>`
      : `<div class="vide"><b>Les placards sont vides</b>Ajoute ce que tu as, avec sa date quand tu la connais.</div>`;
    return;
  }

  visibles.forEach((a) => {
    const el = document.createElement("button");
    el.className = "article " + a.etat;
    el.innerHTML = `
      <div class="compte">${picto(a.genre, 21)}</div>
      <div class="corps"><div class="nom"></div><div class="meta"></div></div>
      <div class="action"></div>`;
    el.querySelector(".nom").textContent = a.nom;
    el.querySelector(".meta").textContent =
      [a.affichage, a.lieu].filter(Boolean).join("  ·  ");
    el.querySelector(".action").textContent = compteCourt(a);
    el.onclick = () => ouvrirArticle(a);
    L.appendChild(el);
  });
}

export function ouvrirArticle(a) {
  const p = panneau(`
    <span class="etiquette">${echappe(a.lieu)}</span>
    <h2 style="margin-top:6px">${echappe(a.nom)}</h2>
    <p class="sous">${a.affichage || "quantité non précisée"}${
      a.date_limite ? " · jusqu'au " + a.date_limite : ""}</p>
    <label class="lab">Où c'est rangé</label>
    <div class="rangee defile" id="a-lieux"></div>
    <label class="lab">Il en reste, et jusqu'à quand</label>
    <div class="champs">
      <input id="a-qte" inputmode="decimal" placeholder="${a.quantite ?? ""}">
      <input id="a-date" class="court" type="date" value="${a.date_limite || ""}">
    </div>
    ${a.date_estimee ? `<p class="sous" style="margin:-4px 0 0">Date estimée d'après
      l'aliment et son rangement. Corrige-la si tu as celle de l'emballage.</p>` : ""}
    <div class="rangee" style="margin-top:12px">
      <button class="btn" id="a-maj" style="flex:1">Mettre à jour</button>
    </div>
    <div class="rangee" style="margin-top:8px">
      <button class="btn calme" id="a-fini" style="flex:1">Il n'y en a plus</button>
      <button class="btn danger" id="a-jete" style="flex:1">Je l'ai jeté</button>
    </div>
    <button class="btn calme" id="a-supp" style="width:100%;margin-top:14px">Effacer, c'était une erreur</button>`);

  const unite = a.famille === "masse" ? "g" : a.famille === "volume" ? "ml" : "";

  // Déplacer un article recalcule sa date: congeler prolonge de plusieurs
  // mois, décongeler ramène à quelques jours. Le serveur s'en charge, à
  // condition que la date n'ait pas été saisie à la main.
  let lieuChoisi = a.lieu;
  const lieux = $("a-lieux");
  LIEUX.forEach((l) => {
    const b = document.createElement("button");
    b.className = "puce";
    b.textContent = l === "congelo" ? "Congélo" : l[0].toUpperCase() + l.slice(1);
    b.setAttribute("aria-pressed", lieuChoisi === l);
    b.onclick = () => {
      lieuChoisi = l;
      [...lieux.children].forEach((x) => x.setAttribute("aria-pressed", x === b));
    };
    lieux.appendChild(b);
  });

  p.querySelector("#a-maj").onclick = async () => {
    const corps = {};
    const q = $("a-qte").value.trim();
    if (q) { corps.quantite = parseFloat(q.replace(",", ".")); corps.unite = unite; }
    const d = $("a-date").value;
    if (d && d !== a.date_limite) corps.date_limite = d;
    if (lieuChoisi !== a.lieu) corps.lieu = lieuChoisi;
    if (!Object.keys(corps).length) return fermer();
    const maj = await api(`/stock/${a.id}`, { method: "PATCH", corps });
    fermer(); await chargerStock();
    mot(corps.lieu && maj.date_limite !== a.date_limite
      ? `Au ${maj.lieu}, à consommer avant le ${maj.date_limite}`
      : "Article mis à jour");
  };
  p.querySelector("#a-fini").onclick = () => sortir(a, false);
  p.querySelector("#a-jete").onclick = () => sortir(a, true);
  p.querySelector("#a-supp").onclick = async () => {
    await api(`/stock/${a.id}`, { method: "DELETE" });
    fermer(); await chargerStock(); mot("Saisie supprimée");
  };
}

export async function sortir(a, jete) {
  await api(`/stock/${a.id}/consomme`, { method: "POST", corps: { jete } });
  fermer(); await chargerStock();
  mot(jete ? `${a.nom} jeté, c'est noté` : `${a.nom} rayé de la liste`);
}

/* ------------------------------------------------------ saisie */

export function ouvrirSaisie() {
  panneau(`
    <span class="etiquette">Nouvel article</span>
    <h2 style="margin-top:6px">Qu'est-ce que tu ranges ?</h2>
    <div class="champs">
      <input id="f-nom" placeholder="Pavés de saumon" autocomplete="off" enterkeyhint="next">
      <input id="f-qte" class="court" placeholder="300" inputmode="decimal" autocomplete="off">
    </div>
    <div class="suggestions-ciqual" id="f-ciqual"></div>
    <label class="lab">Unité</label>
    <div class="rangee defile" id="f-unites"></div>
    <label class="lab">À consommer avant</label>
    <input id="f-date" type="date">
    <label class="lab">Où</label>
    <div class="rangee defile" id="f-lieux"></div>
    <button class="btn" id="f-ajouter" style="width:100%;margin-top:8px">Ajouter au stock</button>`);

  dessinerSaisie();
  brancherSaisie();
  setTimeout(() => $("f-nom").focus(), 60);
}

export function dessinerSaisie() {
  const lieux = $("f-lieux");
  if (!lieux) return;
  lieux.innerHTML = "";
  LIEUX.forEach((l) => {
    const b = document.createElement("button");
    b.className = "puce";
    b.textContent = l === "congelo" ? "Congélo" : l[0].toUpperCase() + l.slice(1);
    b.setAttribute("aria-pressed", etat.lieuSaisie === l);
    b.onclick = () => { etat.lieuSaisie = l; dessinerSaisie(); };
    lieux.appendChild(b);
  });

  const unites = $("f-unites");
  unites.innerHTML = "";
  UNITES.forEach((u) => {
    const b = document.createElement("button");
    b.className = "puce";
    b.textContent = u.nom;
    b.setAttribute("aria-pressed", etat.uniteSaisie === u.code);
    b.onclick = () => { etat.uniteSaisie = u.code; dessinerSaisie(); };
    unites.appendChild(b);
  });
}

let minuteurCiqual;

export function brancherSaisie() {
  $("f-nom").addEventListener("input", () => {
  clearTimeout(minuteurCiqual);
  etat.codeCiqual = null;
  const q = $("f-nom").value.trim();
  if (q.length < 3) return ($("f-ciqual").innerHTML = "");
  minuteurCiqual = setTimeout(async () => {
    try {
      const fiches = await api(`/ciqual?q=${encodeURIComponent(q)}&limite=3`);
      const zone = $("f-ciqual");
      zone.innerHTML = "";
      fiches.forEach((f) => {
        const b = document.createElement("button");
        b.textContent = f.nom;
        b.onclick = () => {
          etat.codeCiqual = f.code;
          zone.innerHTML = `<button aria-pressed="true">Rattaché à ${echappe(f.nom)}</button>`;
        };
        zone.appendChild(b);
      });
    } catch { /* la table CIQUAL n'est pas importée: sans conséquence */ }
    }, 350);
  });

  $("f-ajouter").onclick = ajouterArticle;
  ["f-nom", "f-qte"].forEach((id) =>
    $(id).addEventListener("keydown", (e) => {
      if (e.key === "Enter") ajouterArticle();
    }));
}

export async function ajouterArticle() {
  const nom = $("f-nom").value.trim();
  if (!nom) return $("f-nom").focus();
  const q = $("f-qte").value.trim().replace(",", ".");
  await api("/stock", {
    method: "POST",
    corps: {
      nom,
      quantite: q ? parseFloat(q) : null,
      unite: etat.uniteSaisie,
      lieu: etat.lieuSaisie,
      date_limite: $("f-date").value || null,
      code_ciqual: etat.codeCiqual,
    },
  });
  $("f-nom").value = ""; $("f-qte").value = ""; $("f-date").value = "";
  $("f-ciqual").innerHTML = ""; etat.codeCiqual = null;
  await chargerStock();
  mot(`${nom} ajouté`);
  $("f-nom").focus();
}

$("ouvrir-saisie").onclick = () =>
  etat.onglet === "carnet" ? editerRecette(null) : ouvrirSaisie();

