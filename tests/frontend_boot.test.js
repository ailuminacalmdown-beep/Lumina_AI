// Test d'initialisation du frontend (sans navigateur) : `node tests/frontend_boot.test.js [fichier.html]`
// Reproduit le comportement d'un navigateur : un <script> inline s'exécute AVANT que les éléments
// situés après lui dans le HTML existent. Vérifie (1) aucune exception au chargement,
// (2) que boot() est atteint (l'écran de connexion est affiché pour un utilisateur sans session).
const fs = require("fs");
const vm = require("vm");
const file = process.argv[2] || require("path").join(__dirname, "..", "www", "index.html");
const html = fs.readFileSync(file, "utf8").split("\n");
const start = html.findIndex((l) => l.trim() === "<script>");
const end = html.findIndex((l, i) => i > start && l.trim() === "</script>");
const early = new Set();
for (let i = 0; i < start; i++) for (const m of html[i].matchAll(/id="([^"]+)"/g)) early.add(m[1]);

const calls = [];
function mk(name) {
  const f = function () {};
  return new Proxy(f, {
    get: (t, p) => {
      if (p === Symbol.toPrimitive) return () => "";
      if (p === "length") return 0;
      if (p === "then") return undefined;
      if (p === "classList") return { add() {}, toggle() {}, contains: () => false, remove: (c) => calls.push(name + ".remove." + c) };
      return mk(name + "." + String(p));
    },
    set: () => true, apply: () => mk(name + "()"), construct: () => mk(name + "()"),
  });
}
const store = {};
const ctx = {
  console: { log() {}, error() {}, warn() {} },
  setTimeout: () => 0, setInterval: () => 0, clearTimeout() {}, clearInterval() {}, requestAnimationFrame() {},
  localStorage: { getItem: (k) => store[k] ?? null, setItem: (k, v) => (store[k] = String(v)), removeItem: (k) => delete store[k] },
  navigator: { onLine: true, serviceWorker: { register: () => ({ catch() {} }) }, mediaDevices: {}, userAgent: "x" },
  location: { hostname: "localhost" }, fetch: () => Promise.reject(new Error("réseau coupé")),
  document: {
    getElementById: (id) => (early.has(id) ? mk(id) : null),
    querySelectorAll: () => [], querySelector: () => mk("q"), addEventListener() {}, body: mk("body"),
    documentElement: mk("html"), createElement: () => mk("el"), visibilityState: "visible",
  },
  ResizeObserver: function () { return mk("ro"); }, SpeechSynthesisUtterance: function () {}, Audio: function () {},
  addEventListener() {},
};
ctx.window = ctx; ctx.self = ctx;
vm.createContext(ctx);
let failed = false;
try {
  vm.runInContext(html.slice(start + 1, end).join("\n"), ctx, { filename: "index.html" });
} catch (e) {
  const m = (e.stack || "").match(/index\.html:(\d+)/);
  console.log("ÉCHEC : exception au chargement :", e.message, m ? "(ligne ≈ " + (+m[1] + start + 1) + ")" : "");
  failed = true;
}
setImmediate(() => setImmediate(() => {
  if (!failed) {
    const shown = calls.includes("authScr.remove.hide");
    console.log(shown ? "OK : aucune exception, boot() atteint, écran de connexion affiché."
                      : "ÉCHEC : pas d'exception mais boot() n'a pas affiché l'écran de connexion.");
    failed = !shown;
  }
  process.exit(failed ? 1 : 0);
}));
