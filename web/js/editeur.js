/* L'écriture d'une recette: création, modification, suppression. */

import { $, PARTIES, api, echappe, fermer, mot, panneau, uniteDe }
  from "./noyau.js";
import { chargerCarnet } from "./vues/carnet.js";
import { fermerCuisine, ouvrirRecette } from "./recette.js";

/* --------------------------------------------------- écrire une recette */

export function editerRecette(recette) {
  // `recette` absent: on écrit une nouvelle recette.
  const brouillon = recette
    ? {
        id: recette.id,
        titre: recette.titre,
        cuisine: recette.cuisine || "",
        temps_min: recette.temps_min || 30,
        portions_base: recette.portions_base || 2,
        description: recette.description || "",
        note: recette.note || "",
        ingredients: recette.ingredients.map((i) => {
          // On revient aux quantités de base, et à l'unité d'origine:
          // 3 c. à soupe de crème doivent se relire ainsi, pas "45 ml".
          const echelle = recette.portions / recette.portions_base;
          const brut = i.quantite !== null ? i.quantite / echelle : null;
          const unite = i.unite || uniteDe(i.famille) || "";
          const diviseur = { "càs": 15, "càc": 5 }[unite] || 1;
          return {
            nom: i.nom,
            quantite: brut !== null ? Math.round((brut / diviseur) * 100) / 100 : null,
            unite,
            partie: i.partie || "plat",
            essentiel: i.essentiel !== false,
          };
        }),
        etapes: (recette.etapes || []).map((e) => ({ ...e })),
      }
    : {
        titre: "", cuisine: "", temps_min: 30, portions_base: 2,
        description: "", note: "",
        ingredients: [{ nom: "", quantite: null, unite: "g", partie: "plat", essentiel: true }],
        etapes: [{ titre: "", texte: "", secondes: null }],
      };

  const p = panneau(`
    <span class="etiquette">${recette ? "Modifier" : "Nouvelle recette"}</span>
    <h2 style="margin-top:6px" id="e-entete">${echappe(brouillon.titre || "À toi d'écrire")}</h2>

    <label class="lab">Titre</label>
    <input id="e-titre" placeholder="Poêlée de tofu au brocoli">
    <div class="champs" style="margin-top:12px">
      <input id="e-cuisine" placeholder="chinoise">
      <input id="e-temps" class="court" inputmode="numeric" placeholder="30">
    </div>
    <label class="lab">Pour combien de personnes</label>
    <input id="e-portions" inputmode="numeric">
    <label class="lab">En une phrase</label>
    <input id="e-description" placeholder="Ce que le plat a de particulier">

    <label class="lab">Ingrédients</label>
    <div id="e-ingredients"></div>
    <button class="btn calme" id="e-ajout-ing" style="width:100%;margin-top:8px">+ Un ingrédient</button>

    <label class="lab">Étapes</label>
    <div id="e-etapes"></div>
    <button class="btn calme" id="e-ajout-etape" style="width:100%;margin-top:8px">+ Une étape</button>

    <label class="lab">Le détail qui compte</label>
    <textarea id="e-note" rows="2" placeholder="Le tour de main, la variante"></textarea>

    <div class="rangee" style="margin-top:18px">
      <button class="btn" id="e-ok" style="flex:1">${
        recette ? "Enregistrer" : "Créer la recette"}</button>
    </div>
    ${recette ? `<button class="btn danger" id="e-supprimer" style="width:100%;margin-top:8px">Supprimer cette recette</button>` : ""}`);

  $("e-titre").value = brouillon.titre;
  $("e-cuisine").value = brouillon.cuisine;
  $("e-temps").value = brouillon.temps_min;
  $("e-portions").value = brouillon.portions_base;
  $("e-description").value = brouillon.description;
  $("e-note").value = brouillon.note;

  const dessinerIngredients = () => {
    const zone = $("e-ingredients");
    zone.innerHTML = "";
    brouillon.ingredients.forEach((i, k) => {
      const l = document.createElement("div");
      l.className = "edit-ing";
      l.innerHTML = `
        <input class="nom" placeholder="carotte">
        <div class="edit-ligne">
          <input class="q" inputmode="decimal" placeholder="2">
          <select class="u">${["", "g", "ml", "càs", "càc"]
            .map((u) => `<option value="${u}">${u || "pièce"}</option>`).join("")}</select>
          <select class="p">${PARTIES
            .map((x) => `<option value="${x}">${x}</option>`).join("")}</select>
          <button class="sup" aria-label="Retirer">×</button>
        </div>`;
      l.querySelector(".nom").value = i.nom;
      l.querySelector(".q").value = i.quantite ?? "";
      l.querySelector(".u").value = i.unite;
      l.querySelector(".p").value = i.partie;
      l.querySelector(".nom").oninput = (e) => { i.nom = e.target.value; };
      l.querySelector(".q").oninput = (e) => {
        const v = parseFloat(e.target.value.replace(",", "."));
        i.quantite = Number.isFinite(v) ? v : null;
      };
      l.querySelector(".u").onchange = (e) => { i.unite = e.target.value; };
      l.querySelector(".p").onchange = (e) => { i.partie = e.target.value; };
      l.querySelector(".sup").onclick = () => {
        brouillon.ingredients.splice(k, 1); dessinerIngredients();
      };
      zone.appendChild(l);
    });
  };

  const dessinerEtapes = () => {
    const zone = $("e-etapes");
    zone.innerHTML = "";
    brouillon.etapes.forEach((e, k) => {
      const l = document.createElement("div");
      l.className = "edit-etape";
      l.innerHTML = `
        <div class="edit-ligne">
          <input class="t" placeholder="La sauce">
          <input class="s" inputmode="numeric" placeholder="min">
          <button class="sup" aria-label="Retirer">×</button>
        </div>
        <textarea class="x" rows="3" placeholder="Mélanger 3 c. à soupe de sauce soja…"></textarea>`;
      l.querySelector(".t").value = e.titre || "";
      l.querySelector(".s").value = e.secondes ? Math.round(e.secondes / 60) : "";
      l.querySelector(".x").value = e.texte || "";
      l.querySelector(".t").oninput = (ev) => { e.titre = ev.target.value; };
      l.querySelector(".x").oninput = (ev) => { e.texte = ev.target.value; };
      l.querySelector(".s").oninput = (ev) => {
        const v = parseInt(ev.target.value, 10);
        e.secondes = Number.isFinite(v) && v > 0 ? v * 60 : null;
      };
      l.querySelector(".sup").onclick = () => {
        brouillon.etapes.splice(k, 1); dessinerEtapes();
      };
      zone.appendChild(l);
    });
  };

  dessinerIngredients();
  dessinerEtapes();

  p.querySelector("#e-ajout-ing").onclick = () => {
    brouillon.ingredients.push({ nom: "", quantite: null, unite: "g", partie: "plat", essentiel: true });
    dessinerIngredients();
  };
  p.querySelector("#e-ajout-etape").onclick = () => {
    brouillon.etapes.push({ titre: "", texte: "", secondes: null });
    dessinerEtapes();
  };

  if (recette) {
    p.querySelector("#e-supprimer").onclick = async () => {
      if (!confirm(`Supprimer "${recette.titre}" du carnet ?`)) return;
      await api(`/recettes/${recette.id}`, { method: "DELETE" });
      fermer(); fermerCuisine(); await chargerCarnet();
      mot("Recette supprimée");
    };
  }

  p.querySelector("#e-ok").onclick = async () => {
    const corps = {
      titre: $("e-titre").value.trim(),
      categorie: "plat",
      cuisine: $("e-cuisine").value.trim() || null,
      portions_base: parseInt($("e-portions").value, 10) || 2,
      temps_min: parseInt($("e-temps").value, 10) || null,
      description: $("e-description").value.trim(),
      note: $("e-note").value.trim() || null,
      ingredients: brouillon.ingredients.filter((i) => i.nom.trim()),
      etapes: brouillon.etapes.filter((e) => e.texte.trim()),
    };
    if (corps.titre.length < 2) return mot("Il faut un titre.");
    if (!corps.ingredients.length) return mot("Il faut au moins un ingrédient.");
    if (corps.etapes.length < 3) return mot("Il faut au moins trois étapes.");

    try {
      const enregistree = recette
        ? await api(`/recettes/${recette.id}`, { method: "PUT", corps })
        : await api("/recettes", { method: "POST", corps });
      fermer();
      await chargerCarnet();
      if (recette) ouvrirRecette(enregistree.id);
      else { fermerCuisine(); mot("Recette ajoutée au carnet"); }
    } catch (e) {
      mot(e.message);
    }
  };
}

