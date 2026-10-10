// Only the offline explanation and its public stylesheet are cached. Settings,
// previews, status, and pairing keys always require the live Pi and Tailscale.
const CACHE_NAME = 'desk-matrix-offline-v1';
const OFFLINE_FILES = ['/offline.html', '/app.css'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(OFFLINE_FILES))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(names
        .filter((name) => name.startsWith('desk-matrix-offline-') && name !== CACHE_NAME)
        .map((name) => caches.delete(name))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || event.request.mode !== 'navigate') return;
  event.respondWith((async () => {
    try {
      const response = await fetch(event.request);
      if (response.status < 500) return response;
    } catch { /* The phone or Pi may be offline. */ }
    return (await caches.match('/offline.html')) || Response.error();
  })());
});
