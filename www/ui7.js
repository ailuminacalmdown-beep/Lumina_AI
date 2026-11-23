/* Lumina v7 — couche d'interactions. Chargé après le script principal de index.html
   (il réutilise ST, CFG, BASE, authHeaders, toast, applyCfg, closeBar, etc.). Chaque bloc est isolé :
   une erreur dans l'un ne doit jamais empêcher le chat de fonctionner. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const guard = (name, fn) => { try { fn(); } catch (e) { console.error("[ui7:" + name + "]", e); } };
  const animOff = () => localStorage.getItem("L5_anim") === "off";
  const haptic = (ms) => { try { if (!animOff() && navigator.vibrate) navigator.vibrate(ms); } catch (e) { /* ignoré */ } };

  /* ── Thème, mouvement ──────────────────────────────────────────────── */
  const THEME_COLOR = { dark: "#0d0d0d", amoled: "#000000", light: "#faf8f5" };
  function syncChrome() {
    document.body.classList.toggle("no-anim", animOff());
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta && typeof CFG !== "undefined") meta.setAttribute("content", THEME_COLOR[CFG.theme] || THEME_COLOR.dark);
    const sw = $("stglAnim");
    if (sw) sw.className = "stgl" + (animOff() ? "" : " on");
  }

  guard("theme", () => {
    if (typeof applyCfg === "function") {
      const orig = applyCfg;
      window.applyCfg = function () { orig(); syncChrome(); };
      window.applyCfg();     // applique aussi le thème sur l'écran de connexion
    }
    const item = $("themeItem");
    if (item) {
      item.onclick = () => {
        const order = ["dark", "amoled", "light"];
        CFG.theme = order[(order.indexOf(CFG.theme) + 1) % order.length];
        saveCfg("theme", CFG.theme);
        applyCfg();
        haptic(8);
      };
    }
    // Réglage « Animations » inséré sous « Thème »
    if (item && !$("animItem")) {
      const el = document.createElement("div");
      el.className = "s-item";
      el.id = "animItem";
      el.innerHTML = '<div class="s-il"><div class="s-ico" style="background:rgba(232,121,249,.13)"><svg viewBox="0 0 24 24" fill="none" stroke="#e879f9" stroke-width="2"><path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/></svg></div><div><div class="s-lbl">Animations</div><div class="s-val">Effets visuels et retours tactiles</div></div></div><div class="stgl on" id="stglAnim"></div>';
      item.insertAdjacentElement("afterend", el);
      el.onclick = () => {
        localStorage.setItem("L5_anim", animOff() ? "on" : "off");
        syncChrome();
      };
    }
    syncChrome();
  });

  /* ── Ondulation au toucher + retour haptique ───────────────────────── */
  guard("ripple", () => {
    const SEL = ".wchip,.pm-item,.sb-new,.mbtn,.auth-submit,.art-abtn,.mdl-card,.s-item,.cmd-item,.sb-nav-item,.neutral-btn,.danger-btn,.ci,.lv-btn-main,.lv-btn-sec";
    document.addEventListener("pointerdown", (e) => {
      if (animOff()) return;
      const t = e.target.closest && e.target.closest(SEL);
      if (!t) return;
      t.classList.add("rip-host");
      const r = t.getBoundingClientRect();
      const size = Math.max(r.width, r.height) * 2;
      const s = document.createElement("span");
      s.className = "rip";
      s.style.cssText = "width:" + size + "px;height:" + size + "px;left:" + (e.clientX - r.left - size / 2) + "px;top:" + (e.clientY - r.top - size / 2) + "px";
      t.appendChild(s);
      setTimeout(() => s.remove(), 650);
    }, { passive: true });
    document.addEventListener("pointerdown", (e) => {
      if (e.target.closest && e.target.closest(".send-btn,.plus-btn,.ibtn,.hbtn")) haptic(6);
    }, { passive: true });
  });

  /* ── Bouton d'envoi réactif, indicateur « l'IA travaille » ─────────── */
  guard("send", () => {
    const inp = $("userInp"), sb = $("sendBtn");
    if (!inp || !sb) return;
    const sync = () => sb.classList.toggle("has-text", inp.value.trim().length > 0 && !sb.classList.contains("stop-mode"));
    inp.addEventListener("input", sync);
    if (typeof autoRsz === "function") {
      const orig = autoRsz;
      window.autoRsz = function () { orig(); sync(); };
    }
    new MutationObserver(() => {
      document.body.classList.toggle("ai-busy", sb.classList.contains("stop-mode"));
      sync();
    }).observe(sb, { attributes: true, attributeFilter: ["class"] });
  });

  /* ── Bouton « retour en bas » ───────────────────────────────────────── */
  guard("fab", () => {
    const chat = $("chat");
    if (!chat) return;
    const fab = document.createElement("button");
    fab.className = "fab-down";
    fab.setAttribute("aria-label", "Aller au dernier message");
    fab.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>';
    document.body.appendChild(fab);
    fab.onclick = () => chat.scrollTo({ top: chat.scrollHeight, behavior: animOff() ? "auto" : "smooth" });
    let ticking = false;
    chat.addEventListener("scroll", () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        fab.classList.toggle("show", chat.scrollHeight - chat.scrollTop - chat.clientHeight > 260);
        ticking = false;
      });
    }, { passive: true });
  });

  /* ── Geste : balayer depuis le bord gauche pour ouvrir, vers la gauche pour fermer ── */
  guard("swipe", () => {
    let sx = 0, sy = 0, edge = false, inSide = false, active = false;
    document.addEventListener("touchstart", (e) => {
      if (e.touches.length !== 1) { active = false; return; }
      const t = e.touches[0];
      sx = t.clientX; sy = t.clientY; active = true;
      const sb = $("sidebar");
      edge = sx < 22 && !(sb && sb.classList.contains("open"));
      inSide = !!(sb && sb.classList.contains("open") && e.target.closest && e.target.closest("#sidebar"));
    }, { passive: true });
    document.addEventListener("touchend", (e) => {
      if (!active) return;
      active = false;
      const t = e.changedTouches[0];
      const dx = t.clientX - sx, dy = Math.abs(t.clientY - sy);
      if (dy > 60) return;
      if (edge && dx > 70) { const b = $("menuBtn"); if (b) b.click(); }
      else if (inSide && dx < -70) { const b = $("closeSb"); if (b) b.click(); }
    }, { passive: true });
  });

  /* ── Logo vivant : inclinaison (doigt/souris/gyroscope), éclat, étincelles au toucher ── */
  guard("logo", () => {
    let raf = 0, last = 0;
    const apply = (rx, ry) => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        document.querySelectorAll(".lum-logo").forEach((l) => {
          l.style.setProperty("--rx", rx.toFixed(1) + "deg");
          l.style.setProperty("--ry", ry.toFixed(1) + "deg");
        });
      });
    };
    const clamp = (v, m) => Math.max(-m, Math.min(m, v));
    document.addEventListener("pointermove", (e) => {
      if (animOff()) return;
      const l = document.querySelector(".lum-logo");
      if (!l || !l.offsetParent) return;
      const r = l.getBoundingClientRect();
      const dx = (e.clientX - (r.left + r.width / 2)) / 220;
      const dy = (e.clientY - (r.top + r.height / 2)) / 260;
      last = Date.now();
      apply(clamp(dx * 18, 18), clamp(-dy * 14, 14));
    }, { passive: true });
    window.addEventListener("deviceorientation", (e) => {
      if (animOff() || Date.now() - last < 1500 || e.gamma == null) return;
      apply(clamp(e.gamma / 3, 14), clamp(-((e.beta || 60) - 60) / 4, 12));
    }, { passive: true });
    document.addEventListener("click", (e) => {
      const l = e.target.closest && e.target.closest(".lum-logo");
      if (!l || animOff()) return;
      l.classList.remove("pop"); void l.offsetWidth; l.classList.add("pop");
      haptic(14);
      for (let i = 0; i < 14; i++) {
        const p = document.createElement("i");
        p.className = "lum-burst";
        const a = (Math.PI * 2 * i) / 14 + Math.random() * 0.4, d = 52 + Math.random() * 46;
        p.style.cssText = "left:50%;top:50%;--dx:" + (Math.cos(a) * d).toFixed(0) + "px;--dy:" + (Math.sin(a) * d).toFixed(0) + "px";
        l.appendChild(p);
        setTimeout(() => p.remove(), 900);
      }
    });
    document.addEventListener("visibilitychange", () => document.body.classList.toggle("lum-paused", document.hidden));
  });

  /* ── Menu « + » : entrée échelonnée ────────────────────────────────── */
  guard("plus", () => {
    document.querySelectorAll(".plus-menu .pm-item").forEach((el, i) => el.style.setProperty("--i", i));
  });

  /* ── Légal / signalement / suppression de compte ───────────────────── */
  guard("account", () => {
    const rep = $("navReport");
    if (rep) rep.onclick = () => {
      try { closeBar(); } catch (e) { /* ignoré */ }
      const cid = $("reportConvId"); if (cid) cid.value = ST.convs.cur || "";
      const m = $("reportModal"); if (m) m.classList.add("show");
    };

    const m = document.createElement("div");
    m.className = "modal";
    m.id = "delAccModal";
    m.innerHTML = '<div class="modal-box"><div class="modal-t">Supprimer mon compte</div>' +
      '<p style="font-size:13px;color:var(--text-secondary);margin-bottom:12px;line-height:1.55">Action définitive : ton compte, ta mémoire et l\'historique conservé sur le serveur seront effacés. Les discussions enregistrées sur cet appareil le seront aussi. Entre ton mot de passe pour confirmer.</p>' +
      '<input class="modal-inp" id="delAccPw" type="password" placeholder="Mot de passe" autocomplete="current-password">' +
      '<div class="modal-btns"><button class="mbtn s" id="delAccNo" type="button">Annuler</button><button class="mbtn p" id="delAccYes" type="button" style="background:var(--err)">Supprimer</button></div></div>';
    document.body.appendChild(m);
    const close = () => { m.classList.remove("show"); $("delAccPw").value = ""; };
    $("delAccNo").onclick = close;
    const btn = $("deleteAccBtn");
    if (btn) btn.onclick = () => { const s = $("stgModal"); if (s) s.classList.remove("show"); m.classList.add("show"); setTimeout(() => $("delAccPw").focus(), 200); };
    $("delAccYes").onclick = async () => {
      const pw = $("delAccPw").value;
      if (!pw) { toast("Entre ton mot de passe"); return; }
      const yes = $("delAccYes"); yes.disabled = true;
      try {
        const r = await fetch(`${BASE}/auth/account`, { method: "DELETE", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify({ password: pw }) });
        if (r.ok) {
          Object.keys(localStorage).filter((k) => k.startsWith("L5_")).forEach((k) => localStorage.removeItem(k));
          toast("Compte supprimé");
          setTimeout(() => location.reload(), 600);
          return;
        }
        let msg = "Suppression impossible";
        try { const d = await r.json(); if (d.error) msg = d.error; } catch (e) { /* ignoré */ }
        toast(msg);
      } catch (e) { toast("Serveur injoignable"); }
      finally { yes.disabled = false; }
    };
  });
})();
