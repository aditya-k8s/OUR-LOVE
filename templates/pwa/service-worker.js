/* Our Love service worker (version {{ version }}).
 *
 * - Pre-caches the app shell (CSS, JS, icons, offline page).
 * - Static assets: cache first. Pages: network first, offline page as fallback.
 * - Pages are cached only when the server marks them cacheable (never
 *   "private"/"no-store"), so personal content is not kept on the device.
 * - /admin/, /api/, /media/ and /accounts/ are never intercepted.
 */
const VERSION = "{{ version }}";
const SHELL_CACHE = `ourlove-shell-${VERSION}`;
const PAGE_CACHE = `ourlove-pages-${VERSION}`;
const FONT_CACHE = "ourlove-fonts-v1";
const SHELL = {{ shell_json|safe }};
const STATIC_PREFIX = "{{ static_prefix }}";
const NEVER = ["/admin/", "/api/", "/media/", "/accounts/", "/service-worker.js"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key.startsWith("ourlove-") && ![SHELL_CACHE, PAGE_CACHE, FONT_CACHE].includes(key))
          .map((key) => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("message", (event) => {
  if (event.data === "clear-pages") {
    event.waitUntil(caches.delete(PAGE_CACHE));
  }
});

function cacheable(response) {
  if (!response || !response.ok || response.type === "opaqueredirect" || response.redirected) return false;
  const cc = (response.headers.get("Cache-Control") || "").toLowerCase();
  return !cc.includes("private") && !cc.includes("no-store");
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);

  // Google Fonts: stale-while-revalidate in a long-lived cache.
  if (url.origin === "https://fonts.googleapis.com" || url.origin === "https://fonts.gstatic.com") {
    event.respondWith(
      caches.open(FONT_CACHE).then(async (cache) => {
        const hit = await cache.match(request);
        const network = fetch(request).then((res) => {
          if (res.ok || res.type === "opaque") cache.put(request, res.clone());
          return res;
        }).catch(() => hit);
        return hit || network;
      })
    );
    return;
  }

  if (url.origin !== self.location.origin) return;
  if (NEVER.some((prefix) => url.pathname.startsWith(prefix))) return;

  if (url.pathname.startsWith(STATIC_PREFIX)) {
    event.respondWith(
      caches.match(request).then((hit) => hit || fetch(request).then((res) => {
        if (res.ok) caches.open(SHELL_CACHE).then((cache) => cache.put(request, res.clone()));
        return res;
      }))
    );
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).then((res) => {
        if (cacheable(res)) {
          const copy = res.clone();
          caches.open(PAGE_CACHE).then((cache) => cache.put(request, copy));
        }
        return res;
      }).catch(async () => (await caches.match(request, { cacheName: PAGE_CACHE })) || caches.match("/offline/"))
    );
  }
});
