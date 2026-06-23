const CACHE_NAME = 'portfolio-v5';
const ASSETS = [
  '/alipay-portfolio-report/manifest.json',
  '/alipay-portfolio-report/icon-192.png',
  '/alipay-portfolio-report/icon-512.png'
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const req = e.request;
  const accept = req.headers.get('accept') || '';

  // HTML 页面必须网络优先，避免旧资产配置方案被离线缓存长期顶住
  if (req.mode === 'navigate' || accept.includes('text/html')) {
    e.respondWith(
      fetch(req, { cache: 'no-store' })
        .catch(() => caches.match('/alipay-portfolio-report/index.html'))
    );
    return;
  }

  e.respondWith(caches.match(req).then(r => r || fetch(req)));
});
