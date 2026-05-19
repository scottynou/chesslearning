/* Service worker minimaliste : cache des assets statiques pour shell offline.
   Les requetes API (POST /plan-recommendations, /review-move, /bot-move...)
   passent toujours par le reseau - elles dependent du backend Stockfish/Maia
   distant. Le mode 100% offline necessite une integration Stockfish WASM
   (deferree, voir docs). */

const CACHE_NAME = "chess-elo-coach-v1";
const STATIC_ASSETS = [
  "/",
  "/manifest.webmanifest",
  "/favicon.ico",
  "/favicon.svg",
  "/icon-192.png",
  "/icon-512.png",
  "/apple-touch-icon.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)).catch(() => undefined)
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);

  // Pas de cache pour les API (besoin de fraicheur + auth/headers).
  const apiPaths = ["/plan-recommendations", "/bot-move", "/review-move", "/explain", "/analyze", "/position-plan", "/live-plan-insight", "/import-position-image", "/available-plans", "/health"];
  if (apiPaths.some((path) => url.pathname.startsWith(path))) {
    return;
  }

  // Strategy : stale-while-revalidate pour les assets statiques.
  event.respondWith(
    caches.open(CACHE_NAME).then(async (cache) => {
      const cached = await cache.match(request);
      const fetchPromise = fetch(request)
        .then((response) => {
          if (response && response.status === 200 && response.type === "basic") {
            cache.put(request, response.clone());
          }
          return response;
        })
        .catch(() => cached);
      return cached || fetchPromise;
    })
  );
});
