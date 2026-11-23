/* Lumina Live — caméra (avant/arrière) + voix en continu + commentaires spontanés.
 *
 * Flux :
 *   micro ─► détection de parole locale (VAD) ─► WAV 16 kHz ─► /live/stt (Whisper/Groq) ─► /live/respond (turn)
 *   caméra ─► détection de changement locale ─► image réduite ─► /live/respond (observe) ─► l'IA parle seule si utile
 *   L'IA parle (TTS) ; si l'utilisateur reprend la parole, elle se tait (interruption).
 *
 * Dépend des globaux de index.html : ST, RT, CFG, BASE, authHeaders, toast, speakFull, stopTTS, forceReauth,
 * save, renderMsgs, renderConvList, closePlus, stopVision, startVision.
 */
(function () {
  "use strict";

  const INTERVALS = {
    discret: { min: 20000, max: 60000, change: 16, label: "Discret" },
    normal:  { min: 12000, max: 35000, change: 11, label: "Normal" },
    bavard:  { min: 6000,  max: 20000, change: 7,  label: "Réactif" },
  };
  const LEVELS = ["discret", "normal", "bavard"];
  const END_SILENCE_MS = 900;      // silence qui termine une phrase
  const MAX_UTTER_MS = 25000;      // phrase maximale avant envoi forcé
  const MIN_VOICED_MS = 300;       // en dessous : bruit, on ignore
  const PREROLL_MS = 450;          // audio conservé avant la détection (début de phrase)
  const FRAME_W = 640;
  const FRAME_Q = 0.55;

  const prefs = {
    level: localStorage.getItem("L5_lv_level") || "normal",
    bargein: localStorage.getItem("L5_lv_bargein") !== "false",
  };
  if (!INTERVALS[prefs.level]) prefs.level = "normal";

  let S = null;       // session courante (null = Live fermé)
  let ui = null;      // références DOM
  let rafId = 0;

  const $ = (sel, root) => (root || document).querySelector(sel);
  const nowMs = () => performance.now();
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  const ICON = {
    flip: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 7h-3.2l-1.6-2H8.8L7.2 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2z"/><path d="M9 13a3 3 0 0 1 5.2-2M15 13a3 3 0 0 1-5.2 2"/><polyline points="14.5 9.5 14.5 11.5 12.5 11.5"/><polyline points="9.5 16.5 9.5 14.5 11.5 14.5"/></svg>',
    mic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8"/></svg>',
    micOff: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="1" y1="1" x2="23" y2="23"/><path d="M9 9v3a3 3 0 0 0 5.1 2.1M15 9.3V4a3 3 0 0 0-5.9-.8"/><path d="M19 10v2a7 7 0 0 1-.9 3.4M5 10v2a7 7 0 0 0 11.4 5.4M12 19v4M8 23h8"/></svg>',
    eye: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>',
    eyeOff: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.9 17.9A10.9 10.9 0 0 1 12 20c-7 0-11-8-11-8a18.5 18.5 0 0 1 5.1-5.9M9.9 4.2A9.1 9.1 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.2 3.2M14.1 14.1a3 3 0 1 1-4.2-4.2"/><line x1="1" y1="1" x2="23" y2="23"/></svg>',
    end: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>',
  };

  const STATE_TEXT = {
    starting: "Démarrage…",
    listening: "Je t'écoute",
    userSpeaking: "Je t'entends…",
    thinking: "Je réfléchis…",
    speaking: "Lumina parle",
    observing: "Je regarde…",
    paused: "En pause",
    error: "Problème",
  };

  // ─────────────────────────── Outils audio ───────────────────────────
  function downsample(buf, inRate, outRate) {
    if (outRate >= inRate) return buf;
    const ratio = inRate / outRate;
    const n = Math.floor(buf.length / ratio);
    const out = new Float32Array(n);
    let i = 0;
    for (let o = 0; o < n; o++) {
      const next = Math.floor((o + 1) * ratio);
      let sum = 0, c = 0;
      for (; i < next && i < buf.length; i++) { sum += buf[i]; c++; }
      out[o] = c ? sum / c : 0;
    }
    return out;
  }

  function encodeWav(f32, rate) {
    const buf = new ArrayBuffer(44 + f32.length * 2);
    const v = new DataView(buf);
    const str = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
    str(0, "RIFF"); v.setUint32(4, 36 + f32.length * 2, true); str(8, "WAVE");
    str(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
    v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
    str(36, "data"); v.setUint32(40, f32.length * 2, true);
    let off = 44;
    for (let i = 0; i < f32.length; i++) {
      const x = Math.max(-1, Math.min(1, f32[i]));
      v.setInt16(off, x < 0 ? x * 0x8000 : x * 0x7fff, true);
      off += 2;
    }
    return new Blob([v], { type: "audio/wav" });
  }

  function concatFloat32(chunks) {
    let n = 0;
    for (const c of chunks) n += c.length;
    const out = new Float32Array(n);
    let o = 0;
    for (const c of chunks) { out.set(c, o); o += c.length; }
    return out;
  }

  // ─────────────────────────── Interface ───────────────────────────
  function buildUI() {
    if (ui) return ui;
    const root = document.createElement("div");
    root.className = "lv";
    root.id = "lv";
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-label", "Lumina Live");
    root.dataset.state = "starting";
    root.innerHTML = `
      <video class="lv-video" playsinline muted autoplay></video>
      <div class="lv-shade"></div>
      <div class="lv-flash"></div>
      <div class="lv-top">
        <div class="lv-live"><span class="lv-dot"></span>LIVE</div>
        <div class="lv-status" id="lvStatus" aria-live="polite">Démarrage…</div>
        <div class="lv-chips">
          <button class="lv-chip" id="lvLevel" type="button"></button>
          <button class="lv-chip" id="lvBarge" type="button"></button>
        </div>
      </div>
      <div class="lv-stage">
        <div class="lv-orb"><i class="r1"></i><i class="r2"></i><i class="r3"></i><b class="core"></b></div>
        <div class="lv-bars" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div>
      </div>
      <div class="lv-caps">
        <div class="lv-cap lv-cap-user" id="lvCapUser"></div>
        <div class="lv-cap lv-cap-ai" id="lvCapAi"></div>
        <div class="lv-hint" id="lvHint">Parle naturellement. Touche l'image pour dire « regarde ça ».</div>
      </div>
      <div class="lv-err" id="lvErr" hidden>
        <div class="lv-err-box"><div id="lvErrMsg"></div><button class="lv-btn-main" id="lvErrRetry" type="button">Réessayer</button><button class="lv-btn-sec" id="lvErrClose" type="button">Fermer</button></div>
      </div>
      <div class="lv-ctrl">
        <button class="lv-btn" id="lvFlip" type="button" aria-label="Changer de caméra">${ICON.flip}</button>
        <button class="lv-btn" id="lvMic" type="button" aria-label="Couper le micro">${ICON.mic}</button>
        <button class="lv-btn" id="lvEye" type="button" aria-label="Suspendre la vision">${ICON.eye}</button>
        <button class="lv-btn lv-end" id="lvEnd" type="button" aria-label="Terminer le Live">${ICON.end}</button>
      </div>`;
    document.body.appendChild(root);
    ui = {
      root,
      video: $(".lv-video", root),
      status: $("#lvStatus", root),
      capUser: $("#lvCapUser", root),
      capAi: $("#lvCapAi", root),
      hint: $("#lvHint", root),
      err: $("#lvErr", root),
      errMsg: $("#lvErrMsg", root),
      bars: Array.from(root.querySelectorAll(".lv-bars i")),
      flash: $(".lv-flash", root),
      btnLevel: $("#lvLevel", root),
      btnBarge: $("#lvBarge", root),
      btnMic: $("#lvMic", root),
      btnEye: $("#lvEye", root),
      btnFlip: $("#lvFlip", root),
    };
    $("#lvEnd", root).onclick = () => close();
    $("#lvErrClose", root).onclick = () => close();
    ui.btnFlip.onclick = () => flipCamera();
    ui.btnMic.onclick = () => toggleMic();
    ui.btnEye.onclick = () => toggleVision();
    ui.btnLevel.onclick = () => {
      prefs.level = LEVELS[(LEVELS.indexOf(prefs.level) + 1) % LEVELS.length];
      localStorage.setItem("L5_lv_level", prefs.level);
      refreshChips();
      haptic(8);
    };
    ui.btnBarge.onclick = () => {
      prefs.bargein = !prefs.bargein;
      localStorage.setItem("L5_lv_bargein", String(prefs.bargein));
      refreshChips();
      haptic(8);
    };
    ui.video.addEventListener("click", () => askLook());
    return ui;
  }

  function refreshChips() {
    if (!ui) return;
    ui.btnLevel.textContent = "Commentaires : " + INTERVALS[prefs.level].label;
    ui.btnBarge.textContent = "Interruption : " + (prefs.bargein ? "oui" : "non");
    ui.btnBarge.classList.toggle("off", !prefs.bargein);
    if (S) {
      ui.btnMic.innerHTML = S.micOn ? ICON.mic : ICON.micOff;
      ui.btnMic.classList.toggle("off", !S.micOn);
      ui.btnEye.innerHTML = S.visionOn ? ICON.eye : ICON.eyeOff;
      ui.btnEye.classList.toggle("off", !S.visionOn);
      ui.btnMic.setAttribute("aria-label", S.micOn ? "Couper le micro" : "Activer le micro");
      ui.btnEye.setAttribute("aria-label", S.visionOn ? "Suspendre la vision" : "Reprendre la vision");
    }
  }

  function haptic(ms) { try { navigator.vibrate && navigator.vibrate(ms); } catch (e) { /* ignoré */ } }

  function setPhase(phase) {
    if (!S) return;
    S.phase = phase;
    if (!ui) return;
    ui.root.dataset.state = phase;
    ui.status.textContent = STATE_TEXT[phase] || "";
  }

  function showCaption(who, text) {
    if (!ui) return;
    const el = who === "user" ? ui.capUser : ui.capAi;
    el.textContent = text;
    el.classList.remove("show");
    void el.offsetWidth;   // relance l'animation
    el.classList.add("show");
    ui.hint.classList.add("gone");
  }

  function showError(msg, retry) {
    if (!ui) return;
    ui.errMsg.textContent = msg;
    ui.err.hidden = false;
    const btn = $("#lvErrRetry", ui.root);
    btn.style.display = retry ? "" : "none";
    btn.onclick = () => { ui.err.hidden = true; retry && retry(); };
    setPhase("error");
  }

  function pulseFlash() {
    if (!ui) return;
    ui.flash.classList.remove("on");
    void ui.flash.offsetWidth;
    ui.flash.classList.add("on");
  }

  function animLoop() {
    if (!S || !ui) return;
    const t = nowMs();
    let lvl = 0.04;
    if (S.phase === "userSpeaking") lvl = Math.min(1, S.level * 9);
    else if (S.phase === "speaking") lvl = 0.35 + 0.25 * Math.sin(t / 110) + 0.2 * Math.random();
    else if (S.phase === "thinking") lvl = 0.16 + 0.1 * Math.sin(t / 260);
    else if (S.phase === "listening") lvl = 0.06 + Math.min(0.2, S.level * 3);
    S.shown += (lvl - S.shown) * 0.25;
    ui.root.style.setProperty("--lvl", S.shown.toFixed(3));
    for (let i = 0; i < ui.bars.length; i++) {
      const h = 0.18 + S.shown * (0.5 + 0.5 * Math.sin(t / 120 + i * 1.3));
      ui.bars[i].style.transform = "scaleY(" + Math.max(0.12, Math.min(1, h)).toFixed(3) + ")";
    }
    rafId = requestAnimationFrame(animLoop);
  }

  // ─────────────────────────── Caméra ───────────────────────────
  async function startVideo(facing) {
    stopVideo();
    const base = { width: { ideal: 1280 }, height: { ideal: 720 } };
    const tries = [
      { video: Object.assign({ facingMode: { exact: facing } }, base) },
      { video: Object.assign({ facingMode: { ideal: facing } }, base) },
      { video: true },
    ];
    let stream = null, lastErr = null;
    for (const c of tries) {
      try { stream = await navigator.mediaDevices.getUserMedia(c); break; }
      catch (e) {
        lastErr = e;
        if (e && (e.name === "NotAllowedError" || e.name === "SecurityError")) break;
      }
    }
    if (!stream) throw lastErr || new Error("Caméra indisponible");
    const tr = stream.getVideoTracks()[0];
    const st = tr && tr.getSettings ? tr.getSettings() : {};
    S.facing = st.facingMode || facing;
    S.vStream = stream;
    ui.video.srcObject = stream;
    ui.video.classList.toggle("mirror", S.facing === "user");
    try { await ui.video.play(); } catch (e) { /* autoplay : la vidéo démarre au premier geste */ }
    tr.onended = () => {
      if (!S || S.closing || S.flipping) return;
      showError("La caméra a été interrompue (utilisée par une autre application ?).", () => startVideo(S.facing).catch(() => {}));
    };
    S.obsThumb = null;
    S.prevThumb = null;
  }

  function stopVideo() {
    if (S && S.vStream) {
      S.vStream.getTracks().forEach((t) => { t.onended = null; try { t.stop(); } catch (e) { /* ignoré */ } });
      S.vStream = null;
    }
    if (ui && ui.video) ui.video.srcObject = null;
  }

  async function flipCamera() {
    if (!S || S.flipping) return;
    S.flipping = true;
    const previous = S.facing;
    const next = previous === "user" ? "environment" : "user";
    ui.root.classList.add("flipping");
    haptic(12);
    try {
      await startVideo(next);
      showCaption("ai", next === "environment" ? "Caméra arrière" : "Caméra avant");
    } catch (e) {
      toast("Impossible de changer de caméra");
      try { await startVideo(previous); } catch (e2) { showError("Caméra indisponible.", () => startVideo(previous).catch(() => {})); }
    } finally {
      S.flipping = false;
      S.lastObsAt = nowMs();       // laisse la nouvelle image se stabiliser avant de commenter
      ui.root.classList.remove("flipping");
    }
  }

  function captureFrame(maxW, q) {
    const v = ui && ui.video;
    if (!v || !v.videoWidth) return null;
    const k = Math.min(1, maxW / v.videoWidth);
    const w = Math.max(1, Math.round(v.videoWidth * k)), h = Math.max(1, Math.round(v.videoHeight * k));
    const c = S.cap || (S.cap = document.createElement("canvas"));
    c.width = w; c.height = h;
    c.getContext("2d").drawImage(v, 0, 0, w, h);
    return c.toDataURL("image/jpeg", q);
  }

  function sampleThumb() {
    const v = ui && ui.video;
    if (!v || !v.videoWidth || v.readyState < 2) return null;
    const c = S.tcv || (S.tcv = document.createElement("canvas"));
    c.width = 32; c.height = 24;
    const x = c.getContext("2d", { willReadFrequently: true });
    x.drawImage(v, 0, 0, 32, 24);
    const d = x.getImageData(0, 0, 32, 24).data;
    const g = new Uint8Array(32 * 24);
    for (let i = 0, j = 0; i < d.length; i += 4, j++) g[j] = (d[i] * 3 + d[i + 1] * 6 + d[i + 2]) / 10;
    return g;
  }

  function diffThumb(a, b) {
    if (!a || !b) return 999;
    let s = 0;
    for (let i = 0; i < a.length; i++) s += Math.abs(a[i] - b[i]);
    return s / a.length;
  }

  // ─────────────────────────── Micro : détection de parole ───────────────────────────
  async function startMic() {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    S.aStream = stream;
    const Ctx = window.AudioContext || window.webkitAudioContext;
    const ctx = S.ctx || new Ctx();
    S.ctx = ctx;
    try { await ctx.resume(); } catch (e) { /* ignoré */ }
    const src = ctx.createMediaStreamSource(stream);
    const proc = ctx.createScriptProcessor(2048, 1, 1);
    const mute = ctx.createGain();
    mute.gain.value = 0;          // le micro n'est jamais rejoué dans les haut-parleurs
    src.connect(proc); proc.connect(mute); mute.connect(ctx.destination);
    proc.onaudioprocess = onAudio;
    S.src = src; S.proc = proc; S.mute = mute;
    S.micOn = true;
  }

  function stopMic() {
    if (!S) return;
    try { if (S.proc) { S.proc.onaudioprocess = null; S.proc.disconnect(); } } catch (e) { /* ignoré */ }
    try { if (S.src) S.src.disconnect(); } catch (e) { /* ignoré */ }
    try { if (S.mute) S.mute.disconnect(); } catch (e) { /* ignoré */ }
    if (S.aStream) S.aStream.getTracks().forEach((t) => { try { t.stop(); } catch (e) { /* ignoré */ } });
    if (S.ctx) { try { S.ctx.close(); } catch (e) { /* ignoré */ } }
    S.aStream = S.src = S.proc = S.mute = S.ctx = null;
  }

  function onAudio(e) {
    if (!S || S.closing || !S.micOn) return;
    const input = e.inputBuffer.getChannelData(0);
    const copy = new Float32Array(input);
    let sum = 0;
    for (let i = 0; i < copy.length; i++) sum += copy[i] * copy[i];
    const rms = Math.sqrt(sum / copy.length);
    S.level = S.level * 0.6 + rms * 0.4;
    const frameMs = (1000 * copy.length) / e.inputBuffer.sampleRate;
    S.rate = e.inputBuffer.sampleRate;

    const aiTalking = S.phase === "speaking";
    // Seuil adaptatif : plancher de bruit appris + marge. Plus haut quand l'IA parle (écho possible).
    const thr = aiTalking ? Math.max(S.noise * 3.2 + 0.03, 0.07) : Math.max(S.noise * 2.6 + 0.012, 0.02);
    const loud = rms > thr;
    if (!loud && !S.inUtter) S.noise = S.noise * 0.97 + rms * 0.03;

    if (!S.inUtter) {
      S.pre.push(copy);
      const keep = Math.ceil(PREROLL_MS / frameMs);
      while (S.pre.length > keep) S.pre.shift();
      S.loudMs = loud ? S.loudMs + frameMs : Math.max(0, S.loudMs - frameMs * 2);
      const need = aiTalking ? 420 : 140;
      if (S.loudMs >= need && (!aiTalking || prefs.bargein) && S.phase !== "error") startUtterance();
    } else {
      S.utter.push(copy);
      S.utterMs += frameMs;
      if (loud) { S.silenceMs = 0; S.voicedMs += frameMs; } else S.silenceMs += frameMs;
      if (S.silenceMs >= END_SILENCE_MS || S.utterMs >= MAX_UTTER_MS) endUtterance();
    }
  }

  function startUtterance() {
    S.inUtter = true;
    S.utter = S.pre.slice();
    S.pre = [];
    S.utterMs = 0;
    S.voicedMs = S.loudMs;
    S.silenceMs = 0;
    S.loudMs = 0;
    S.epoch++;                       // invalide toute observation en cours
    if (S.obsAbort) { try { S.obsAbort.abort(); } catch (e) { /* ignoré */ } }
    if (S.phase === "speaking") {    // interruption : l'IA se tait
      S.ttsTok++;
      stopTTS();
      S.interrupted++;
    }
    setPhase("userSpeaking");
    haptic(6);
  }

  function endUtterance() {
    S.inUtter = false;
    const chunks = S.utter;
    const voiced = S.voicedMs;
    S.utter = [];
    S.lastUserAt = nowMs();
    if (voiced < MIN_VOICED_MS) {            // bruit/toux : on ne bloque pas une réponse en attente
      if (S.pending) runTurn(); else setPhase("listening");
      return;
    }
    const raw = concatFloat32(chunks);
    const wav = encodeWav(downsample(raw, S.rate || 48000, 16000), 16000);
    setPhase("thinking");
    transcribe(wav);
  }

  // ─────────────────────────── Réseau ───────────────────────────
  function handleAuthFail(status) {
    if (status === 401) { close(); forceReauth(); return true; }
    return false;
  }

  async function transcribe(blob) {
    const ep = S.epoch;
    try {
      const fd = new FormData();
      fd.append("audio", blob, "u.wav");
      fd.append("lang", "fr");
      const r = await fetch(`${BASE}/live/stt`, { method: "POST", headers: authHeaders(), body: fd });
      if (!S) return;
      if (handleAuthFail(r.status)) return;
      if (!r.ok) { noteFailure(r.status); setPhase(S.pending ? "thinking" : "listening"); return; }
      const d = await r.json();
      const text = (d.text || "").trim();
      if (!text) {
        if (!S.inUtter) { if (S.pending) runTurn(); else setPhase("listening"); }
        return;
      }
      S.fails = 0;
      S.pending = S.pending ? S.pending + " " + text : text;
      showCaption("user", S.pending);
      if (ep !== S.epoch && S.inUtter) return;   // l'utilisateur parle encore : on attend la fin
      runTurn();
    } catch (e) {
      if (S) { noteFailure(0); setPhase("listening"); }
    }
  }

  async function runTurn() {
    if (!S || !S.pending) return;
    const my = ++S.turnEpoch;
    S.epoch++;
    if (S.turnAbort) { try { S.turnAbort.abort(); } catch (e) { /* ignoré */ } }
    S.turnAbort = new AbortController();
    setPhase("thinking");
    const text = S.pending;
    const frame = S.visionOn ? captureFrame(FRAME_W, FRAME_Q) : null;
    try {
      const r = await fetch(`${BASE}/live/respond`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ kind: "turn", conv_id: S.conv, text, image: frame, camera: S.facing, level: prefs.level }),
        signal: S.turnAbort.signal,
      });
      if (!S || my !== S.turnEpoch) return;
      if (handleAuthFail(r.status)) return;
      if (!r.ok) {
        noteFailure(r.status);
        setPhase("listening");
        showCaption("ai", r.status === 429 ? "Doucement, je reprends mon souffle…" : "Je n'arrive pas à répondre pour le moment.");
        return;
      }
      const d = await r.json();
      S.fails = 0;
      if (S.inUtter) return;             // il reparle : on garde pending et on attend la suite
      S.pending = "";
      S.exchanges.push({ user: text, assistant: d.reply });
      S.turns++;
      sayAloud(d.reply, true);
    } catch (e) {
      if (e && e.name === "AbortError") return;
      if (S) { noteFailure(0); setPhase("listening"); }
    }
  }

  function sayAloud(text, isReply) {
    if (!S) return;
    const tok = ++S.ttsTok;
    showCaption("ai", text);
    setPhase("speaking");
    S.lastAIAt = nowMs();
    S.recent.push(text);
    if (S.recent.length > 4) S.recent.shift();
    const done = () => {
      if (!S || tok !== S.ttsTok) return;       // interrompu ou périmé
      S.lastAIAt = nowMs();
      setPhase(S.inUtter ? "userSpeaking" : (S.pending ? "thinking" : "listening"));
    };
    try { speakFull(text, done); } catch (e) { done(); }
  }

  async function observe(force) {
    if (!S || S.observing) return;
    const frame = captureFrame(FRAME_W, FRAME_Q);
    if (!frame) return;
    S.observing = true;
    S.lastObsAt = nowMs();
    const ep = S.epoch;
    S.obsAbort = new AbortController();
    pulseFlash();
    ui.root.classList.add("observing");
    try {
      const r = await fetch(`${BASE}/live/respond`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ kind: "observe", conv_id: S.conv, image: frame, camera: S.facing, level: prefs.level, recent: S.recent }),
        signal: S.obsAbort.signal,
      });
      if (!S) return;
      if (handleAuthFail(r.status)) return;
      if (!r.ok) { noteFailure(r.status); return; }
      const d = await r.json();
      S.fails = 0;
      S.obsThumb = S.prevThumb || S.obsThumb;
      S.observeCount++;
      if (ep !== S.epoch || S.phase !== "listening") return;   // contexte changé : réponse périmée
      if (d.speak && d.text) {
        S.exchanges.push({ assistant: d.text, proactive: true });
        S.spontaneous++;
        sayAloud(d.text, false);
      }
    } catch (e) {
      if (!(e && e.name === "AbortError") && S) noteFailure(0);
    } finally {
      if (S) { S.observing = false; ui.root.classList.remove("observing"); }
    }
  }

  function noteFailure(status) {
    S.fails++;
    if (status === 429) S.backoffUntil = nowMs() + 30000;
    else if (S.fails >= 3) {
      S.backoffUntil = nowMs() + 60000;
      if (!S.warned) { S.warned = true; toast("Connexion instable : les commentaires spontanés sont suspendus un instant"); }
    }
  }

  // ─────────────────────────── Ordonnanceur d'observation ───────────────────────────
  function tick() {
    if (!S || S.closing) return;
    const cur = sampleThumb();
    if (cur) {
      S.prevThumb = cur;
      S.change = S.obsThumb ? diffThumb(cur, S.obsThumb) : 999;
    }
    if (!CFG.vision || !S.visionOn || document.hidden || S.observing || S.flipping) return;
    if (S.phase !== "listening") return;
    const t = nowMs();
    const cfg = INTERVALS[prefs.level];
    if (t < S.backoffUntil) return;
    if (t - S.lastObsAt < cfg.min) return;
    if (t - Math.max(S.lastAIAt, S.lastUserAt) < 2500) return;
    const changed = S.change >= cfg.change;
    const stale = t - S.lastObsAt >= cfg.max;
    if (changed || stale) observe(false);
  }

  function askLook() {
    if (!S || S.closing) return;
    if (S.phase === "speaking") { S.ttsTok++; stopTTS(); }
    S.pending = S.pending ? S.pending + " Regarde ce que je te montre." : "Regarde ce que je te montre.";
    showCaption("user", S.pending);
    haptic(10);
    runTurn();
  }

  function toggleMic() {
    if (!S) return;
    if (!S.proc && !S.micOn) {          // micro refusé au départ : nouvelle tentative
      startMic().then(refreshChips).catch(() => toast("Micro indisponible"));
      return;
    }
    S.micOn = !S.micOn;
    if (!S.micOn) { S.inUtter = false; S.utter = []; S.pre = []; S.loudMs = 0; }
    refreshChips();
    haptic(8);
  }

  function toggleVision() {
    if (!S) return;
    S.visionOn = !S.visionOn;
    ui.root.classList.toggle("vision-off", !S.visionOn);
    refreshChips();
    haptic(8);
  }

  // ─────────────────────────── Cycle de vie ───────────────────────────
  function consentOk() {
    if (localStorage.getItem("L5_lv_consent") === "1") return Promise.resolve(true);
    return new Promise((resolve) => {
      const m = document.createElement("div");
      m.className = "lv-consent";
      m.innerHTML = `<div class="lv-consent-box" role="dialog" aria-modal="true" aria-labelledby="lvCT">
        <div class="lv-consent-t" id="lvCT">Lumina Live</div>
        <p>Pour te répondre en direct, Lumina envoie à son serveur et à son fournisseur d'IA (Groq) des <b>images réduites de ta caméra</b> et des <b>extraits de ta voix</b>. Les images et l'audio ne sont pas enregistrés par le serveur Lumina ; seul le texte des échanges est conservé dans ta conversation.</p>
        <p>Ne filme pas de personnes sans leur accord. Un casque évite que Lumina s'entende elle-même.</p>
        <div class="lv-consent-btns"><button type="button" class="lv-btn-sec" id="lvNo">Annuler</button><button type="button" class="lv-btn-main" id="lvYes">Continuer</button></div>
      </div>`;
      document.body.appendChild(m);
      $("#lvNo", m).onclick = () => { m.remove(); resolve(false); };
      $("#lvYes", m).onclick = () => { localStorage.setItem("L5_lv_consent", "1"); m.remove(); resolve(true); };
    });
  }

  async function open() {
    if (S) return;
    if (!ST.token) { toast("Connecte-toi pour utiliser le Live"); return; }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      toast("Caméra non disponible ici (HTTPS requis)");
      return;
    }
    if (!(await consentOk())) return;

    try { closePlus(); } catch (e) { /* ignoré */ }
    try { stopTTS(); } catch (e) { /* ignoré */ }
    try { if (RT.camActive) stopVision(); } catch (e) { /* ignoré */ }

    const Ctx = window.AudioContext || window.webkitAudioContext;
    S = {
      active: true, closing: false, phase: "starting",
      conv: ST.convs.cur, facing: "user", vStream: null, aStream: null,
      ctx: Ctx ? new Ctx() : null,     // créé dans le geste utilisateur (politique autoplay)
      micOn: false, visionOn: true,
      level: 0, shown: 0, noise: 0.008, rate: 48000,
      pre: [], utter: [], inUtter: false, utterMs: 0, voicedMs: 0, silenceMs: 0, loudMs: 0,
      pending: "", epoch: 0, turnEpoch: 0, ttsTok: 0, turnAbort: null, obsAbort: null,
      observing: false, observeCount: 0, spontaneous: 0, turns: 0, interrupted: 0,
      lastObsAt: 0, lastAIAt: 0, lastUserAt: 0, backoffUntil: 0, fails: 0, warned: false,
      obsThumb: null, prevThumb: null, change: 0, recent: [], exchanges: [], flipping: false,
      wake: null, timer: 0,
    };
    if (S.ctx && S.ctx.resume) S.ctx.resume().catch(() => {});

    buildUI();
    ui.root.classList.remove("closing", "vision-off", "observing", "flipping");
    ui.err.hidden = true;
    ui.capUser.textContent = ""; ui.capAi.textContent = "";
    ui.hint.classList.remove("gone");
    refreshChips();
    requestAnimationFrame(() => ui.root.classList.add("open"));
    setPhase("starting");
    try { history.pushState({ lv: 1 }, ""); } catch (e) { /* ignoré */ }

    try {
      await startVideo("user");
    } catch (e) {
      showError(e && e.name === "NotAllowedError"
        ? "Accès à la caméra refusé. Autorise la caméra dans les réglages de l'application."
        : "Caméra indisponible.", () => { teardown(); open(); });
      return;
    }
    try {
      await startMic();
    } catch (e) {
      S.micOn = false;
      toast("Micro indisponible : le Live fonctionnera sans la voix");
    }
    try { if (navigator.wakeLock) S.wake = await navigator.wakeLock.request("screen"); } catch (e) { /* ignoré */ }

    S.lastObsAt = nowMs() - INTERVALS[prefs.level].min + 3500;   // premier regard ~3,5 s après le départ
    S.timer = setInterval(tick, 700);
    refreshChips();
    setPhase("listening");
    cancelAnimationFrame(rafId);
    rafId = requestAnimationFrame(animLoop);
  }

  function commitToChat(sess) {
    if (!sess || !sess.exchanges.length) return;
    const conv = sess.conv;
    if (!ST.hist[conv]) ST.hist[conv] = [];
    sess.exchanges.forEach((ex) => {
      if (ex.user) ST.hist[conv].push({ role: "user", content: ex.user, type: "text" });
      if (ex.assistant) ST.hist[conv].push({ role: "assistant", content: ex.assistant, type: "text" });
    });
    const c = ST.convs.list.find((x) => x.id === conv);
    if (c && c.title === "Nouvelle discussion") c.title = "Session Live";
    save();
    try { renderConvList(); if (ST.convs.cur === conv) renderMsgs(); } catch (e) { /* ignoré */ }
  }

  function teardown() {
    const sess = S;
    if (!sess) return null;
    sess.closing = true;
    clearInterval(sess.timer);
    cancelAnimationFrame(rafId);
    if (sess.turnAbort) { try { sess.turnAbort.abort(); } catch (e) { /* ignoré */ } }
    if (sess.obsAbort) { try { sess.obsAbort.abort(); } catch (e) { /* ignoré */ } }
    sess.ttsTok++;
    try { stopTTS(); } catch (e) { /* ignoré */ }
    stopMic();
    stopVideo();
    if (sess.wake) { try { sess.wake.release(); } catch (e) { /* ignoré */ } }
    S = null;
    return sess;
  }

  function close(fromPop) {
    if (!S) return;
    const sess = teardown();
    if (ui) {
      ui.root.classList.remove("open");
      ui.root.classList.add("closing");
      setTimeout(() => { if (ui && !S) ui.root.classList.remove("closing"); }, 320);
    }
    if (!fromPop) { try { if (history.state && history.state.lv) history.back(); } catch (e) { /* ignoré */ } }
    commitToChat(sess);
    if (sess && sess.turns + sess.spontaneous > 0) toast("Session Live enregistrée dans la conversation");
  }

  window.addEventListener("popstate", () => { if (S) close(true); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && S) close(); });
  document.addEventListener("visibilitychange", () => {
    if (!S) return;
    if (document.hidden) { S.ttsTok++; try { stopTTS(); } catch (e) { /* ignoré */ } if (S.phase === "speaking") setPhase("listening"); }
    else if (S.wake === null && navigator.wakeLock) navigator.wakeLock.request("screen").then((w) => { if (S) S.wake = w; else w.release(); }).catch(() => {});
  });

  // ─────────────────────────── Branchements ───────────────────────────
  function wire() {
    const live = document.getElementById("liveBtn");
    if (live) live.onclick = () => open();
    const pmV = document.getElementById("pmVision");
    if (pmV) pmV.onclick = () => { try { closePlus(); } catch (e) { /* ignoré */ } open(); };
    const pmG = document.getElementById("pmGestures");
    if (pmG) pmG.onclick = () => { try { closePlus(); } catch (e) { /* ignoré */ } if (RT.camActive) stopVision(); else startVision(); };
  }
  wire();

  // Exposé pour les tests automatisés et le débogage.
  window.LuminaLive = {
    open, close, flipCamera,
    getState() {
      return S ? {
        open: true, phase: S.phase, facing: S.facing, micOn: S.micOn, visionOn: S.visionOn,
        observeCount: S.observeCount, spontaneous: S.spontaneous, turns: S.turns,
        interrupted: S.interrupted, exchanges: S.exchanges.length, level: prefs.level,
      } : { open: false };
    },
    _prefs: prefs,
  };
})();
