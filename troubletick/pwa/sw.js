// Troubletick PWA — Service Worker (Network-First con Auto-Update e Cache Busting)
importScripts('./version.js');

const CACHE_NAME = 'troubletick-pwa-v' + (self.APP_VERSION || '1.0.0');

// Risorse statiche principali da memorizzare per il funzionamento offline
const ASSETS_TO_CACHE = [
  './',
  './index.html',
  './version.js',
  './config.js',
  './app.js',
  './style.css',
  './manifest.json',
  './icon-192.png'
];

// 1. Installazione: Scarica le risorse e attiva immediatamente il nuovo worker
self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[ServiceWorker] Caching risorse versione:', CACHE_NAME);
      return cache.addAll(ASSETS_TO_CACHE).catch((err) => {
        console.warn('[ServiceWorker] Alcuni asset non sono stati pre-caricati:', err);
      });
    })
  );
});

// 2. Attivazione: Rimuove tutte le vecchie cache e prende il controllo immediato
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keyList) => {
      return Promise.all(
        keyList.map((key) => {
          if (key !== CACHE_NAME) {
            console.log('[ServiceWorker] Rimozione vecchia cache obsoleta:', key);
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// 3. Ricezione comandi dal client (es. SKIP_WAITING)
self.addEventListener('message', (event) => {
  if (event.data === 'SKIP_WAITING' || event.data === 'skipWaiting') {
    self.skipWaiting();
  }
});

// 4. Fetch: Strategia Network-First per ottenere sempre la versione più recente
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Non memorizzare in cache le chiamate API REST o le richieste diverse da GET
  if (event.request.method !== 'GET' || url.pathname.includes('/api') || url.pathname.includes('/login') || url.pathname.includes('/logout')) {
    return;
  }

  // Network-First: Prova prima a scaricare dal server; se online, aggiorna la cache e restituisci la risorsa fresca
  event.respondWith(
    fetch(event.request, { cache: 'no-cache' })
      .then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200 && networkResponse.type === 'basic') {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      })
      .catch(() => {
        // Se offline o in caso di errore di rete, recupera dalla cache locale
        return caches.match(event.request).then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }
          // Fallback a index.html per richieste di navigazione HTML
          if (event.request.headers.get('accept') && event.request.headers.get('accept').includes('text/html')) {
            return caches.match('./index.html') || caches.match('./');
          }
        });
      })
  );
});
