/* Le noyau: ce dont tous les écrans ont besoin.

   Constantes, appels réseau, panneau modal, messages, mise en forme.
   Rien ici ne connaît un écran en particulier: c'est ce qui permet
   d'ouvrir n'importe quel autre module sans traîner tout le reste. */

export const $ = (id) => document.getElementById(id);

export const LIEUX = ["frigo", "congelo", "placard"];
export const UNITES = [
  { code: "", nom: "pièce" },
  { code: "g", nom: "g" },
  { code: "kg", nom: "kg" },
  { code: "ml", nom: "ml" },
  { code: "l", nom: "l" },
];
export const TEMPS = [
  { v: null, nom: "Peu importe" },
  { v: 20, nom: "20 min" },
  { v: 30, nom: "30 min" },
  { v: 45, nom: "45 min" },
  { v: 60, nom: "1 h" },
  { v: 90, nom: "1 h 30" },
  { v: 120, nom: "2 h" },
  { v: 180, nom: "3 h" },
];
export const ONGLETS = [
  // `id` nomme l'écran, `picto` le tracé: les deux diffèrent pour le
  // menu, dont l'écran s'appelle "idees" depuis le début.
  { id: "stock", picto: "stock", nom: "Stock" },
  { id: "idees", picto: "menu", nom: "Menu" },
  { id: "carnet", picto: "carnet", nom: "Carnet" },
  { id: "bilan", picto: "bilan", nom: "Bilan" },
];

export const etat = {
  onglet: "stock",
  stock: [],
  filtre: "tout",
  filtreIdees: "tout",
  filtreCarnet: "tout",
  carnet: [],
  lieuSaisie: "frigo",
  uniteSaisie: "g",
  codeCiqual: null,
  tempsIA: null,
  repas: null,
  remarques: {},   // par recette: ce qui manque, ce qui cloche
  imposes: [],     // ids du stock à utiliser absolument
  nbRecettes: 0,
};

/* ------------------------------------------------------------- réseau */

export async function api(chemin, options = {}) {
  const reponse = await fetch("/api" + chemin, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.corps ? JSON.stringify(options.corps) : undefined,
  });
  if (reponse.status === 204) return null;
  const donnees = await reponse.json().catch(() => null);
  if (!reponse.ok) {
    const detail = donnees && donnees.detail;
    throw new Error(
      typeof detail === "string" ? detail
        : detail && detail.message ? detail.message
        : "Le serveur n'a pas répondu comme prévu."
    );
  }
  return donnees;
}

let motEnCours;
export function mot(texte) {
  clearTimeout(motEnCours);
  const ancien = document.querySelector(".mot");
  if (ancien) ancien.remove();
  const el = document.createElement("div");
  el.className = "mot";
  el.textContent = texte;
  el.setAttribute("role", "status");
  document.body.appendChild(el);
  motEnCours = setTimeout(() => el.remove(), 3200);
}

/* ------------------------------------------------------------ panneau */

export function panneau(html) {
  const m = $("modale");
  m.innerHTML = `<div class="voile"><div class="panneau"><div class="poignee"></div>${html}</div></div>`;
  m.querySelector(".voile").onclick = (e) => {
    if (e.target === m.querySelector(".voile")) fermer();
  };
  // Le fond ne défile plus tant que le panneau est ouvert: sans ça, on
  // se retrouvait avec deux ascenseurs, celui du panneau et celui de la
  // page derrière.
  document.body.classList.add("panneau-ouvert");
  return m.querySelector(".panneau");
}
export function fermer() {
  $("modale").innerHTML = "";
  document.body.classList.remove("panneau-ouvert");
}
document.addEventListener("keydown", (e) => { if (e.key === "Escape") fermer(); });

export function echappe(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}


export const PARTIES = ["plat", "sauce", "marinade", "accompagnement", "garniture"];

/** Un nombre lisible: virgule décimale, et pas de 0,5555555 brocoli. */
export function nombre(v) {
  if (v === null || v === undefined || !Number.isFinite(v)) return "";
  const arrondi = v >= 10 ? Math.round(v) : Math.round(v * 100) / 100;
  return Number.isInteger(arrondi) ? String(arrondi)
    : String(arrondi).replace(".", ",");
}

/** Des secondes en minutes:secondes, pour les minuteurs. */
export function format(s) {
  const m = Math.floor(s / 60), r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

/** L'unité de saisie correspondant à une famille de quantités. */
export function uniteDe(famille) {
  return famille === "masse" ? "g" : famille === "volume" ? "ml" : "";
}
