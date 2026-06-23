const CACHE_NAME = 'portfolio-v1';
const ASSETS = [
  '/alipay-portfolio-report/',
  '/alipay-portfolio-report/index.html',
  '/alipay-portfolio-report/manifest.json',
  '/alipay-portfolio-report/icon-192.png',
  '/alipay-portfolio-report/icon-512.png'
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', e => {
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request))
  );
});
