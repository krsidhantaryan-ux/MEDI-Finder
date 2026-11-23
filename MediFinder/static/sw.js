const CACHE_NAME = 'medfinder-shell-v20261123-14';
const SHELL_ASSETS = [
  '/',
  '/manifest.json',
  '/static/icons/icon-192.svg',
  '/static/icons/icon-512.svg',
  '/static/vendor/leaflet/leaflet.css',
  '/static/vendor/leaflet/leaflet.js'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(SHELL_ASSETS))
      .catch(() => {})
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  // Leave cross-origin APIs (GPS reverse-geocoding, tiles, OSRM, RxNorm, openFDA, Open-Meteo) completely untouched
  if (url.origin !== self.location.origin) return;
  // Never serve cached /api/* responses; live stock and holds must always come fresh from server
  if (url.pathname.startsWith('/api/')) return;

  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.status === 200 && res.type === 'basic') {
          const cloned = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, cloned)).catch(() => {});
        }
        return res;
      })
      .catch(() => caches.match(req).then((cached) => cached || caches.match('/')))
  );
});
