/* L'écran des aliments: relier ce qu'on cuisine aux fiches de l'ANSES.

   C'est de ce rattachement que dépendent tous les chiffres du bilan. Un
   aliment non relié est absent du calcul, ce qui se voit; un aliment mal
   relié le fausse en silence, ce qui ne se voit pas. D'où cet écran: les
   rapprochements automatiques y restent en attente jusqu'à ce qu'on les
   ait regardés. */

import { $, api, echappe, fermer, mot, nombre, panneau } from "../noyau.js";

let enAttente = [];

export async function chargerAliments() {
  const zone = $("contenu-aliments");
  zone.innerHTML = `<div class="charge"><span>Lecture des rattachements</span></div>`;

  try {
    const [attente, connus] = await Promise.all([
      api("/aliments/a-confirmer"),
      api("/aliments"),
    ]);
    enAttente = attente;
    dessiner(connus);
  } catch (e) {
    zone.innerHTML = `<div class="alerte">${echappe(e.message)}</div>`;
  }
}

function dessiner(connus) {
  const zone = $("contenu-aliments");
  const confirmes = connus.filter((a) => a.confirme);

  $("resume-aliments").textContent = connus.length
    ? `${connus.length} aliment${connus.length > 1 ? "s" : ""} relié${
        connus.length > 1 ? "s" : ""} à une fiche, ${confirmes.length} vérifié${
        confirmes.length > 1 ? "s" : ""} par toi`
    : "Aucun aliment relié pour le moment";

  zone.innerHTML = `
    <div class="compteurs">
      <div class="compteur"><div class="v">${connus.length}</div><div class="l">reliés</div></div>
      <div class="compteur ${enAttente.length ? "approche" : "calme"}">
        <div class="v">${enAttente.length}</div><div class="l">à vérifier</div></div>
      <div class="compteur calme"><div class="v">${confirmes.length}</div><div class="l">vérifiés</div></div>
    </div>
    <div id="liste-attente"></div>
    <div id="liste-connus"></div>`;

  dessinerAttente();
  dessinerConnus(connus);
}

/* ------------------------------------------------------- à vérifier */

function dessinerAttente() {
  const zone = $("liste-attente");
  if (!enAttente.length) {
    zone.innerHTML = `<div class="vide"><b>Tout est vérifié</b>Les valeurs du bilan
      s'appuient sur des fiches que tu as validées.</div>`;
    return;
  }

  zone.innerHTML = `<h2 style="margin-top:22px">À vérifier</h2>
    <p class="sous">L'application a proposé une fiche pour chacun. Confirme,
      corrige, ou passe. <br> Attention : il faut choisir l'aliment mesuré</p>
    <div class="liste" id="attente"></div>
    <button class="btn calme" id="tout-confirmer" style="width:100%;margin-top:12px">
      Tout confirmer d'un coup</button>`;

  const liste = $("attente");
  enAttente.forEach((a) => liste.appendChild(ligneAliment(a)));

  $("tout-confirmer").onclick = async () => {
    if (!confirm(`Confirmer les ${enAttente.length} rattachements proposés ?`)) return;
    await api("/aliments/tout-confirmer", { method: "POST" });
    mot("Rattachements confirmés");
    chargerAliments();
  };
}

function ligneAliment(a) {
  const el = document.createElement("button");
  el.className = "article";
  el.innerHTML = `
    <div class="corps">
      <div class="nom"></div>
      <div class="meta"></div>
    </div>
    <div class="action">›</div>`;
  el.querySelector(".nom").textContent = a.nom;
  el.querySelector(".meta").textContent = a.actuel
    ? `${a.actuel.libelle} · ${nombre(a.actuel.kcal)} kcal`
    : "aucune fiche proposée";
  el.onclick = () => ouvrirChoix(a);
  return el;
}

/* ------------------------------------------------ le choix d'une fiche */

function ouvrirChoix(a) {
  const p = panneau(`
    <span class="etiquette">${echappe(a.origine === "stock" ? "Dans ton stock" : "Dans tes recettes")}</span>
    <h2 style="margin-top:6px">${echappe(a.nom)}</h2>
    <p class="sous">Quelle fiche de la table CIQUAL correspond ? Les valeurs du
      bilan en dépendent.</p>

    <label class="lab">Propositions</label>
    <div id="ch-propositions"></div>

    <label class="lab">Chercher une autre fiche</label>
    <input id="ch-recherche" placeholder="fromage blanc nature" autocomplete="off">
    <div id="ch-resultats"></div>

    <details class="ch-manuel">
      <summary>Rien ne convient : saisir les valeurs à la main</summary>
      <p class="sous" style="margin:8px 0">Pour 100 g. Laisse vide ce que tu ne sais pas ;
        au minimum les kcal.</p>
      <div class="ch-grille">
        ${["kcal", "proteines", "glucides", "lipides", "fibres", "sel"].map((n) =>
          `<label>${n === "proteines" ? "protéines" : n}
             <input id="m-${n}" inputmode="decimal" placeholder="0"></label>`).join("")}
      </div>
      <button class="btn calme" id="m-enregistrer" style="width:100%;margin-top:10px">
        Enregistrer ces valeurs</button>
    </details>

    <div class="actions-collees">
      <button class="btn calme" id="ch-ia">Demander à l'assistant</button>
      <button class="btn calme" id="ch-ignorer">Ne pas compter cet aliment</button>
      <button class="btn calme" id="ch-passer">Passer pour l'instant</button>
    </div>`);

  dessinerFiches($("ch-propositions"), a.propositions, a);

  p.querySelector("#m-enregistrer").onclick = async () => {
    const corps = { libelle: a.nom };
    for (const n of ["kcal", "proteines", "glucides", "lipides", "fibres", "sel"]) {
      const v = parseFloat($("m-" + n).value.replace(",", "."));
      if (Number.isFinite(v) && v >= 0) corps[n] = v;
    }
    if (corps.kcal === undefined) return mot("Renseigne au moins les kcal.");
    await api(`/aliments/${encodeURIComponent(a.cle)}`, { method: "PUT", corps });
    fermer();
    mot(`${a.nom} : valeurs enregistrées`);
    chargerAliments();
  };

  p.querySelector("#ch-ignorer").onclick = async () => {
    await api(`/aliments/${encodeURIComponent(a.cle)}`,
              { method: "PUT", corps: { ignorer: true } });
    fermer();
    mot(`${a.nom} ne sera plus compté dans le bilan`);
    chargerAliments();
  };

  let minuteur;
  $("ch-recherche").oninput = () => {
    clearTimeout(minuteur);
    const q = $("ch-recherche").value.trim();
    if (q.length < 3) return ($("ch-resultats").innerHTML = "");
    minuteur = setTimeout(async () => {
      const fiches = await api(`/aliments/recherche?q=${encodeURIComponent(q)}&limite=6`);
      dessinerFiches($("ch-resultats"), fiches, a);
    }, 350);
  };

  p.querySelector("#ch-passer").onclick = fermer;
  p.querySelector("#ch-ia").onclick = async (e) => {
    e.target.disabled = true;
    e.target.textContent = "L'assistant regarde…";
    try {
      const r = await api(`/ia/aliment/${encodeURIComponent(a.cle)}`, { method: "POST" });
      fermer();
      mot(r.raison || `${a.nom} rattaché`);
      chargerAliments();
    } catch (err) {
      mot(err.message);
      e.target.disabled = false;
      e.target.textContent = "Demander à l'assistant";
    }
  };
}

function dessinerFiches(zone, fiches, aliment) {
  zone.innerHTML = "";
  if (!fiches || !fiches.length) {
    zone.innerHTML = `<p class="sous" style="margin:4px 0 0">Rien de probant.</p>`;
    return;
  }

  fiches.forEach((f) => {
    const choisie = aliment.actuel && aliment.actuel.reference === f.code;
    const el = document.createElement("button");
    el.className = "fiche" + (choisie ? " choisie" : "");
    el.innerHTML = `
      <div class="titre"></div>
      <div class="valeurs"></div>
      ${f.transforme ? `<div class="alerte-fiche">Aliment transformé: vérifie que
        c'est bien celui-là</div>` : ""}`;
    el.querySelector(".titre").textContent = f.nom;
    el.querySelector(".valeurs").textContent = [
      `${nombre(f.kcal)} kcal`,
      `${nombre(f.proteines)} g prot.`,
      `${nombre(f.lipides)} g lip.`,
      `${nombre(f.glucides)} g gluc.`,
    ].join("  ·  ");

    el.onclick = async () => {
      await api(`/aliments/${encodeURIComponent(aliment.cle)}`, {
        method: "PUT", corps: { code_ciqual: f.code },
      });
      fermer();
      mot(`${aliment.nom} → ${f.nom}`);
      chargerAliments();
    };
    zone.appendChild(el);
  });
}

/* --------------------------------------------------- déjà rattachés */

function dessinerConnus(connus) {
  const zone = $("liste-connus");
  const vus = connus.filter((a) => a.confirme);
  if (!vus.length) return (zone.innerHTML = "");

  zone.innerHTML = `<h2 style="margin-top:26px">Déjà vérifiés</h2>
    <p class="sous">Tape sur l'un d'eux pour changer sa fiche.</p>
    <div class="liste" id="connus"></div>`;

  const liste = $("connus");
  vus.sort((a, b) => a.cle.localeCompare(b.cle)).forEach((a) => {
    const el = document.createElement("button");
    el.className = "article";
    el.innerHTML = `<div class="corps"><div class="nom"></div>
      <div class="meta"></div></div><div class="action">›</div>`;
    el.querySelector(".nom").textContent = a.cle;
    el.querySelector(".meta").textContent = `${a.libelle} · ${nombre(a.kcal)} kcal`;
    el.onclick = () => ouvrirChoix({
      cle: a.cle, nom: a.cle, origine: "stock", actuel: a, propositions: [],
    });
    liste.appendChild(el);
  });
}
