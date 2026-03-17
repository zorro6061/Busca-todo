const CACHE_NAME = "busca-todo-v111-stale";
const urlsToCache = [
  "/",
  "/static/css/style.css",
  "/static/css/toasts.css",
  "/static/css/silver.css",
  "/static/js/main.js",
  "/static/js/offline_sync.js",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png"
];

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(urlsToCache)),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cache) => {
          if (cache !== CACHE_NAME) {
            return caches.delete(cache);
          }
        }),
      );
    }),
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;

  const url = event.request.url;
  const isStatic = url.includes('/static/') || url.includes('fonts.googleapis') || url.includes('fonts.gstatic');

  if (isStatic) {
    // 🏂 Estrategia: Stale-While-Revalidate (Cargar de cache, actualizar en background)
    event.respondWith(
      caches.open(CACHE_NAME).then((cache) => {
        return cache.match(event.request).then((cachedResponse) => {
          const fetchedResponse = fetch(event.request).then((networkResponse) => {
            cache.put(event.request, networkResponse.clone());
            return networkResponse;
          }).catch(() => {}); // Fallback silencioso si no hay red
          return cachedResponse || fetchedResponse;
        });
      })
    );
  } else {
    // 🌐 Estrategia para rutas dinámicas: Red primero, Fallback Cache
    event.respondWith(
      fetch(event.request).catch(() => caches.match(event.request))
    );
  }
});
