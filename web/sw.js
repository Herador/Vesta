/* Service worker minimal.
   La coquille de l'app est mise en cache pour un démarrage instantané.
   Les données, elles, ne le sont jamais: un stock périmé affiché comme
   frais serait pire que pas de stock du tout. */

const CACHE = "vesta-v9";
const COQUILLE = [
  "/", "/index.html", "/style.css", "/manifest.webmanifest",
  "/js/app.js", "/js/noyau.js", "/js/navigation.js", "/js/recette.js",
  "/js/editeur.js", "/js/vues/stock.js", "/js/vues/menu.js",
  "/js/vues/carnet.js", "/js/vues/bilan.js", "/js/pictos.js",
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

  // Le réseau d'abord, le cache en secours. L'inverse servait une
  // version périmée du code après chaque modification, et il fallait
  // vider le cache du navigateur à la main pour voir ses changements.
  // Le cache reste indispensable, mais comme filet: hors ligne, ou quand
  // le Pi ne répond pas.
  e.respondWith(
    fetch(e.request)
      .then((r) => {
        if (r.ok && url.origin === location.origin) {
          const copie = r.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copie));
        }
        return r;
      })
      .catch(() => caches.match(e.request))
  );
});
