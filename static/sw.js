// Mera Hisaab PWA Service Worker
const CACHE_NAME = 'mera-hisaab-v1';
const ASSETS_TO_CACHE = [
  '/',
  '/static/css/app.css',
  '/static/js/app.js',
  '/static/vendor/bootstrap/bootstrap.min.css',
  '/static/vendor/bootstrap/bootstrap.bundle.min.js',
  '/static/vendor/bootstrap-icons/bootstrap-icons.min.css',
  '/static/vendor/htmx/htmx.min.js',
  '/static/icons/icon.svg',
  '/static/manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE).catch(() => {
        // Non-blocking asset fetch
      });
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Only cache GET requests
  if (event.request.method !== 'GET') return;

  // Stale-while-revalidate for static assets, network-first for HTML pages
  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then((cachedResponse) => {
        const fetchPromise = fetch(event.request).then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, networkResponse.clone()));
          }
          return networkResponse;
        }).catch(() => cachedResponse);
        return cachedResponse || fetchPromise;
      })
    );
  } else {
    // Network-first for dynamic business views
    event.respondWith(
      fetch(event.request).catch(() => caches.match(event.request))
    );
  }
});
