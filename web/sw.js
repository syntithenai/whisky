const APP_CACHE = "whisky-app-v10";
const DATA_CACHE = "whisky-data-v4";
const IMAGE_CACHE = "whisky-images-v3";

const BASE_PATH = new URL(self.registration.scope).pathname.replace(/\/$/, "");

function appPath(path) {
  return `${BASE_PATH}${path === "/" ? "/" : path}`;
}

const PHASE_PATHS = [
  "/phase-1",
  "/phase-2",
  "/phase-3",
  "/phase-4",
  "/phase-5",
  "/phase-6",
  "/phase-7",
  "/phase-8",
  "/phase-9",
  "/phase-10",
];

const APP_SHELL = [
  "/",
  "/database",
  "/resources",
  "/quizzes",
  "/whisky-lessons",
  "/glossary",
  "/privacy",
  "/manifest.webmanifest",
  "/sw.js",
  "/web/icons/icon.svg",
  ...PHASE_PATHS,
  ...PHASE_PATHS.map((path) => `${path}/raw`),
  "/quizzes/data",
  "/glossary/data",
  "/data-web/distilleries.json",
  "/data-web/taxonomy.json",
  "/data-web/dataset-manifest.json",
  "/data-web/resources.json",
  "/data-web/resources-taxonomy.json",
  "/data-web/resources-manifest.json",
].map(appPath);

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(APP_CACHE).then((cache) => cache.addAll(APP_SHELL)).then(() => self.skipWaiting())
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
  if (event.request.method !== "GET") {
    return;
  }

  if (url.pathname.startsWith(appPath("/data-web/"))) {
    event.respondWith(staleWhileRevalidate(event.request, DATA_CACHE));
    return;
  }

  if (url.pathname.startsWith(appPath("/media/"))) {
    event.respondWith(cacheFirst(event.request, IMAGE_CACHE));
    return;
  }

  if (url.pathname === appPath("/quizzes/data") || url.pathname === appPath("/glossary/data") || url.pathname.endsWith("/raw")) {
    event.respondWith(staleWhileRevalidate(event.request, DATA_CACHE));
    return;
  }

  if (APP_SHELL.includes(url.pathname) || url.pathname.startsWith(appPath("/phase-"))) {
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
