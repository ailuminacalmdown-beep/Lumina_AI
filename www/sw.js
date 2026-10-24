/* Lumina v7 — service worker minimal et prudent.
   - Met en cache l'enveloppe de l'appli (HTML/CSS/JS/icônes) pour un démarrage hors ligne.
   - Réseau d'abord : une nouvelle version déployée est toujours prise en compte dès qu'on est en ligne.
   - Ne met JAMAIS en cache l'API (auth, chat, live, feedback, mémoire) ni les requêtes non-GET. */
const VERSION = "lumina-v7-1";
const SHELL = ["/", "/index.html", "/v7.css", "/ui7.js", "/live.js", "/manifest.json",
  "/icons/icon-32.png", "/icons/icon-192.png", "/icons/icon-512.png"];
const API_PREFIXES = ["/auth", "/chat", "/live", "/feedback", "/get_memory", "/clear_memory",
  "/conv_memory", "/search_web", "/status", "/healthz", "/models", "/groq_models"];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(VERSION)
      .then((c) => Promise.all(SHELL.map((u) => c.add(u).catch(() => null))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (API_PREFIXES.some((p) => url.pathname === p || url.pathname.startsWith(p + "/"))) return;

  e.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.ok && res.type === "basic") {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(req, copy)).catch(() => {});
        }
        return res;
      })
      .catch(() => caches.match(req).then((hit) => hit || (req.mode === "navigate" ? caches.match("/index.html") : Response.error())))
  );
});
