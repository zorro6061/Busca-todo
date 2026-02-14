const CACHE_NAME = 'busca-todo-v2-final';
const urlsToCache = [
    '/',
    '/static/css/style.css',
    '/static/js/main.js'
];

self.addEventListener('install', event => {
    self.skipWaiting(); // Forzar activación del nuevo worker
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(urlsToCache))
    );
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cache => {
                    if (cache !== CACHE_NAME) {
                        return caches.delete(cache); // Limpiar cache viejo
                    }
                })
            );
        })
    );
});

self.addEventListener('fetch', event => {
    // Solo interceptar peticiones GET (evita romper POST de la API)
    if (event.request.method !== 'GET') return;

    // Estrategia: Red primero, si falla Cache (para ver cambios al instante)
    event.respondWith(
        fetch(event.request).catch(() => caches.match(event.request))
    );
});
