/* Les pictogrammes, dessinés à la main plutôt qu'empruntés.

   Une bibliothèque d'icônes chargée depuis un CDN serait plus fournie,
   mais sur un Raspberry Pi sans internet elle ne charge pas, et une
   icône absente vaut moins qu'une icône approximative. Ces dix-neuf
   symboles pèsent moins qu'une requête réseau.

   Chaque tracé tient dans une grille de 24, en trait de 1,6 pixel, sans
   remplissage: ils restent lisibles à 18 pixels comme à 40. */

const TRACES = {
  poisson: '<path d="M16 12c0 3-3 5.5-7 5.5S3 15 3 12s2-5.5 6-5.5 7 2.5 7 5.5z"/><path d="M16 12l5-4v8z"/><circle cx="7" cy="11" r=".9" fill="currentColor" stroke="none"/>',
  viande: '<path d="M8.5 4.5c6 0 11 3.2 11 7.5s-5 7.5-11 7.5c-3.4 0-5.5-1.8-5.5-4 0-1.2.7-2 .7-3.5S3 9.7 3 8.5c0-2.2 2.1-4 5.5-4z"/><circle cx="8.8" cy="12" r="2.5"/>',
  oeuf: '<path d="M12 3c3.6 0 6.5 5.4 6.5 9.5A6.5 6.5 0 0 1 5.5 12.5C5.5 8.4 8.4 3 12 3z"/><path d="M9 13a3 3 0 0 0 3 3"/>',
  laitage: '<path d="M8 3h8M9 3l-1 4v13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V7l-1-4"/><path d="M8.4 10h7.2"/>',
  champignon: '<path d="M4 11a8 8 0 0 1 16 0z"/><path d="M10 11v6a2 2 0 0 0 4 0v-6"/><path d="M9 20h6"/>',
  feuille: '<path d="M5 19c0-8 5-13 14-14 1 8-3 15-11 15-1 0-2 0-3-1z"/><path d="M9 15c2-3 4-5 7-6"/>',
  herbe: '<path d="M12 21V8"/><path d="M12 12c-4 0-6-2-6-6 4 0 6 2 6 6zM12 12c4 0 6-2 6-6-4 0-6 2-6 6z"/>',
  racine: '<path d="M12 21c-2-3-3.5-6-3.5-9S10 8 12 8s3.5 1 3.5 4-1.5 6-3.5 9z"/><path d="M12 8V4"/><path d="M12 6c-2-1-4-1-5-3 2-1 4 0 5 3zM12 6c2-1 4-1 5-3-2-1-4 0-5 3z"/>',
  legume: '<circle cx="12" cy="14.5" r="6.5"/><path d="M12 8V5"/><path d="M12 8c-2.2 0-3.6-.7-4.4-2.2 2-.7 3.6 0 4.4 2.2zM12 8c2.2 0 3.6-.7 4.4-2.2-2-.7-3.6 0-4.4 2.2z"/>',
  fruit: '<path d="M12 8c-4-2-8 1-8 5 0 4 3 8 5 8 1 0 2-1 3-1s2 1 3 1c2 0 5-4 5-8 0-4-4-7-8-5z"/><path d="M12 8V4M12 4c2 0 3-1 3-2"/>',
  legumineuse: '<circle cx="8" cy="10" r="3"/><circle cx="15" cy="8" r="2.4"/><circle cx="13" cy="16" r="3.4"/>',
  cereale: '<path d="M12 21V6"/><path d="M12 10c-3 0-4-2-4-5 3 0 4 2 4 5zM12 10c3 0 4-2 4-5-3 0-4 2-4 5z"/><path d="M12 16c-3 0-4-2-4-5 3 0 4 2 4 5zM12 16c3 0 4-2 4-5-3 0-4 2-4 5z"/>',
  pain: '<path d="M4 12c0-3 3-5 8-5s8 2 8 5v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/><path d="M8 12v7M12 12v7M16 12v7"/>',
  graine: '<path d="M9.5 4C6.5 4 5 6 5 8.5c0 1.8.8 2.6.8 3.5S5 13.7 5 15.5C5 18 6.5 20 9.5 20s4.5-2 4.5-4.5c0-1.8-.8-2.6-.8-3.5s.8-1.7.8-3.5C14 6 12.5 4 9.5 4z"/><path d="M17 9c2 0 3 1.4 3 3s-1 3-3 3"/>',
  condiment: '<path d="M10 3h4v3l2 3v11a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V9l2-3z"/><path d="M8 13h8"/>',
  epice: '<path d="M9 3h6l-1 5H10z"/><path d="M8 8h8l1 12a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1z"/><path d="M10 13h4M10 17h4"/>',
  conserve: '<ellipse cx="12" cy="6" rx="7" ry="2.5"/><path d="M5 6v12c0 1.4 3 2.5 7 2.5s7-1.1 7-2.5V6"/><path d="M5 12c0 1.4 3 2.5 7 2.5s7-1.1 7-2.5"/>',
  sucre: '<path d="M7 9h10a1 1 0 0 1 1 1v9a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2v-9a1 1 0 0 1 1-1z"/><path d="M8 9V7.5a1.5 1.5 0 0 1 1.5-1.5h5A1.5 1.5 0 0 1 16 7.5V9"/><path d="M9 3.4c1.4.7 4.6.7 6 0"/><path d="M8.5 14.5c1.2-1 2-1 3 0s1.9 1 3 0"/>',
  autre: '<rect x="4" y="7" width="16" height="13" rx="1.5"/><path d="M9 7V5a3 3 0 0 1 6 0v2"/>',
};

/** Le pictogramme d'une famille, en SVG prêt à insérer. */
export function picto(genre, taille = 20) {
  const trace = TRACES[genre] || TRACES.autre;
  return `<svg viewBox="0 0 24 24" width="${taille}" height="${taille}"
    fill="none" stroke="currentColor" stroke-width="1.6"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${trace}</svg>`;
}

/* Les pictogrammes de la barre de navigation. Ils ne désignent pas des
   aliments mais des lieux de l'application, d'où un jeu à part: un
   champignon pour "menu" ne voulait rien dire. */
const ONGLETS = {
  stock: '<rect x="5" y="2.5" width="14" height="19" rx="2.5"/><path d="M5 9h14"/><path d="M8 5.5v2M8 11.5v3.5"/><path d="M7.5 21.5V23M16.5 21.5V23"/>',
  menu: '<path d="M5 3v8a3 3 0 0 0 6 0V3"/><path d="M8 3v18"/><path d="M17.5 3c-1.7 1.6-2.5 4-2.5 6.5 0 1.9 1 3.3 2.5 3.5V21"/>',
  carnet: '<path d="M6 3h11a2 2 0 0 1 2 2v16H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M4 17.5h15"/><path d="M9 8h6M9 11.5h4"/>',
  bilan: '<path d="M12 3a9 9 0 1 0 9 9h-9z"/><path d="M15.5 3.6A9 9 0 0 1 20.4 8.5H15.5z"/>',
};

/** Le pictogramme d'un onglet. */
export function pictoOnglet(nom, taille = 20) {
  return `<svg viewBox="0 0 24 24" width="${taille}" height="${taille}"
    fill="none" stroke="currentColor" stroke-width="1.6"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${
      ONGLETS[nom] || TRACES.autre}</svg>`;
}

export const GENRES = Object.keys(TRACES);
