/* Situer un apport par rapport aux repères d'un repas.

   Les bornes viennent des références françaises pour un adulte, ramenées
   à un repas: environ un tiers de la journée pour l'énergie et les
   macronutriments, la moitié pour les fibres puisqu'on en manque
   généralement, et la limite de sel de l'OMS divisée par trois.

   Ce sont des ordres de grandeur, pas des règles. Un plat riche un soir
   ne dit rien; c'est la répétition sur la semaine qui compte, et c'est
   pour ça que l'écran du bilan raisonne sur sept jours. */

const REPERES = {
  // [en dessous de, au dessus de], dans l'unité affichée
  kcal:      { bas: 400, haut: 850 },
  proteines: { bas: 15, haut: 50 },
  glucides:  { bas: 35, haut: 115 },
  lipides:   { bas: 10, haut: 38 },
  // Les fibres et rien d'autre: en manquer est le cas courant, en avoir
  // beaucoup est une bonne nouvelle. Le sens des couleurs s'inverse.
  fibres:    { bas: 5, haut: null, plus_c_est_mieux: true },
  sel:       { bas: null, haut: 2.2 },
};

/** "bas", "juste" ou "haut", ou "" quand on n'a pas de repère. */
export function niveau(cle, valeur) {
  const repere = REPERES[cle];
  if (!repere || valeur === null || valeur === undefined) return "";
  if (repere.bas !== null && valeur < repere.bas) {
    return repere.plus_c_est_mieux ? "bas" : "bas";
  }
  if (repere.haut !== null && valeur > repere.haut) return "haut";
  return "juste";
}

/** Une phrase courte, pour la ligne sous les chiffres. */
export function commentaire(cle, valeur) {
  const etat = niveau(cle, valeur);
  if (etat === "juste" || !etat) return "";
  // Deux mots au plus: ces libellés vivent dans une carte étroite, et
  // "beaucoup de matières grasses" y débordait.
  const phrases = {
    kcal: { bas: "léger", haut: "copieux" },
    proteines: { bas: "peu", haut: "beaucoup" },
    glucides: { bas: "peu", haut: "beaucoup" },
    lipides: { bas: "peu", haut: "assez gras" },
    fibres: { bas: "peu", haut: "" },
    sel: { bas: "", haut: "salé" },
  };
  return (phrases[cle] || {})[etat] || "";
}
