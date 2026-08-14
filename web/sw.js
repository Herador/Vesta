/* Service worker minimal.
   La coquille de l'app est mise en cache pour un démarrage instantané.
   Les données, elles, ne le sont jamais: un stock périmé affiché comme
   frais serait pire que pas de stock du tout. */

const CACHE = "garde-manger-v1";
const COQUILLE = ["/", "/index.html", "/style.css", "/app.js", "/manifest.webmanifest"];

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

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;

  // Les appels à l'API vont toujours au réseau.
  if (url.pathname.startsWith("/api/")) return;

  // Le reste: le cache d'abord, le réseau ensuite pour se rafraîchir.
  e.respondWith(
    caches.match(e.request).then((enCache) => {
      const reseau = fetch(e.request).then((r) => {
        if (r.ok && url.origin === location.origin) {
          const copie = r.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copie));
        }
        return r;
      }).catch(() => enCache);
      return enCache || reseau;
    })
  );
});
