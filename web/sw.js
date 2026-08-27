/* Service worker minimal.
   La coquille de l'app est mise en cache pour un démarrage instantané.
   Les données, elles, ne le sont jamais: un stock périmé affiché comme
   frais serait pire que pas de stock du tout. */

const CACHE = "vesta-v13";
const COQUILLE = [
  "/", "/index.html", "/style.css", "/manifest.webmanifest",
  "/js/app.js", "/js/noyau.js", "/js/navigation.js", "/js/recette.js",
  "/js/editeur.js", "/js/vues/stock.js", "/js/vues/menu.js",
  "/js/vues/carnet.js", "/js/vues/bilan.js", "/js/vues/aliments.js",
  "/js/pictos.js",
  "/js/reperes.js",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(COQUILLE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((noms) => Promise.all(noms.filter((n) => n !== CACHE).map((n) => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("message", (e) => {
  if (e.data && e.data.action === "prendre-la-main") self.skipWaiting();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;

  // Les appels à l'API vont toujours au réseau.
  if (url.pathname.startsWith("/api/")) return;
  if (url.origin !== location.origin) return;

  // Coquille: on sert le cache tout de suite et on rafraîchit derrière
  // (stale-while-revalidate). Sur un Pi qui rame, attendre le réseau à
  // chaque changement d'écran se sentait. La fraîcheur du code ne
  // dépend pas de ça: à chaque chargement, app.js redemande sw.js, une
  // nouvelle version prend la main et recharge la page une fois.
  e.respondWith(
    caches.open(CACHE).then((cache) =>
      cache.match(e.request).then((enCache) => {
        const reseau = fetch(e.request)
          .then((r) => {
            if (r.ok) cache.put(e.request, r.clone());
            return r;
          })
          .catch(() => enCache);
        return enCache || reseau;
      })
    )
  );
});
