/* Lumina v8 — barre de saisie : sélecteur de modèle, pièces jointes, texte long collé → fichier TXT.
   Chaque bloc est isolé : une erreur ici ne doit jamais empêcher le chat de fonctionner. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const guard = (n, fn) => { try { fn(); } catch (e) { console.error("[ui8:" + n + "]", e); } };
  const PASTE_MIN = 1500;      // au-delà, le texte collé devient un fichier
  const MAX_TOTAL = 7500;      // le serveur refuse > MAX_MESSAGE_CHARS (8000 par défaut)
  let atts = [];

  const FILE_ICO = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';
  const total = () => atts.reduce((n, a) => n + a.text.length, 0);

  const fullByThumb = {};   // miniature -> image pleine résolution (pour l'aperçu plein écran)
  function viewer(item) {
    document.querySelectorAll(".l8-view").forEach((x) => x.remove());
    const ov = document.createElement("div"); ov.className = "l8-view";
    const x = document.createElement("button"); x.type = "button"; x.className = "l8-view-x"; x.setAttribute("aria-label", "Fermer"); x.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>';
    const body = document.createElement("div"); body.className = "l8-view-body";
    if (item.src) { const im = document.createElement("img"); im.src = item.src; im.alt = "Aperçu"; body.appendChild(im); }
    else { const t = document.createElement("div"); t.className = "l8-view-text"; t.textContent = item.text; body.appendChild(t); }
    const close = () => { ov.classList.add("out"); setTimeout(() => ov.remove(), 180); };
    x.onclick = close; ov.append(x, body); document.body.appendChild(ov);
    let y0 = null, dy = 0;   // glisser vers le bas pour fermer
    ov.addEventListener("touchstart", (e) => { if (e.touches.length === 1 && (item.src || body.scrollTop <= 0)) { y0 = e.touches[0].clientY; dy = 0; } }, { passive: true });
    ov.addEventListener("touchmove", (e) => { if (y0 == null) return; dy = e.touches[0].clientY - y0; if (dy > 0) { body.style.transform = "translateY(" + dy + "px)"; ov.style.opacity = String(Math.max(.3, 1 - dy / 500)); } }, { passive: true });
    ov.addEventListener("touchend", () => { if (y0 == null) return; if (dy > 110) close(); else { body.style.transform = ""; ov.style.opacity = ""; } y0 = null; });
  }
  window.L8view = (src) => viewer({ src: fullByThumb[src] || src });

  function renderAtt() {
    const box = $("cmpAtt"); if (!box) return; box.innerHTML = "";
    atts.forEach((a, i) => {
      const c = document.createElement("div"); c.className = "att-card" + (a.img ? " is-img" : "");
      if (a.img) { const im = document.createElement("img"); im.src = a.img.thumb; im.alt = "Photo jointe"; c.appendChild(im); }
      else {
        const b = document.createElement("span"); b.className = "att-badge"; b.textContent = "TXT";
        const n = document.createElement("div"); n.className = "att-name"; n.textContent = a.name.replace(/\.txt$/i, "");
        c.append(b, n);
      }
      c.onclick = () => viewer(a.img ? { src: a.img.full } : { text: a.text });
      const x = document.createElement("button"); x.type = "button"; x.className = "att-x"; x.setAttribute("aria-label", "Retirer");
      x.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>';
      x.onclick = (e) => { e.stopPropagation(); atts.splice(i, 1); renderAtt(); };
      c.appendChild(x); box.appendChild(c);
    });
  }
  function addAtt(name, text) {
    if (total() + text.length > MAX_TOTAL) { toast("Texte trop long (" + (total() + text.length).toLocaleString("fr-FR") + " caractères, maximum " + MAX_TOTAL.toLocaleString("fr-FR") + " pour l'instant)"); return false; }
    atts.push({ name, text }); renderAtt(); return true;
  }

  guard("paste", () => {
    $("userInp").addEventListener("paste", (e) => {
      const t = (e.clipboardData || window.clipboardData).getData("text");
      if (t && t.length > PASTE_MIN) { e.preventDefault(); addAtt("Contenu collé.txt", t); }
    });
  });

  guard("send", () => {
    const orig = window.sendMsg; if (typeof orig !== "function") return;
    const origApi = window.callAPI;
    if (typeof origApi === "function") {   // la photo en attente part avec la prochaine requête au serveur
      window.callAPI = function (msg, conv, img, regen) {
        if (!img && window.__imgNext) { img = window.__imgNext; window.__imgNext = null; }
        return origApi.call(this, msg, conv, img, regen);
      };
    }
    window.sendMsg = function (override, retry) {
      if (override || retry || !atts.length) return orig.apply(this, arguments);
      if (RT.streamingConvs.has(ST.convs.cur)) return orig.apply(this, arguments);
      const typed = $("userInp").value.trim();
      const photos = atts.filter((a) => a.img), photo = photos[0], files = atts.filter((a) => !a.img);
      let msg = (typed ? typed + "\n\n" : "") + files.map((a) => "[Fichier joint : " + a.name + "]\n" + a.text).join("\n\n");
      if (!msg.trim() && photo) msg = "Analyse cette image en détail. Décris ce que tu vois, les couleurs, les éléments, le contexte. Réponds en français.";
      const names = files.map((a) => a.name); atts = []; renderAtt();
      if (photo) { window.__imgNext = photo.img.full; window.__imgsPending = photos.map((p) => p.img.full); }
      const conv = ST.convs.cur, p = orig.call(this, msg);
      let tries = 0;
      const patch = () => {  // bulle compacte : miniature + question + pastilles fichier, à l'écran et dans l'historique local
        const b = [...document.querySelectorAll("#chat .ubub")].reverse().find((x) => x.textContent === msg);
        const h = (ST.hist[conv] || []).slice().reverse().find((m) => m.role === "user" && m.content === msg);
        if (b) {
          b.textContent = "";
          if (photos.length) { const row = document.createElement("div"); row.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px"; photos.forEach((ph) => { const im = document.createElement("img"); im.src = ph.img.thumb; im.alt = "Photo envoyée"; im.style.cssText = "width:" + (photos.length > 1 ? "88px;height:88px;object-fit:cover" : "170px") + ";border-radius:10px;cursor:pointer"; im.onclick = () => viewer({ src: ph.img.full }); row.appendChild(im); }); b.appendChild(row); }
          if (typed) b.append(typed);
          names.forEach((n) => { const l = document.createElement("div"); l.className = "att-line"; l.innerHTML = FILE_ICO.replace("<svg", '<svg width="16" height="16"'); l.append(n); b.appendChild(l); });
        }
        if (h) { h.content = (photo ? "📷 ".repeat(photos.length) : "") + (typed || (photo && !names.length ? "Photo envoyée" : "")) + names.map((n) => "\n📎 " + n).join(""); save(); }
        if (!b && !h && ++tries < 40) setTimeout(patch, 50);
      };
      patch(); return p;
    };
  });

  guard("photo", () => {   // jusqu'à 4 photos jointes en haut de la barre ; question facultative
    const inp = $("imgInp"); if (!inp) return; inp.multiple = true;
    inp.onchange = (e) => {
      const fs = [...e.target.files]; e.target.value = ""; if (!fs.length) return;
      fs.forEach((f) => {
        if (!f.type.startsWith("image/")) return toast("Ce fichier n'est pas une image");
        if (atts.filter((a) => a.img).length >= 4) return toast("4 photos maximum par message");
        const r = new FileReader();
        r.onload = async () => {
          try {
            const full = await resizeDataUrl(r.result, 1280, 0.8), thumb = await resizeDataUrl(r.result, 480, 0.6);
            if (atts.filter((a) => a.img).length >= 4) return;
            fullByThumb[thumb] = full; atts.push({ name: f.name, text: "", img: { full, thumb } }); renderAtt(); $("userInp").focus();
          } catch (err) { toast("Impossible de lire cette image"); }
        };
        r.readAsDataURL(f);
      });
    };
  });

  guard("files", () => {   // fichiers texte : lus localement ; les autres formats ne sont pas encore analysés
    const inp = $("fileInp"); if (!inp) return;
    inp.onchange = (e) => {
      const f = e.target.files[0]; e.target.value = ""; if (!f) return;
      const textual = f.type.startsWith("text/") || /\.(txt|md|csv|json|py|js|html|css|xml|log|sql|ya?ml)$/i.test(f.name);
      if (!textual) { toast("Ce format (" + (f.name.split(".").pop() || "?") + ") n'est pas encore analysé. Texte, code et CSV fonctionnent."); return; }
      const r = new FileReader(); r.onload = () => addAtt(f.name, String(r.result)); r.readAsText(f);
    };
  });

  guard("model", () => {
    const chip = $("modelPill"); if (!chip) return;
    const sync = () => { const m = MODELS.find((x) => x.id === ST.mdl) || MODELS[0]; $("modelLabel").textContent = m.label.replace("Lumina ", ""); };
    sync();
    let menu = null; const close = () => { if (menu) { menu.remove(); menu = null; } };
    const open = (e) => {
      e.stopPropagation(); if (menu) return close();
      menu = document.createElement("div"); menu.className = "model-menu";
      MODELS.forEach((m) => {
        const b = document.createElement("button"); b.type = "button"; if (m.id === ST.mdl) b.className = "on";
        b.innerHTML = "<b></b><span></span>"; b.firstChild.textContent = m.label; b.lastChild.textContent = m.desc;
        b.onclick = () => { ST.mdl = m.id; sync(); close(); toast("Modèle : " + m.label); };
        menu.appendChild(b);
      });
      document.body.appendChild(menu);
      const r = chip.getBoundingClientRect();
      menu.style.left = Math.max(8, Math.min(r.left, innerWidth - menu.offsetWidth - 8)) + "px";
      menu.style.top = Math.max(8, r.top - menu.offsetHeight - 8) + "px";
      setTimeout(() => document.addEventListener("click", close, { once: true }), 0);
    };
    chip.onclick = open; chip.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") open(e); };
  });

  guard("grow", () => {   // la barre se déplie presque jusqu'en haut de l'écran visible (clavier déduit)
    const ta = $("userInp"), wrap = document.querySelector(".cmp-wrap"); if (!ta) return;
    const vh = () => (window.visualViewport ? window.visualViewport.height : innerHeight);
    const fit = () => { ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, Math.max(120, vh() - 210)) + "px"; };
    ta.addEventListener("input", fit);
    if (window.visualViewport) window.visualViewport.addEventListener("resize", fit);
    if (wrap && window.ResizeObserver) new ResizeObserver(() => document.documentElement.style.setProperty("--cmp-h", wrap.offsetHeight + "px")).observe(wrap);
  });

  guard("viewbubble", () => {   // un appui sur une image du chat l'ouvre en plein écran
    const chat = $("chat"); if (!chat) return;
    chat.addEventListener("click", (e) => { const im = e.target.closest && e.target.closest(".ubub img"); if (im && !im.onclick) window.L8view(im.src); });
  });

  guard("newtop", () => { const b = $("newConvTop"); if (b) b.onclick = () => $("newConvBtn").click(); });
})();

/* ── Bibliothèque : artéfacts enregistrés avec leur nom, et images générées ── */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const guard = (n, fn) => { try { fn(); } catch (e) { console.error("[ui8:" + n + "]", e); } };
  const KEY = "L8_arts", MAX_ITEMS = 60, MAX_CODE = 200000;
  const load = () => { try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch (e) { return []; } };
  const store = (l) => { try { localStorage.setItem(KEY, JSON.stringify(l)); return true; } catch (e) { toast("Stockage plein : artéfact non enregistré"); return false; } };
  const hash = (s) => { let h = 5381; for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0; return (h >>> 0).toString(36) + s.length; };
  const ICO = (d) => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + d + "</svg>";

  function nameFor(lang, code, n) {
    let m;
    if ((m = code.match(/<title[^>]*>([^<]{1,60})<\/title>/i)) && m[1].trim()) return m[1].trim();
    if ((m = code.match(/<h1[^>]*>([^<]{1,60})<\/h1>/i)) && m[1].trim()) return m[1].trim();
    if ((m = code.match(/^\s*(?:#|\/\/|\/\*+|--)\s*([^\n*]{3,60})/))) return m[1].trim();
    if ((m = code.match(/\b(?:class|def|function)\s+([A-Za-z_]\w{2,40})/))) return m[1];
    return artMeta(lang).lbl + " " + (n + 1);
  }

  guard("cards", () => {
    const orig = window.buildArtCard; if (typeof orig !== "function") return;
    window.buildArtCard = function (lang, code) {
      const card = orig.apply(this, arguments);
      try {
        if (code.length > MAX_CODE) return card;
        const list = load(), id = hash(lang + "|" + code);
        let it = list.find((x) => x.id === id);
        if (!it) {
          it = { id, name: nameFor(lang, code, list.length), lang, code, date: Date.now(), conv: ST.convs.cur };
          list.unshift(it); if (list.length > MAX_ITEMS) list.length = MAX_ITEMS; store(list);
        }
        const t = card.querySelector(".art-title"); if (t) t.textContent = it.name;
      } catch (e) { console.error("[ui8:cards]", e); }
      return card;
    };
  });

  function sheet(title, build) {
    document.querySelectorAll(".lib-ov").forEach((x) => x.remove());
    const ov = document.createElement("div"); ov.className = "lib-ov";
    ov.innerHTML = '<div class="lib-sheet"><div class="lib-head"><h2></h2><button class="lib-x" type="button" aria-label="Fermer">✕</button></div><div class="lib-body"></div></div>';
    ov.querySelector("h2").textContent = title;
    const close = () => ov.remove();
    ov.querySelector(".lib-x").onclick = close; ov.onclick = (e) => { if (e.target === ov) close(); };
    document.body.appendChild(ov); build(ov.querySelector(".lib-body"), close);
  }

  const PREVIEWABLE = ["html", "svg", ""];   // pages web, jeux, SVG : s'affichent ; le reste est du « Code »
  window.L8sheet = sheet;

  const A_ICO = {
    copy: ICO('<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>'),
    share: ICO('<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.6" y1="13.5" x2="15.4" y2="17.5"/><line x1="15.4" y1="6.5" x2="8.6" y2="10.5"/>'),
    save: ICO('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>'),
    open: ICO('<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>'),
  };
  function fileOf(it) { const m = artMeta(it.lang); const base = (it.name || "lumina").replace(/[^\w\-. ]+/g, "").trim().replace(/\s+/g, "-").slice(0, 50) || "lumina"; return { name: base + "." + m.ext, type: it.lang === "html" || !it.lang ? "text/html" : "text/plain" }; }
  const codeActions = {
    copy: (it) => (navigator.clipboard ? navigator.clipboard.writeText(it.code).then(() => toast("Copié")) : toast("Copie impossible sur ce navigateur")),
    share: async (it) => {
      const f = fileOf(it);
      try {
        const file = new File([it.code], f.name, { type: f.type });
        if (navigator.canShare && navigator.canShare({ files: [file] })) return await navigator.share({ files: [file], title: it.name });
        if (navigator.share) return await navigator.share({ title: it.name, text: it.code });
      } catch (e) { if (e && e.name === "AbortError") return; }
      codeActions.copy(it);
    },
    save: (it) => { const f = fileOf(it), a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([it.code], { type: f.type })); a.download = f.name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 4000); toast("Exporté : " + f.name); },
    open: (it) => {
      const f = fileOf(it);
      try { const w = window.open(URL.createObjectURL(new Blob([it.code], { type: f.type + ";charset=utf-8" })), "_blank"); if (w) return; } catch (e) { /* repli ci-dessous */ }
      artStore[it.id] = { lang: it.lang, code: it.code, m: artMeta(it.lang) }; openArt(it.id);
    },
  };

  function openCode() {
    sheet("Code", function render(body, close) {
      body.innerHTML = ""; const list = load();
      if (!list.length) { body.innerHTML = '<div class="lib-empty">Aucun code pour l\'instant.<br>Les scripts, pages et jeux que Lumina écrit apparaissent ici : tu peux les copier, partager, exporter ou ouvrir dans ton navigateur.</div>'; return; }
      list.forEach((it) => {
        const m = artMeta(it.lang), card = document.createElement("div"); card.className = "code-card";
        card.innerHTML = '<div class="lib-item" style="padding:6px 4px"><div class="lib-ico"></div><div class="lib-info"><div class="lib-name"></div><div class="lib-sub"></div></div></div><div class="code-acts"></div>';
        const ico = card.querySelector(".lib-ico"); ico.style.cssText = "background:" + m.col + "22;color:" + m.col; ico.innerHTML = m.ico;
        card.querySelector(".lib-name").textContent = it.name;
        card.querySelector(".lib-sub").textContent = m.lbl + " · " + it.code.split("\n").length + " lignes · " + new Date(it.date).toLocaleDateString("fr-FR");
        const acts = card.querySelector(".code-acts");
        [["copy", "Copier"], ["share", "Partager"], ["save", "Exporter"], ["open", "Ouvrir"]].forEach(([k, label]) => {
          const b = document.createElement("button"); b.type = "button"; b.className = "code-act"; b.innerHTML = A_ICO[k]; b.append(label);
          b.onclick = () => codeActions[k](it); acts.appendChild(b);
        });
        card.querySelector(".lib-info").onclick = () => { artStore[it.id] = { lang: it.lang, code: it.code, m }; close(); closeBar(); openArt(it.id); };
        body.appendChild(card);
      });
    });
  }

  function openArtifacts() {
    sheet("Artéfacts", function render(body, close) {
      body.innerHTML = ""; const list = load().filter((x) => PREVIEWABLE.includes(x.lang));
      if (!list.length) { body.innerHTML = '<div class="lib-empty">Aucun artéfact pour l\'instant.<br>Le code, les pages web et les jeux que Lumina génère apparaissent ici avec leur nom.</div>'; return; }
      list.forEach((it) => {
        const m = artMeta(it.lang), row = document.createElement("div"); row.className = "lib-item";
        row.innerHTML = '<div class="lib-ico"></div><div class="lib-info"><div class="lib-name"></div><div class="lib-sub"></div></div><button class="lib-act" type="button" aria-label="Renommer">✎</button><button class="lib-act" type="button" aria-label="Supprimer">🗑</button>';
        const ico = row.querySelector(".lib-ico"); ico.style.cssText = "background:" + m.col + "22;color:" + m.col; ico.innerHTML = m.ico;
        row.querySelector(".lib-name").textContent = it.name;
        row.querySelector(".lib-sub").textContent = m.lbl + " · " + it.code.split("\n").length + " lignes · " + new Date(it.date).toLocaleDateString("fr-FR");
        row.querySelector(".lib-info").onclick = () => { artStore[it.id] = { lang: it.lang, code: it.code, m }; close(); closeBar(); openArt(it.id); };
        const [ren, del] = row.querySelectorAll(".lib-act");
        ren.onclick = async () => { const n = ((await L8ui.prompt("Nom de l'artéfact", { value: it.name })) || "").trim().slice(0, 60); if (n) { it.name = n; store(load().map((x) => x.id === it.id ? it : x)); render(body, close); } };
        del.onclick = async () => { if (await L8ui.confirm("Supprimer « " + it.name + " » ?", { danger: true, ok: "Supprimer" })) { store(load().filter((x) => x.id !== it.id)); render(body, close); } };
        body.appendChild(row);
      });
    });
  }

  function openImages() {
    sheet("Images", (body) => {
      const urls = [];
      Object.values(ST.hist || {}).forEach((msgs) => (msgs || []).forEach((m) => { if (m.type === "imggen" && m.content) urls.push(m.content); }));
      if (!urls.length) { body.innerHTML = '<div class="lib-empty">Aucune image générée.<br>Demande « Génère un paysage africain » pour en créer une.</div>'; return; }
      const g = document.createElement("div"); g.className = "lib-grid";
      urls.reverse().forEach((u) => { const i = document.createElement("img"); i.loading = "lazy"; i.alt = "Image générée"; i.src = u; i.onclick = () => window.open(u); g.appendChild(i); });
      body.appendChild(g);
    });
  }

  guard("nav", () => {
    const anchor = $("navStg"); if (!anchor) return;
    [["navCode", "Code", ICO('<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>'), openCode],
     ["navImages", "Images", ICO('<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>'), openImages],
     ["navArtifacts", "Artéfacts", ICO('<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>'), openArtifacts]
    ].forEach(([id, label, svg, fn]) => {
      const d = document.createElement("div"); d.className = "sb-nav-item"; d.id = id; d.innerHTML = svg; d.append(label);
      d.onclick = () => { closeBar(); fn(); }; anchor.parentNode.insertBefore(d, anchor);
    });
  });
})();

/* ── Régénérer seulement sur la dernière réponse · Projets · Personnaliser · Explorer · Abonnement ── */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const guard = (n, fn) => { try { fn(); } catch (e) { console.error("[ui8:" + n + "]", e); } };
  const ICO = (d) => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + d + "</svg>";
  const rd = (k, d) => { try { return JSON.parse(localStorage.getItem(k) || "null") ?? d; } catch (e) { return d; } };
  const wr = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { toast("Stockage plein"); } };
  const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
  const CONTACT_MAIL = "ai.lumina.calmdown@gmail.com", CONTACT_TEL = "+22393770325", CONTACT_TEL_FMT = "+223 93 77 03 25";

  /* Barre d'actions : « Régénérer » uniquement sur la dernière réponse ; copier / lire / like / dislike / partager restent partout */
  guard("lastbar", () => {
    const chat = $("chat"); if (!chat) return; let raf = 0;
    const mark = () => {
      raf = 0; const bars = [...chat.querySelectorAll(".msg-a .macts")];
      bars.forEach((b, i) => {
        const last = i === bars.length - 1; b.classList.toggle("is-last", last);
        const r = b.querySelector('[data-id="retry"]'); if (r) r.style.display = last ? "" : "none";
      });
    };
    new MutationObserver(() => { if (!raf) raf = requestAnimationFrame(mark); }).observe(chat, { childList: true, subtree: true });
    mark();
  });

  /* Instructions personnalisées + instructions du projet courant, envoyées avec chaque message du chat */
  const projects = () => rd("L8_projects", []);
  const custom = () => String(rd("L8_custom", "") || "");
  function instrFor(conv) {
    const parts = [], c = custom().trim(); if (c) parts.push(c);
    const pr = projects().find((p) => (p.convs || []).includes(conv));
    if (pr && (pr.instr || "").trim()) parts.push("Projet « " + pr.name + " » : " + pr.instr.trim());
    return parts.join("\n\n").slice(0, 1500);
  }
  guard("fetchwrap", () => {
    const f = window.fetch;
    window.fetch = function (u, o) {
      let isChat = false;
      try {
        if (o && o.method === "POST" && typeof u === "string" && /\/chat(\?|$)/.test(u) && typeof o.body === "string") {
          isChat = true;
          const b = JSON.parse(o.body), ci = instrFor(b.conv_id || ST.convs.cur);
          if (window.__imgsPending) { b.images = window.__imgsPending; window.__imgsPending = null; }
          if (ci) b.custom_instructions = ci;
          b.client_offset_min = -new Date().getTimezoneOffset();   // l'heure locale de l'utilisateur, pour que Lumina connaisse la date réelle
          o = Object.assign({}, o, { body: JSON.stringify(b) });
        }
      } catch (e) { /* on n'empêche jamais l'envoi */ }
      const p = f.call(this, u, o);
      if (isChat) p.then((r) => { try { r.clone().json().then((d) => { if (d && typeof d.elapsed_s === "number") window.__metaFresh = { s: d.elapsed_s, t: Date.now() }; }).catch(() => {}); } catch (e) { /* ignoré */ } }).catch(() => {});
      return p;
    };
  });

  /* Conversations épinglées en tête de liste, avec un intitulé */
  guard("pinned", () => {
    const o = window.renderConvList; if (typeof o !== "function") return;
    window.renderConvList = function () {
      o.apply(this, arguments);
      try {
        const cl = $("convList"), items = [...cl.children]; if (!items.length) return;
        const pinned = items.filter((d) => d.innerHTML.includes('y1="17"'));
        if (pinned.length) cl.insertBefore(el("div", "sb-sec", "Épinglés"), items[0]);
        cl.insertBefore(el("div", "sb-sec", "Récents"), items[pinned.length] || null);
      } catch (e) { /* purement visuel */ }
    };
    window.renderConvList();
  });

  /* Personnaliser */
  function openCustom() {
    L8sheet("Personnaliser", (body, close) => {
      body.append(el("div", "lib-sub", "Dis à Lumina comment te répondre (ton, niveau, langue, contexte). Ces instructions sont envoyées avec tes messages."));
      const ta = el("textarea", "modal-inp"); ta.rows = 6; ta.maxLength = 1000; ta.value = custom(); ta.style.cssText = "margin-top:10px;width:100%;resize:vertical";
      ta.placeholder = "Ex. : Je prépare le BAC. Explique simplement, avec des exemples tirés du quotidien au Mali.";
      const save = el("button", "mbtn p", "Enregistrer"); save.type = "button";
      save.onclick = () => { wr("L8_custom", ta.value.trim()); toast("Instructions enregistrées"); close(); };
      const row = el("div", "modal-btns"); row.append(save); body.append(ta, row);
    });
  }

  /* Projets : un nom, des instructions propres, des discussions regroupées */
  function openProjects() {
    L8sheet("Projets", function render(body, close) {
      body.innerHTML = ""; const list = projects();
      const add = el("button", "mbtn p", "+ Nouveau projet"); add.type = "button"; add.style.margin = "4px 8px 10px";
      add.onclick = async () => { const n = ((await L8ui.prompt("Nom du projet", { placeholder: "Ex. : Révision BAC" })) || "").trim().slice(0, 50); if (!n) return; list.unshift({ id: "p" + Date.now().toString(36), name: n, instr: "", convs: [] }); wr("L8_projects", list); render(body, close); };
      body.append(add);
      if (!list.length) body.append(el("div", "lib-empty", "Un projet regroupe des discussions autour d'un même sujet, avec des instructions qui s'appliquent à toutes."));
      list.forEach((p) => {
        const r = el("div", "lib-item"); r.innerHTML = '<div class="lib-ico" style="background:var(--accent-soft);color:var(--accent)"></div><div class="lib-info"><div class="lib-name"></div><div class="lib-sub"></div></div>';
        r.querySelector(".lib-ico").innerHTML = ICO('<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>');
        r.querySelector(".lib-name").textContent = p.name; r.querySelector(".lib-sub").textContent = (p.convs || []).length + " discussion(s)";
        r.onclick = () => detail(p.id, body, close); body.append(r);
      });
    });
  }
  function detail(pid, body, close) {
    const all = projects(), p = all.find((x) => x.id === pid); if (!p) return;
    const persist = () => wr("L8_projects", all);
    body.innerHTML = "";
    const h = el("div", "lib-name", p.name); h.style.cssText = "font-size:16px;padding:4px 8px 8px"; body.append(h);
    const ta = el("textarea", "modal-inp"); ta.rows = 4; ta.maxLength = 800; ta.value = p.instr || ""; ta.placeholder = "Instructions du projet (contexte, objectif, règles)…"; ta.style.cssText = "width:100%;resize:vertical;margin:0 0 8px";
    ta.onblur = () => { p.instr = ta.value.trim(); persist(); };
    body.append(ta);
    const mk = (t, fn, cls) => { const b = el("button", cls || "mbtn s", t); b.type = "button"; b.style.margin = "2px 4px 6px 0"; b.onclick = fn; return b; };
    const reload = () => { persist(); detail(pid, body, close); };
    body.append(
      mk("+ Nouvelle discussion", () => { p.instr = ta.value.trim(); newConv(); p.convs = [ST.convs.cur].concat(p.convs || []); persist(); close(); closeBar(); toast("Discussion créée dans « " + p.name + " »"); }, "mbtn p"),
      mk("Ajouter une existante", () => {
        const free = ST.convs.list.filter((c) => !(p.convs || []).includes(c.id));
        if (!free.length) return toast("Aucune autre discussion disponible");
        body.innerHTML = ""; body.append(el("div", "lib-sub", "Choisis une discussion à ajouter :"));
        free.forEach((c) => { const r = el("div", "lib-item"); r.append(el("div", "lib-name", c.title)); r.onclick = () => { p.convs = (p.convs || []).concat(c.id); reload(); }; body.append(r); });
      }),
      mk("Supprimer le projet", async () => { if (await L8ui.confirm("Supprimer « " + p.name + " » ? Les discussions sont conservées.", { danger: true, ok: "Supprimer" })) { wr("L8_projects", all.filter((x) => x.id !== pid)); close(); openProjects(); } })
    );
    (p.convs || []).forEach((cid) => {
      const c = ST.convs.list.find((x) => x.id === cid); if (!c) return;
      const r = el("div", "lib-item"); const info = el("div", "lib-info"); info.append(el("div", "lib-name", c.title)); r.append(info);
      info.onclick = () => { close(); closeBar(); loadConv(cid); };
      const x = el("button", "lib-act", "✕"); x.type = "button"; x.setAttribute("aria-label", "Retirer du projet"); x.onclick = () => { p.convs = p.convs.filter((i) => i !== cid); reload(); };
      r.append(x); body.append(r);
    });
  }

  /* Explorer : idées de demandes prêtes à lancer */
  const IDEAS = [
    ["Études", [["Explique la dérivée avec 3 exemples progressifs et un exercice corrigé"], ["Fais-moi un plan de révision de 4 semaines pour le BAC en maths"], ["Aide-moi à structurer une dissertation de philosophie sur la liberté"]]],
    ["Code et jeux", [["Crée un jeu du serpent en HTML avec score et niveaux"], ["Écris un script Python qui lit un fichier CSV et affiche des statistiques"], ["Explique cette erreur et propose une correction : ", true]]],
    ["Écriture", [["Rédige un email professionnel poli pour demander un délai supplémentaire"], ["Résume ce texte en 5 points clés : ", true], ["Corrige l'orthographe et améliore le style de ce texte : ", true]]],
    ["Créer", [["Génère un paysage africain au coucher du soleil"], ["y = A*sin(k*x)*exp(-0.1*x)"]]],
  ];
  function openExplore() {
    L8sheet("Explorer", (body, close) => {
      IDEAS.forEach(([cat, items]) => {
        const t = el("div", "sb-sec", cat); t.style.padding = "10px 8px 4px"; body.append(t);
        items.forEach(([txt, fill]) => {
          const r = el("div", "lib-item"); r.append(el("div", "lib-name", txt)); r.querySelector(".lib-name").style.whiteSpace = "normal";
          r.onclick = () => { close(); closeBar(); if (fill) { setInp(txt); $("userInp").focus(); } else qs(txt); };
          body.append(r);
        });
      });
    });
  }

  /* Abonnement : état honnête, aucun paiement possible tant qu'un prestataire n'est pas branché et vérifié côté serveur */
  function openPlans() {
    L8sheet("Abonnement", (body) => {
      const NAMES = { free: "Gratuit", pro: "Pro", max: "Max" };
      const Lm = (v) => v == null ? "illimité" : String(v);
      const card = (title, badge, lines, current) => {
        const c = el("div", "lib-item"); c.style.cssText = "display:block;cursor:default;border:1px solid " + (current ? "var(--accent)" : "var(--border)") + ";margin:6px 8px;border-radius:14px;padding:14px";
        const h = el("div", "lib-name", title + "  "); h.style.fontSize = "16px"; if (badge) h.append(el("span", "s-badge", badge)); c.append(h);
        lines.forEach((l) => { const d = el("div", "lib-sub", l); d.style.marginTop = "6px"; c.append(d); }); return c;
      };
      const draw = (st) => {   // st = réponse réelle du serveur, "loading", ou null
        body.innerHTML = "";
        if (!st || st === "loading") { body.append(el("div", "lib-empty", st === "loading" ? "Chargement…" : "Statut indisponible pour l'instant (connexion au serveur impossible).")); return; }
        const note = el("div", "lib-sub", "Les limites se comptent en unités : un message simple = 1 unité, un message avancé (modèle Prime, recherche, photo) = " + st.prime_units + " unités. Plafond par jour et par semaine."); note.style.cssText = "padding:4px 16px 8px;line-height:1.5"; body.append(note);
        st.catalog.forEach((c) => {
          const cur = c.plan === st.plan;
          const lines = [Lm(c.units_day) + " unités par jour · " + Lm(c.units_week) + " par semaine", Lm(c.images_day) + " analyses de photos par jour"];
          if (c.plan !== "free") lines.unshift(c.price_eur + " € par mois · paiement pas encore disponible");
          if (cur && st.expires_at) lines.push("Actif jusqu'au " + new Date(st.expires_at * 1000).toLocaleDateString("fr-FR") + ".");
          if (cur) lines.push("Aujourd'hui : " + st.usage.units + " / " + Lm(st.limits.units_day) + " unités · cette semaine : " + st.usage.week_units + " / " + Lm(st.limits.units_week) + " · photos : " + st.usage.images + " / " + Lm(st.limits.images_day));
          body.append(card(NAMES[c.plan], cur ? "Ton plan" : "", lines, cur));
        });
        const ct = el("div", "lib-sub"); ct.style.cssText = "padding:12px 16px;line-height:1.8";
        const a = el("a", "", CONTACT_MAIL); a.href = "mailto:" + CONTACT_MAIL; const t = el("a", "", CONTACT_TEL_FMT); t.href = "tel:" + CONTACT_TEL;
        [a, t].forEach((x) => x.style.color = "var(--accent)");
        ct.append("Une question ou une demande ? Écris-nous : ", a, " · ", t); body.append(ct);
      };
      draw("loading");
      fetch(AUTH_API.replace("/auth", "") + "/billing/status", { headers: authHeaders() })
        .then((r) => r.ok ? r.json() : null).then((st) => { if (st && st.plan) { draw(st); setPlanLabel(st); } else draw(null); }).catch(() => draw(null));
    });
  }
  function setPlanLabel(st) { const e = document.querySelector(".sb-plan"); if (e && st) e.textContent = "Lumina · " + ({ pro: "Pro", max: "Max" }[st.plan] || "Gratuit"); }

  guard("planlabel", () => {
    const mb = $("menuBtn"); if (!mb) return;
    mb.addEventListener("click", () => { if (!ST.token) return; fetch(AUTH_API.replace("/auth", "") + "/billing/status", { headers: authHeaders() }).then((r) => r.ok ? r.json() : null).then(setPlanLabel).catch(() => {}); });
  });

  guard("nav", () => {
    const anchor = $("navStg"); if (!anchor) return;
    [["navExplore", "Explorer", ICO('<circle cx="12" cy="12" r="10"/><polygon points="16.2 7.8 14.1 14.1 7.8 16.2 9.9 9.9 16.2 7.8"/>'), openExplore],
     ["navProjects", "Projets", ICO('<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>'), openProjects],
     ["navCustom", "Personnaliser", ICO('<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>'), openCustom],
     ["navPlans", "Abonnement", ICO('<path d="M19 7V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-2"/><path d="M21 12h-5a2 2 0 0 0 0 4h5z"/>'), openPlans]
    ].forEach(([id, label, svg, fn]) => {
      if ($(id)) return; const d = el("div", "sb-nav-item"); d.id = id; d.innerHTML = svg; d.append(label);
      d.onclick = () => { closeBar(); fn(); }; anchor.parentNode.insertBefore(d, anchor);
    });
  });
})();

/* ── Boîtes de dialogue intégrées · menu latéral · écran « Ajouter au chat » ── */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const guard = (n, fn) => { try { fn(); } catch (e) { console.error("[ui8:" + n + "]", e); } };
  const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
  const ICO = (d, extra) => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"' + (extra || "") + ">" + d + "</svg>";

  /* Dialogues : remplacent prompt() / confirm() du navigateur (qui affichaient l'adresse du serveur) */
  function dialog(title, build) {
    return new Promise((resolve) => {
      const m = el("div", "modal"); m.style.zIndex = "950";
      const box = el("div", "modal-box"); box.append(el("div", "modal-t", title));
      const done = (v) => { m.classList.remove("show"); setTimeout(() => m.remove(), 180); resolve(v); };
      build(box, done); m.appendChild(box); document.body.appendChild(m);
      m.addEventListener("click", (e) => { if (e.target === m) done(null); });
      requestAnimationFrame(() => m.classList.add("show"));
    });
  }
  window.L8ui = {
    prompt(title, o) {
      o = o || {};
      return dialog(title, (box, done) => {
        const inp = el("input", "modal-inp"); inp.value = o.value || ""; inp.placeholder = o.placeholder || ""; inp.maxLength = 80; inp.autocomplete = "off";
        const no = el("button", "mbtn s", "Annuler"), ok = el("button", "mbtn p", o.ok || "OK"); no.type = ok.type = "button";
        no.onclick = () => done(null); ok.onclick = () => done(inp.value);
        inp.onkeydown = (e) => { if (e.key === "Enter") done(inp.value); if (e.key === "Escape") done(null); };
        const row = el("div", "modal-btns"); row.append(no, ok); box.append(inp, row); setTimeout(() => { inp.focus(); inp.select(); }, 200);
      });
    },
    confirm(msg, o) {
      o = o || {};
      return dialog(o.title || "Confirmer", (box, done) => {
        const p = el("div", "lib-sub", msg); p.style.cssText = "margin:-4px 0 16px;line-height:1.5;font-size:14px;color:var(--text-secondary)";
        const no = el("button", "mbtn s", "Annuler"), ok = el("button", "mbtn p", o.ok || "OK"); no.type = ok.type = "button";
        if (o.danger) ok.style.background = "var(--err)";
        no.onclick = () => done(false); ok.onclick = () => done(true);
        const row = el("div", "modal-btns"); row.append(no, ok); box.append(p, row);
      }).then((v) => v === true);
    },
  };
  guard("settings-dialogs", () => {
    $("editProf").onclick = async () => {
      $("stgModal").classList.remove("show");
      const n = await L8ui.prompt("Votre prénom", { value: ST.user });
      if (n == null) return;
      ST.user = (n || "").trim() || ST.user; localStorage.setItem("L5_u", ST.user); updConvName(); toast("Profil mis à jour");
    };
    $("clearAllBtn").onclick = async () => {
      if (!(await L8ui.confirm("Effacer toutes les conversations ?", { danger: true, ok: "Effacer" }))) return;
      ST.convs = { cur: null, list: [] }; ST.hist = {}; ST.pins = [];
      save(); newConv(); $("stgModal").classList.remove("show"); toast("Conversations effacées");
    };
  });

  /* Menu latéral : « Signaler un problème » en icône dans le pied ; le reste est dans l'écran (+) */
  guard("sidebar", () => {
    const foot = document.querySelector(".sb-foot"), rep = $("navReport");
    if (foot && rep) { rep.classList.add("sb-icon-only"); rep.setAttribute("aria-label", "Signaler un problème"); rep.title = "Signaler un problème"; foot.appendChild(rep); }
  });

  /* Écran « Ajouter au chat » */
  const TG = (on) => '<div class="tgl' + (on ? " on" : "") + '"></div>';
  function projectName() {
    try { const p = (JSON.parse(localStorage.getItem("L8_projects") || "[]")).find((x) => (x.convs || []).includes(ST.convs.cur)); return p ? p.name : "Aucun"; } catch (e) { return "Aucun"; }
  }
  function openAdd() {
    document.querySelectorAll(".add-ov").forEach((x) => x.remove());
    const ov = el("div", "add-ov"), sh = el("div", "add-sheet");
    const close = () => { ov.classList.remove("show"); setTimeout(() => ov.remove(), 200); };
    const head = el("div", "add-head"), x = el("button", "add-x"); x.type = "button"; x.setAttribute("aria-label", "Fermer");
    x.innerHTML = ICO('<path d="M18 6L6 18M6 6l12 12"/>'); x.onclick = close; head.append(x, el("div", "add-title", "Ajouter au chat"));
    const body = el("div", "add-body");
    const go = (fn) => () => { close(); setTimeout(fn, 60); };

    const tiles = el("div", "add-tiles");
    const cam = el("input"); cam.type = "file"; cam.accept = "image/*"; cam.setAttribute("capture", "environment"); cam.style.display = "none";
    cam.onchange = (e) => $("imgInp").onchange(e);
    [["Caméra", ICO('<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>'), () => cam.click()],
     ["Photos", ICO('<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>'), () => $("imgInp").click()],
     ["Fichiers", ICO('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><polyline points="9 15 12 12 15 15"/>'), () => $("fileInp").click()]
    ].forEach(([label, svg, fn]) => {
      const t = el("button", "add-tile"); t.type = "button"; const ic = el("span", "add-tile-ic"); ic.innerHTML = svg; t.append(ic, label);
      t.onclick = () => { fn(); if (label !== "Caméra") close(); else setTimeout(close, 300); }; tiles.appendChild(t);
    });
    tiles.appendChild(cam);

    const row = (svg, title, sub, opt) => {
      opt = opt || {}; const r = el("div", "add-row"); const ic = el("span", "add-row-ic"); ic.innerHTML = svg;
      const tx = el("div", "add-row-tx"); tx.append(el("div", "add-row-t", title)); if (sub) { const s = el("div", "add-row-s", sub); if (opt.accent) s.style.color = "var(--accent)"; tx.append(s); }
      r.append(ic, tx);
      if (opt.toggle) { const w = el("div"); w.innerHTML = TG(opt.toggle()); const t = w.firstChild; r.appendChild(t); r.onclick = () => { opt.flip(); t.classList.toggle("on", !!opt.toggle()); }; }
      else { const ch = el("span", "add-row-ch"); ch.innerHTML = ICO('<polyline points="9 18 15 12 9 6"/>'); r.appendChild(ch); r.onclick = opt.onclick; }
      return r;
    };
    const grp = (...rows) => { const g = el("div", "add-grp"); rows.forEach((r) => g.appendChild(r)); return g; };
    const planTxt = (document.querySelector(".sb-plan") || {}).textContent || "";

    const toolsOpen = () => { const pm = $("plusMenu"); if (pm) { pm.classList.add("show"); $("plusBtn").classList.add("open"); } };
    body.append(tiles,
      grp(row(ICO('<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>'), "Changer de projet", projectName(), { accent: true, onclick: go(() => $("navProjects").click()) })),
      grp(row(ICO('<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>'), "Recherche web", null,
            { toggle: () => CFG.web, flip: () => { CFG.web = !CFG.web; saveCfg("web", CFG.web); applyCfg(); } }),
          row(ICO('<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>'), "Lecture automatique", null,
            { toggle: () => CFG.autoTTS, flip: () => { CFG.autoTTS = !CFG.autoTTS; saveCfg("tts", CFG.autoTTS); applyCfg(); } }),
          row(ICO('<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94z"/>'), "Outils Lumina", "Graphique, image, musique, vision, gestes", { onclick: go(() => L8tools()) })),
      grp(row(ICO('<circle cx="12" cy="12" r="10"/><polygon points="16.2 7.8 14.1 14.1 7.8 16.2 9.9 9.9 16.2 7.8"/>'), "Explorer", null, { onclick: go(() => $("navExplore").click()) }),
          row(ICO('<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>'), "Personnaliser", null, { onclick: go(() => $("navCustom").click()) }),
          row(ICO('<path d="M19 7V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-2"/><path d="M21 12h-5a2 2 0 0 0 0 4h5z"/>'), "Abonnement", planTxt.replace("Lumina · ", ""), { onclick: go(() => $("navPlans").click()) }),
          row(ICO('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>'), "Paramètres", null, { onclick: go(() => $("navStg").click()) }),
          row(ICO('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>'), "Conditions d'utilisation", null, { onclick: go(() => L8legal("terms")) }),
          row(ICO('<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>'), "Politique de confidentialité", null, { onclick: go(() => L8legal("privacy")) })));

    sh.append(head, body); ov.appendChild(sh); document.body.appendChild(ov);
    ov.addEventListener("click", (e) => { if (e.target === ov) close(); });
    let y0 = null, dy = 0;   // glisser vers le bas depuis l'en-tête pour fermer
    head.addEventListener("touchstart", (e) => { y0 = e.touches[0].clientY; dy = 0; }, { passive: true });
    head.addEventListener("touchmove", (e) => { if (y0 == null) return; dy = e.touches[0].clientY - y0; if (dy > 0) sh.style.transform = "translateY(" + dy + "px)"; }, { passive: true });
    head.addEventListener("touchend", () => { if (y0 == null) return; if (dy > 100) close(); else sh.style.transform = ""; y0 = null; });
    requestAnimationFrame(() => ov.classList.add("show"));
  }
  guard("plus", () => { const b = $("plusBtn"); if (b) b.onclick = (e) => { e.stopPropagation(); openAdd(); }; });
})();


/* ── Sources (« Lu N pages »), réflexion dépliable, documents légaux, écran de connexion ── */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const guard = (n, fn) => { try { fn(); } catch (e) { console.error("[ui8:" + n + "]", e); } };
  const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
  const SVG = (d) => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + d + "</svg>";
  const safeUrl = (u) => { try { const x = new URL(u); return x.protocol === "http:" || x.protocol === "https:" ? x.href : null; } catch (e) { return null; } };
  const hue = (s) => { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360; return h; };

  /* Réflexion : durée réellement mesurée par le serveur ; repliée par défaut */
  guard("reason", () => {
    window.buildReasonPanel = function (reasoning) {
      if (!reasoning || !String(reasoning).trim()) return null;
      const m = window.__metaFresh; let secs = null;
      if (m && Date.now() - m.t < 15000) { secs = m.s; window.__metaFresh = null; }
      const panel = el("div", "rp8"), head = el("button", "rp8-head"); head.type = "button";
      const label = secs == null ? "Réflexion" : secs < 1 ? "Réflexion pendant moins d'une seconde" : "Réflexion pendant " + Math.round(secs) + " seconde" + (Math.round(secs) > 1 ? "s" : "");
      head.append(el("span", "", label)); const ch = el("span", "rp8-ch"); ch.innerHTML = SVG('<polyline points="9 18 15 12 9 6"/>'); head.appendChild(ch);
      const body = el("div", "rp8-body"); body.append(el("div", "rp8-txt", String(reasoning).trim()));
      head.onclick = () => panel.classList.toggle("open");
      panel.append(head, body); return panel;
    };
  });

  /* Sources : « Lu N pages » seulement pour des pages réellement lues ; sinon « N sources » */
  function openSources(list) {
    L8sheet("Résultats de recherche", (body) => {
      list.forEach((s, i) => {
        const url = safeUrl(s.href), it = el("div", "src8-item");
        const top = el("div", "src8-top"); top.append(el("span", "src8-site", s.source || "Web"), el("span", "src8-num", String(i + 1)));
        it.append(top, el("div", "src8-title", s.title || s.source || "Source"));
        if (s.snippet) it.append(el("div", "src8-snip", s.snippet));
        if (s.read) it.append(el("div", "src8-read", "Page lue par Lumina"));
        if (url) it.onclick = () => window.open(url, "_blank", "noopener"); else it.style.cursor = "default";
        body.appendChild(it);
      });
    });
  }
  guard("sources", () => {
    window.buildSourcesRow = function (sources) {
      if (!sources || !sources.length) return null;
      const read = sources.filter((s) => s.read).length, n = read || sources.length;
      const row = el("button", "src8-row"); row.type = "button";
      const av = el("span", "src8-avs");
      [...new Set(sources.map((s) => s.source || "Web"))].slice(0, 4).forEach((d) => {
        const a = el("span", "src8-av", (d.replace(/^www\./, "")[0] || "W").toUpperCase()); a.style.background = "hsl(" + hue(d) + ",45%,38%)"; av.appendChild(a);
      });
      row.append(el("span", "src8-lbl", read ? "Lu " + n + " page" + (n > 1 ? "s" : "") : n + " source" + (n > 1 ? "s" : "")), av);
      const ch = el("span", "src8-ch"); ch.innerHTML = SVG('<polyline points="9 18 15 12 9 6"/>'); row.appendChild(ch);
      row.onclick = () => openSources(sources); return row;
    };
  });

  /* Documents légaux : le contenu vient des pages publiques /privacy et /terms (une seule source de vérité) */
  window.L8legal = function (which) {
    const path = which === "privacy" ? "/privacy.html" : "/terms.html", title = which === "privacy" ? "Politique de confidentialité" : "Conditions d'utilisation";
    L8sheet(title, (body) => {
      body.textContent = "Chargement…"; body.style.padding = "8px 18px 24px";
      fetch(AUTH_API.replace("/auth", "") + path).then((r) => r.ok ? r.text() : Promise.reject(new Error("http")))
        .then((html) => {
          const main = new DOMParser().parseFromString(html, "text/html").querySelector("main"); if (!main) throw new Error("vide");
          const w = el("div", "legal8"); w.innerHTML = main.innerHTML; w.querySelector("h1") && w.querySelector("h1").remove();
          w.querySelectorAll('a[href="/privacy"],a[href="/terms"]').forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); L8legal(a.getAttribute("href") === "/privacy" ? "privacy" : "terms"); }));
          body.textContent = ""; body.appendChild(w);
        }).catch(() => { body.textContent = "Impossible de charger ce document pour l'instant. Il reste consultable sur " + path + "."; });
    });
  };
  guard("auth-legal", () => {
    const box = document.querySelector(".auth-box"); if (!box) return;
    const d = el("div", "auth-legal"); d.append("En continuant, tu acceptes les ");
    const a = el("a", "", "Conditions d'utilisation"); a.href = "/terms"; a.target = "_blank"; a.rel = "noopener";
    const b = el("a", "", "Politique de confidentialité"); b.href = "/privacy"; b.target = "_blank"; b.rel = "noopener";
    d.append(a, " et la ", b, "."); box.appendChild(d);
  });

  /* Génération de musique : indisponible tant qu'elle n'a pas de fournisseur fiable (pas de bouton qui échoue) */
  guard("music", () => {
    window.genMusic = async function () { await streamResp("La génération de musique n'est pas encore disponible. Tu peux me demander « Joue … » pour lancer un morceau libre de droits."); };
  });
})();

/* ── Vérification d'email et mot de passe oublié (codes à 6 chiffres, saisis dans l'appli) ── */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const guard = (n, fn) => { try { fn(); } catch (e) { console.error("[ui8:" + n + "]", e); } };
  const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };

  /* Écran plein écran réutilisant le style de la connexion */
  function screen(id, title, sub) {
    document.getElementById(id) && document.getElementById(id).remove();
    const scr = el("div", "auth-scr"); scr.id = id; scr.style.zIndex = "9100";
    const box = el("div", "auth-box"); const h = el("div", "logo-name", title); h.style.cssText = "font-size:22px;text-align:center";
    box.append(h); if (sub) { const p = el("div", "auth-hint", sub); p.style.lineHeight = "1.6"; box.append(p); }
    const err = el("div", "auth-err"); box.append(err); scr.appendChild(box); document.body.appendChild(scr);
    const showErr = (m) => { err.textContent = m; err.style.display = "block"; };
    const hideErr = () => { err.style.display = "none"; };
    return { scr, box, showErr, hideErr, close: () => scr.remove() };
  }
  const input = (type, ph, ac) => { const i = el("input", "auth-inp"); i.type = type; i.placeholder = ph; if (ac) i.autocomplete = ac; return i; };
  const button = (label, primary) => { const b = el("button", primary ? "auth-submit" : "neutral-btn", label); b.type = "button"; if (!primary) b.style.justifyContent = "center"; return b; };
  const post = (path, body, withAuth) => fetch(AUTH_API + path, { method: "POST", headers: Object.assign({ "Content-Type": "application/json" }, withAuth ? authHeaders() : {}), body: JSON.stringify(body || {}) })
    .then(async (r) => ({ ok: r.ok, status: r.status, data: await r.json().catch(() => ({})) }));

  /* Vérification : l'accès à Lumina reste fermé tant que le code n'est pas saisi */
  function showVerify(onDone) {
    const s = screen("l8Verify", "Vérifie ton email", "Nous avons envoyé un code à 6 chiffres à " + (ST.email || "ton adresse") + ". Il est valable 15 minutes.");
    const code = input("text", "Code à 6 chiffres", "one-time-code"); code.inputMode = "numeric"; code.maxLength = 6; code.style.textAlign = "center"; code.style.letterSpacing = ".3em"; code.style.fontSize = "20px";
    const ok = button("Vérifier", true), again = button("Renvoyer le code"), out = button("Se déconnecter");
    ok.onclick = async () => {
      s.hideErr(); ok.disabled = true;
      try {
        const r = await post("/verify", { code: code.value.trim() }, true);
        if (r.ok) { window.__emailVerified = true; s.close(); onDone(); } else s.showErr(r.data.error || "Code invalide ou expiré");
      } catch (e) { s.showErr("Impossible de joindre le serveur."); } finally { ok.disabled = false; }
    };
    code.addEventListener("keydown", (e) => { if (e.key === "Enter") ok.click(); });
    again.onclick = async () => {
      s.hideErr();
      try { const r = await post("/resend", {}, true); if (r.ok) toast("Code renvoyé"); else s.showErr(r.data.error || "Envoi impossible"); } catch (e) { s.showErr("Impossible de joindre le serveur."); }
    };
    out.onclick = () => { s.close(); logout(); };
    s.box.append(code, ok, again, out); setTimeout(() => code.focus(), 150);
  }
  guard("verify-hooks", () => {
    const origApply = window.applyAuthUser;
    if (typeof origApply === "function") window.applyAuthUser = function (user) { window.__emailVerified = !(user && user.email_verified === false); return origApply.apply(this, arguments); };
    const origStart = window.startApp;
    if (typeof origStart === "function") window.startApp = function () {
      if (window.__emailVerified === false) { showVerify(() => origStart.apply(this, arguments)); return; }
      return origStart.apply(this, arguments);
    };
  });

  /* Mot de passe oublié : email -> code + nouveau mot de passe */
  function openForgot() {
    const s = screen("l8Forgot", "Mot de passe oublié", "Entre l'adresse de ton compte : nous t'envoyons un code à 6 chiffres.");
    const email = input("email", "Email", "email"); email.value = ($("authEmail") || {}).value || "";
    const send = button("Envoyer le code", true), back = button("Retour");
    back.onclick = s.close;
    send.onclick = async () => {
      s.hideErr(); const addr = email.value.trim().toLowerCase(); if (!addr) return s.showErr("Entre ton adresse email.");
      send.disabled = true;
      try {
        const r = await post("/forgot", { email: addr });
        if (r.ok) step2(addr); else s.showErr(r.data.error || "Une erreur est survenue.");
      } catch (e) { s.showErr("Impossible de joindre le serveur."); } finally { send.disabled = false; }
    };
    s.box.append(email, send, back);
    function step2(addr) {
      s.close();
      const t = screen("l8Forgot", "Nouveau mot de passe", "Si un compte existe pour " + addr + ", un code vient d'être envoyé. Il est valable 15 minutes.");
      const code = input("text", "Code à 6 chiffres", "one-time-code"); code.inputMode = "numeric"; code.maxLength = 6; code.style.textAlign = "center"; code.style.letterSpacing = ".3em"; code.style.fontSize = "20px";
      const pw = input("password", "Nouveau mot de passe (8 caractères minimum)", "new-password");
      const go = button("Changer le mot de passe", true), no = button("Annuler"); no.onclick = t.close;
      go.onclick = async () => {
        t.hideErr(); go.disabled = true;
        try {
          const r = await post("/reset", { email: addr, code: code.value.trim(), new_password: pw.value });
          if (r.ok) { t.close(); const ae = $("authEmail"); if (ae) ae.value = addr; const ap = $("authPw"); if (ap) ap.value = ""; toast("Mot de passe changé. Connecte-toi."); }
          else t.showErr(r.data.error || "Code invalide ou expiré");
        } catch (e) { t.showErr("Impossible de joindre le serveur."); } finally { go.disabled = false; }
      };
      t.box.append(code, pw, go, no); setTimeout(() => code.focus(), 150);
    }
  }
  guard("forgot-link", () => {
    const hint = $("authHint"); if (!hint || !hint.parentNode) return;
    const a = el("div", "auth-hint"); const l = el("a", "", "Mot de passe oublié ?"); l.style.cursor = "pointer"; l.onclick = openForgot; a.appendChild(l);
    hint.parentNode.insertBefore(a, hint.nextSibling);
  });
})();


/* ── Outils Lumina (médias, vision, graphique, image…) · repli des logos ── */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const guard = (n, fn) => { try { fn(); } catch (e) { console.error("[ui8:" + n + "]", e); } };
  const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };

  /* Les outils reprennent exactement les éléments de l'ancien menu (mêmes icônes SVG, mêmes actions).
     La génération de musique n'y figure pas tant qu'elle n'a pas de fournisseur fiable. */
  window.L8tools = function () {
    L8sheet("Outils Lumina", (body, close) => {
      const menu = $("plusMenu"); if (!menu) { body.textContent = "Outils indisponibles."; return; }
      const run = (node) => () => { close(); setTimeout(() => node.click(), 80); };
      const grid = el("div", "tools-grid");
      menu.querySelectorAll(".pm-item").forEach((it) => {
        if (it.id === "pmMusic") return;
        const t = el("button", "tool-tile"); t.type = "button";
        const ic = el("span", "tool-ic"); const src = it.querySelector(".pm-ico");
        if (src) { ic.innerHTML = src.innerHTML; ic.style.background = src.style.background; }
        t.append(ic, (it.querySelector(".pm-lbl") || {}).textContent || ""); t.onclick = run(it); grid.appendChild(t);
      });
      body.appendChild(grid);
      const skip = new Set(["pmToggleWeb", "pmToggleTTS", "pmOpenStg"]);   // déjà dans « Ajouter au chat »
      menu.querySelectorAll(".pm-trow").forEach((r) => {
        if (skip.has(r.id)) return;
        const row = el("div", "add-row"); row.style.cssText = "margin-top:10px;background:var(--surface);border-radius:16px";
        const ic = el("span", "add-row-ic"); const src = r.querySelector(".pm-tico"); if (src) ic.innerHTML = src.innerHTML;
        const tx = el("div", "add-row-tx"); tx.append(el("div", "add-row-t", (r.querySelector(".pm-tlbl") || {}).textContent || ""));
        row.append(ic, tx); row.onclick = run(r); body.appendChild(row);
      });
    });
  };

  /* Un logo qui ne se charge pas ne doit jamais s'afficher comme une image cassée : on le remplace par le SVG de Lumina */
  guard("logo-fallback", () => {
    const swap = (img) => {
      if (!img || img.dataset.l8 || !/\/icons\//.test(img.getAttribute("src") || "")) return;
      img.dataset.l8 = "1";
      const r = img.getBoundingClientRect(), w = Math.round(r.width) || 28, h = Math.round(r.height) || 28;
      const holder = document.createElement("span");
      holder.className = img.className; holder.style.cssText = img.style.cssText + ";display:inline-flex;align-items:center;justify-content:center;width:" + w + "px;height:" + h + "px;color:var(--accent)";
      holder.innerHTML = '<svg viewBox="0 0 40 24" fill="none" width="' + Math.round(w * 0.8) + '" height="' + Math.round(h * 0.5) + '"><use href="#luminaBrain" stroke="currentColor" stroke-width="1.8"/></svg>';
      img.replaceWith(holder);
    };
    document.addEventListener("error", (e) => { if (e.target && e.target.tagName === "IMG") swap(e.target); }, true);
    const sweep = () => document.querySelectorAll("img").forEach((i) => { if (i.complete && i.naturalWidth === 0) swap(i); });
    window.addEventListener("load", () => { sweep(); setTimeout(sweep, 1500); });
  });
})();
