const APP_CACHE = "whisky-app-v6";
const DATA_CACHE = "whisky-data-v3";
const IMAGE_CACHE = "whisky-images-v2";

const PHASE_ROUTES = [
  "/phase-1",
  "/phase-2",
  "/phase-3",
  "/phase-4",
  "/phase-5",
  "/phase-6",
  "/phase-7",
];

const PRECACHE_ROUTES = [
  "/",
  "/database",
  "/resources",
  "/quizzes",
  "/whisky-lessons",
  "/the-whisky-course",
  "/privacy",
  "/manifest.webmanifest",
  "/sw.js",
  "/web/icons/icon.svg",
  ...PHASE_ROUTES,
  ...PHASE_ROUTES.map((path) => `/data-web/${path.slice(1)}.md`),
  "/data-web/quizzes.json",
  "/data-web/distilleries.json",
  "/data-web/taxonomy.json",
  "/data-web/dataset-manifest.json",
  "/data-web/resources.json",
  "/data-web/resources-taxonomy.json",
  "/data-web/resources-manifest.json",
];

const SCOPE_URL = new URL(self.registration.scope);
const SCOPE_PATH = SCOPE_URL.pathname.replace(/\/$/, "");

function appUrl(route) {
  if (route === "/") {
    return new URL(".", self.registration.scope).toString();
  }
  return new URL(route.slice(1), self.registration.scope).toString();
}

function appRelativePath(pathname) {
  let relativePath = pathname || "/";
  if (SCOPE_PATH && SCOPE_PATH !== "/" && relativePath.startsWith(SCOPE_PATH)) {
    relativePath = relativePath.slice(SCOPE_PATH.length) || "/";
  }
  if (relativePath.length > 1 && relativePath.endsWith("/")) {
    return relativePath.slice(0, -1);
  }
  return relativePath || "/";
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(APP_CACHE).then((cache) => cache.addAll(PRECACHE_ROUTES.map((route) => appUrl(route)))).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => ![APP_CACHE, DATA_CACHE, IMAGE_CACHE].includes(key))
          .map((key) => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const relativePath = appRelativePath(url.pathname);
  if (event.request.method !== "GET") {
    return;
  }

  if (relativePath.startsWith("/data-web/")) {
    event.respondWith(staleWhileRevalidate(event.request, DATA_CACHE));
    return;
  }

  if (relativePath.startsWith("/media/")) {
    event.respondWith(cacheFirst(event.request, IMAGE_CACHE));
    return;
  }

  if (PRECACHE_ROUTES.includes(relativePath) || relativePath.startsWith("/phase-") || relativePath.startsWith("/distillery/")) {
    event.respondWith(cacheFirst(event.request, APP_CACHE));
    return;
  }
});

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) {
    return cached;
  }
  const response = await fetch(request);
  if (response && response.ok) {
    cache.put(request, response.clone());
  }
  return response;
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const networkPromise = fetch(request)
    .then((response) => {
      if (response && response.ok) {
        cache.put(request, response.clone());
      }
      return response;
    })
    .catch(() => null);

  if (cached) {
    networkPromise.catch(() => null);
    return cached;
  }

  const network = await networkPromise;
  if (network) {
    return network;
  }

  throw new Error("Request failed and no cached response available.");
}
