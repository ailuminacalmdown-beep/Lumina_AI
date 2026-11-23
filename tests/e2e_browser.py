"""Tests de bout en bout dans un vrai Chromium (Playwright). Facultatif : nécessite `pip install playwright`
et un Chromium (`playwright install chromium`). Serveur Lumina réel + fournisseurs IA simulés.
Caméra et micro : périphériques factices de Chromium ; le micro rejoue une boucle audio synthétique
(1,5 s de « voix » puis 2,5 s de silence) pour rendre la détection de parole déterministe.

    python tests/e2e_browser.py          (ou : python -m unittest tests.e2e_browser)
"""
import math, os, random, struct, sys, tempfile, time, unittest, wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import support                                  # noqa: E402
from support import server                     # noqa: E402

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""))
try:
    from playwright.sync_api import sync_playwright
except ImportError:                              # pragma: no cover
    sync_playwright = None

PORT = 5097
URL = f"http://127.0.0.1:{PORT}/"


def make_fake_mic(path, silence_s=2.5):
    rate = 48000; frames = []
    for i in range(int(rate * 1.5)):             # « voix » : harmoniques modulées
        t = i / rate
        v = 0.35 * (0.6 * math.sin(2 * math.pi * 180 * t) + 0.3 * math.sin(2 * math.pi * 420 * t) + 0.1 * math.sin(2 * math.pi * 900 * t))
        v *= 0.7 + 0.3 * math.sin(2 * math.pi * 4 * t)
        frames.append(int(max(-1, min(1, v)) * 32767))
    for _ in range(int(rate * silence_s)):
        frames.append(random.randint(-20, 20))
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(struct.pack("<%dh" % len(frames), *frames))


def make_jpeg(path, seed, size=(3200, 2400)):
    from PIL import Image
    rnd = random.Random(seed)
    im = Image.effect_noise(size, 80).convert("RGB")
    px = Image.new("RGB", (64, 64), (rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255))).resize(size)
    Image.blend(im, px, 0.5).save(path, "JPEG", quality=95)


@unittest.skipIf(sync_playwright is None, "playwright non installé")
class E2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake, cls.stt, _ = support.install_fakes()
        cls.srv = support.start_http(PORT)
        cls.tmp = tempfile.mkdtemp(prefix="lumina_e2e_")
        cls.pw = sync_playwright().start()
        cls.browser = cls.launch(2.5)           # parole toutes les 4 s (utilisateur bavard : test d'interruption)
        cls.quiet = None                        # navigateur « calme » créé à la demande (test des commentaires spontanés)
        cls.n = 0

    @classmethod
    def launch(cls, silence_s):
        mic = os.path.join(cls.tmp, f"mic_{silence_s}.wav"); make_fake_mic(mic, silence_s)
        return cls.pw.chromium.launch(args=[
            "--no-sandbox", "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
            f"--use-file-for-fake-audio-capture={mic}", "--autoplay-policy=no-user-gesture-required"])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        if cls.quiet: cls.quiet.close()
        cls.pw.stop(); cls.srv.shutdown()

    def setUp(self):
        support.reset_limits()
        self.fake.calls.clear(); self.fake.fail = False; self.fake.counter = 0
        self.fake.observe_text = "Tu tiens un stylo, tu écris quelque chose ?"
        self.stt.update(text="bonjour lumina", status=200, calls=0)
        self.use_browser = self.browser
        self.ctx = self.browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                            has_touch=True, is_mobile=True, permissions=["camera", "microphone"])
        self.page = self.ctx.new_page()
        self.errors = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.requests = []
        self.page.on("request", lambda r: self.requests.append(r) if r.method == "POST" else None)

    def tearDown(self):
        self.ctx.close()

    # ── outils
    def signup(self, email=None, wait_greeting=True):
        E2E.n += 1
        email = email or f"e2e{E2E.n}_{int(time.time()*1000)}@test.local"
        p = self.page
        p.goto(URL); p.wait_for_selector("#tabSignup", state="visible")
        p.click("#tabSignup"); p.fill("#authEmail", email); p.fill("#authPw", "motdepasse123"); p.click("#authSubmit")
        p.wait_for_selector("#authScr", state="hidden"); p.wait_for_selector("#plusBtn", state="visible")
        p.wait_for_function("document.querySelectorAll('.msg-a').length>=1", timeout=15000)
        # la salutation s'écrit en « streaming » : l'appli ignore les envois pendant ce temps
        if wait_greeting:
            p.wait_for_function("RT.streamingConvs.size===0", timeout=30000)
        return email

    def send(self, text):
        n = self.page.evaluate("document.querySelectorAll('.msg-a').length")
        self.page.fill("#userInp", text); self.page.click("#sendBtn")
        self.page.wait_for_function(f"document.querySelectorAll('.msg-a').length>{n}", timeout=15000)
        self.page.wait_for_function("!document.getElementById('sendBtn').classList.contains('stop-mode')", timeout=20000)

    def chat_bodies(self):
        import json
        return [json.loads(r.post_data) for r in self.requests if r.url.endswith("/chat")]

    def js_errors(self):
        return [e for e in self.errors if "ERR_NAME_NOT_RESOLVED" not in e]

    # ── 1. démarrage, mise en page mobile
    def test_boot_layout_and_no_script_error(self):
        self.signup()
        p = self.page
        self.assertEqual(self.js_errors(), [])
        self.assertTrue(p.is_visible("#plusBtn")); self.assertTrue(p.is_visible("#userInp")); self.assertTrue(p.is_visible("#liveBtn"))
        p.evaluate("document.documentElement.style.setProperty('--safe-area-inset-top','28px')")
        self.assertEqual(p.evaluate("getComputedStyle(document.querySelector('.header')).paddingTop"), "28px")
        for w in (360, 390):
            p.set_viewport_size({"width": w, "height": 740})
            self.assertLessEqual(p.evaluate("document.scrollingElement.scrollWidth"), w, f"débordement horizontal à {w}px")
        self.assertTrue(p.evaluate("getComputedStyle(document.querySelector('#convName')).display") != "none")
        p.screenshot(path=os.path.join(self.tmp, "home.png"))

    def test_login_screen_has_living_logo(self):
        self.page.goto(URL); self.page.wait_for_selector(".lum-logo", state="visible")
        self.assertEqual(self.page.evaluate("document.querySelectorAll('#authScr .lum-logo .lum-reflect, #authScr .lum-logo .lum-aura, #authScr .lum-logo .lum-shine').length"), 3)
        self.assertTrue(self.page.evaluate("document.querySelector('.lum-logo img').complete && document.querySelector('.lum-logo img').naturalWidth>0"))
        self.page.screenshot(path=os.path.join(self.tmp, "auth.png"))

    def test_theme_cycle_and_animation_toggle(self):
        self.signup(); p = self.page
        p.click("#menuBtn"); p.click("#navStg"); p.wait_for_selector("#themeItem", state="visible")
        seen = []
        for _ in range(3):
            p.click("#themeItem"); seen.append(p.evaluate("document.body.className.match(/t-(amoled|light)/)?.[0]||'dark'"))
        self.assertEqual(seen, ["t-amoled", "t-light", "dark"])
        self.assertEqual(p.evaluate("document.querySelector('meta[name=theme-color]').content"), "#0d0d0d")
        p.click("#animItem"); self.assertTrue(p.evaluate("document.body.classList.contains('no-anim')"))
        p.click("#animItem"); self.assertFalse(p.evaluate("document.body.classList.contains('no-anim')"))

    # ── 2. sécurité du rendu
    def test_xss_and_artifact_isolation(self):
        self.signup(); p = self.page
        p.evaluate("""()=>{ST.convs.list[0].title='"><img src=x onerror=window.__x=1>';
          ST.hist[ST.convs.list[0].id]=[{role:'assistant',type:'text',content:'[clic](https://a.fr/x"onmouseover="window.__x=2)'}];
          renderConvList(); renderMsgs();}""")
        p.wait_for_timeout(300)
        self.assertIsNone(p.evaluate("window.__x||null"))
        self.assertEqual(p.evaluate("document.querySelectorAll('.ci-title img, .atext a[onmouseover]').length"), 0)
        sandbox = p.evaluate("""()=>{const c=buildArtCard('html','<script>window.parent.__p=1</script>');document.body.appendChild(c);c.click();
          return document.querySelector('.art-iframe').sandbox.value}""")
        self.assertNotIn("allow-same-origin", sandbox); self.assertIn("allow-scripts", sandbox)

    def test_logout_then_other_account_does_not_see_previous_chats(self):
        self.signup(); self.send("secret de A")
        self.page.evaluate("logout()"); self.page.wait_for_selector("#authScr", state="visible")
        self.page.click("#tabSignup"); self.page.fill("#authEmail", f"b{time.time()}@test.local"); self.page.fill("#authPw", "motdepasse123")
        self.page.click("#authSubmit"); self.page.wait_for_selector("#authScr", state="hidden"); self.page.wait_for_timeout(500)
        self.assertNotIn("secret de A", self.page.evaluate("JSON.stringify(localStorage)"))

    def test_touch_device_sees_conversation_menu_and_message_actions(self):
        self.signup(); self.send("bonjour")
        self.page.click("#menuBtn"); self.page.wait_for_timeout(500)
        self.assertEqual(self.page.evaluate("getComputedStyle(document.querySelector('.ci-more')).display"), "flex")
        self.assertEqual(self.page.evaluate("getComputedStyle(document.querySelector('.macts')).opacity"), "1")

    # ── 3. régénération, images, cache
    def test_regenerate_sends_flag_and_images_are_resized_and_not_mixed(self):
        self.signup(); self.send("raconte une blague")
        self.page.locator('.mact[data-id="retry"]').last.click()
        self.page.wait_for_function("!document.getElementById('sendBtn').classList.contains('stop-mode')", timeout=20000)
        self.page.wait_for_timeout(500)
        bodies = self.chat_bodies()
        self.assertEqual([b["regen"] for b in bodies[:2]], [False, True])
        for i in (1, 2):
            f = os.path.join(self.tmp, f"p{i}.jpg"); make_jpeg(f, i)
            self.assertGreater(os.path.getsize(f), 400_000)
            self.page.set_input_files("#imgInp", f)
            self.page.wait_for_function(f"document.querySelectorAll('.msg-a').length>={2+i}", timeout=20000)
            self.page.wait_for_function("!document.getElementById('sendBtn').classList.contains('stop-mode')", timeout=20000)
        imgs = [b for b in self.chat_bodies() if b.get("image")]
        self.assertEqual(len(imgs), 2)
        for b in imgs:
            self.assertTrue(b["image"].startswith("data:image/jpeg;base64,"))
            self.assertLess(len(b["image"]), 600_000, "image non réduite avant envoi")
        replies = [m for m in self.fake.calls if isinstance(m["messages"][-1]["content"], list)]
        self.assertEqual(len(replies), 2)                         # 2 images différentes => 2 appels (pas de cache croisé)
        self.assertLess(self.page.evaluate("JSON.stringify(localStorage).length"), 900_000, "localStorage saturé par les images")

    def test_message_sent_during_welcome_animation_is_not_lost(self):
        self.signup(wait_greeting=False)
        self.assertTrue(self.page.evaluate("RT.streamingConvs.size>0"))     # la salutation s'écrit encore
        self.page.fill("#userInp", "premier message rapide"); self.page.click("#sendBtn")
        self.page.wait_for_function("ST.hist[ST.convs.cur].some(m=>m.role==='assistant'&&m.content.startsWith('RÉPONSE'))", timeout=20000)
        hist = self.page.evaluate("ST.hist[ST.convs.cur].map(m=>m.role+':'+m.content.slice(0,22))")
        self.assertEqual(self.page.input_value("#userInp"), "")
        self.assertEqual(len([h for h in hist if h.startswith("user:")]), 1)
        self.assertFalse(any(h.startswith("assistant:Bonjour") for h in hist), "salutation tronquée conservée : " + str(hist))

    def test_provider_outage_shows_message_not_blank(self):
        self.signup(); self.fake.fail = True
        self.send("test panne")
        self.page.wait_for_function("[...document.querySelectorAll('.msg-a .atext')].some(e=>/surcharg|indisponible/i.test(e.innerText))", timeout=10000)

    # ── 4. Lumina Live (caméra avant/arrière, voix, commentaires spontanés, interruption)
    def open_live(self):
        p = self.page
        p.click("#liveBtn"); p.wait_for_selector(".lv-consent", state="visible"); p.click("#lvYes")
        p.wait_for_function("window.LuminaLive.getState().open && window.LuminaLive.getState().phase!=='starting'", timeout=15000)

    def test_live_cameras_front_and_rear(self):
        self.signup(); p = self.page; self.open_live()
        st = p.evaluate("LuminaLive.getState()")
        self.assertEqual(st["facing"], "user"); self.assertTrue(st["micOn"])
        p.wait_for_function("(()=>{const v=document.querySelector('.lv-video');return v.videoWidth>0&&!v.paused})()", timeout=10000)
        self.assertTrue(p.evaluate("document.querySelector('.lv-video').classList.contains('mirror')"))   # selfie : image en miroir
        p.screenshot(path=os.path.join(self.tmp, "live_front.png"))
        p.click("#lvFlip"); p.wait_for_function("LuminaLive.getState().facing==='environment'", timeout=10000)
        p.wait_for_function("document.querySelector('.lv-video').videoWidth>0", timeout=10000)
        self.assertFalse(p.evaluate("document.querySelector('.lv-video').classList.contains('mirror')"))   # caméra arrière : pas de miroir
        p.screenshot(path=os.path.join(self.tmp, "live_rear.png"))
        p.click("#lvFlip"); p.wait_for_function("LuminaLive.getState().facing==='user'", timeout=10000)
        p.click("#lvMic"); self.assertFalse(p.evaluate("LuminaLive.getState().micOn"))
        p.click("#lvEye"); self.assertFalse(p.evaluate("LuminaLive.getState().visionOn"))
        p.click("#lvEnd"); p.wait_for_function("!LuminaLive.getState().open")
        self.assertTrue(p.evaluate("document.querySelector('.lv-video').srcObject===null"))
        self.assertEqual(self.js_errors(), [])

    def test_live_ai_speaks_on_its_own_and_answers_when_user_talks(self):
        # micro « calme » : une phrase au début, puis 30 s de silence -> l'IA a le temps de commenter seule
        E2E.quiet = E2E.quiet or E2E.launch(30)
        self.ctx.close(); self.ctx = E2E.quiet.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                                          permissions=["camera", "microphone"])
        self.page = self.ctx.new_page(); self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.signup(); p = self.page; self.open_live()
        p.wait_for_function("LuminaLive.getState().turns>=1", timeout=30000)        # l'utilisateur parle -> réponse
        self.assertGreaterEqual(self.stt["calls"], 1)
        turn = [c for c in self.fake.calls if c["reason"] == "live" and "bonjour lumina" in str(c["messages"][-1]["content"])]
        self.assertTrue(turn)
        p.wait_for_function("LuminaLive.getState().spontaneous>=1", timeout=60000)  # puis l'IA commente seule
        obs = [c for c in self.fake.calls if c["reason"] == "live" and "Que vois-tu de nouveau" in str(c["messages"][-1]["content"])]
        self.assertGreaterEqual(len(obs), 1)
        self.assertTrue(any(x.get("type") == "image_url" and x["image_url"]["url"].startswith("data:image/jpeg") for x in obs[0]["messages"][-1]["content"]))
        self.assertIn("Tu tiens un stylo", p.inner_text("#lvCapAi"))
        p.screenshot(path=os.path.join(self.tmp, "live_speaking.png"))
        p.click("#lvEnd"); p.wait_for_function("!LuminaLive.getState().open")
        self.assertTrue(p.evaluate("ST.hist[ST.convs.cur].some(m=>m.content&&m.content.includes('bonjour lumina'))"))
        self.assertTrue(p.evaluate("ST.hist[ST.convs.cur].some(m=>m.content&&m.content.includes('Tu tiens un stylo'))"))
        self.assertEqual(self.js_errors(), [])

    def test_live_user_can_interrupt_the_ai(self):
        self.signup(); p = self.page
        # la synthèse vocale de Chromium headless n'a pas de voix : on simule une réponse parlée de 30 s
        p.evaluate("window.speakFull=(t,done)=>{RT.ttsBusy=true;setTimeout(()=>{RT.ttsBusy=false;done&&done()},30000)}")
        self.open_live()
        p.wait_for_function("LuminaLive.getState().phase==='speaking'", timeout=40000)
        p.wait_for_function("LuminaLive.getState().interrupted>=1", timeout=60000)   # parole toutes les 4 s : coupe l'IA qui parle
        p.click("#lvBarge")                                                          # désactivation de l'interruption
        self.assertFalse(p.evaluate("LuminaLive._prefs.bargein"))
        p.click("#lvEnd"); p.wait_for_function("!LuminaLive.getState().open")

    def test_live_without_permission_shows_clear_error(self):
        ctx = self.browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)   # pas de permission
        page = ctx.new_page()
        page.add_init_script("navigator.mediaDevices.getUserMedia=()=>Promise.reject(Object.assign(new Error('x'),{name:'NotAllowedError'}))")
        self.page = page
        self.signup(); page.click("#liveBtn"); page.click("#lvYes")
        page.wait_for_selector(".lv-err", state="visible")
        self.assertIn("refusé", page.inner_text("#lvErrMsg"))
        page.click("#lvErrClose"); page.wait_for_function("!LuminaLive.getState().open"); ctx.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
