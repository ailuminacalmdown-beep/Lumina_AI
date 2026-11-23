"""Tests backend Lumina v7 — `python -m unittest discover -s tests -v`.
SQLite temporaire, Groq/Whisper simulés. Ne touche ni Neon ni aucun service externe."""
import io, json, os, sqlite3, time, unittest
from unittest import mock

import support
from support import server

JPEG = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQ"   # préfixe valide, contenu factice


def hdr(token): return {"Authorization": "Bearer " + token}


class Base(unittest.TestCase):
    n = 0

    @classmethod
    def setUpClass(cls):
        cls.fake, cls.stt, _ = support.install_fakes()
        cls.c = server.app.test_client()

    def setUp(self):
        support.reset_limits()
        self.fake.calls.clear(); self.fake.fail = False
        self.stt.update(text="bonjour lumina", status=200, calls=0)

    def user(self, ip=None):
        Base.n += 1
        email = f"user{Base.n}_{int(time.time()*1000)}@test.local"
        h = {"X-Forwarded-For": ip or f"10.0.{Base.n % 250}.{Base.n % 250 + 1}"}
        r = self.c.post("/auth/signup", json={"email": email, "password": "motdepasse1"}, headers=h)
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        return email, r.json["token"], r.json["user"]["id"]

    def chat(self, token, msg="salut", **extra):
        body = {"message": msg, "conv_id": "c1", "model": "openai/gpt-oss-20b"}; body.update(extra)
        return self.c.post("/chat", json=body, headers=hdr(token))

    def db(self):
        return sqlite3.connect(os.environ["SQLITE_PATH"])


class TestDatabaseLayer(Base):
    def test_get_db_returns_connection(self):          # régression C1 : get_db() renvoyait None
        with server.app.test_request_context():
            db = server.get_db()
            self.assertIsNotNone(db)
            self.assertEqual(db.execute("SELECT 1 AS x").fetchone()["x"], 1)

    def test_postgres_placeholder_translation(self):
        seen = []
        class C:
            def execute(self, q, p=()): seen.append(q); return None
        server.DBConnection(C(), postgres=True).execute("SELECT * FROM t WHERE a = ? AND b LIKE '50%'", (1,))
        self.assertEqual(seen[0], "SELECT * FROM t WHERE a = %s AND b LIKE '50%%'")
        seen.clear()
        server.DBConnection(C(), postgres=False).execute("SELECT ? AS a", (1,))
        self.assertEqual(seen[0], "SELECT ? AS a")

    def test_unreachable_postgres_does_not_crash_and_does_not_leak_url(self):
        url = "postgresql://user:secretpw@127.0.0.1:1/neondb"
        out = io.StringIO()
        with mock.patch.object(server, "DATABASE_URL", url), mock.patch.object(server, "_schema_ready", False), \
                mock.patch("sys.stdout", out):
            ok = server.ensure_schema()
        self.assertFalse(ok)
        self.assertNotIn("secretpw", out.getvalue())
        with mock.patch.object(server, "DATABASE_URL", url), mock.patch.object(server, "_schema_ready", False):
            r = self.c.get("/healthz")
            self.assertEqual(r.status_code, 503)
            r = self.c.post("/auth/login", json={"email": "a@b.co", "password": "x" * 9})
            self.assertEqual(r.status_code, 503)
            self.assertIn("error", r.json)

    def test_migration_is_additive_and_idempotent(self):
        server._add_v7_tables(); server._add_v7_tables()
        tables = {r[0] for r in self.db().execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in ("users", "sessions", "user_knowledge", "conv_memories", "feedback"):
            self.assertIn(t, tables)


class TestAuth(Base):
    def test_signup_login_me_logout(self):
        email, tok, uid = self.user()
        self.assertEqual(self.c.get("/auth/me", headers=hdr(tok)).json["user"]["email"], email)
        r = self.c.post("/auth/login", json={"email": email, "password": "motdepasse1"})
        self.assertEqual(r.status_code, 200)
        tok2 = r.json["token"]
        self.assertEqual(self.c.post("/auth/logout", headers=hdr(tok2)).status_code, 200)
        self.assertEqual(self.c.get("/auth/me", headers=hdr(tok2)).status_code, 401)
        self.assertEqual(self.c.get("/auth/me", headers=hdr(tok)).status_code, 200)

    def test_rejections(self):
        email, _, _ = self.user()
        self.assertEqual(self.c.post("/auth/signup", json={"email": email, "password": "motdepasse1"}).status_code, 409)
        self.assertEqual(self.c.post("/auth/signup", json={"email": "pas-un-email", "password": "motdepasse1"}).status_code, 400)
        self.assertEqual(self.c.post("/auth/signup", json={"email": "x@y.zz", "password": "court"}).status_code, 400)
        self.assertEqual(self.c.post("/auth/signup", json={"email": "x@y.zz", "password": "a" * 300}).status_code, 400)
        self.assertEqual(self.c.post("/auth/login", json={"email": email, "password": "faux-mot-de-passe"}).status_code, 401)
        self.assertEqual(self.c.get("/auth/me").status_code, 401)
        self.assertEqual(self.c.get("/auth/me", headers=hdr("inconnu")).status_code, 401)

    def test_session_expires(self):
        _, tok, _ = self.user()
        self.assertEqual(self.c.get("/auth/me", headers=hdr(tok)).status_code, 200)
        db = self.db(); db.execute("UPDATE sessions SET created_at=?", (time.time() - server.SESSION_TTL - 60,)); db.commit()
        self.assertEqual(self.c.get("/auth/me", headers=hdr(tok)).status_code, 401)
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM sessions WHERE token=?", (tok,)).fetchone()[0], 0)

    def test_signup_rate_limit_per_ip(self):
        codes = [self.c.post("/auth/signup", json={"email": f"rl{i}_{time.time()}@t.io", "password": "motdepasse1"},
                             headers={"X-Forwarded-For": "203.0.113.9"}).status_code for i in range(server.SIGNUP_MAX_PER_HOUR + 2)]
        self.assertEqual(codes[:server.SIGNUP_MAX_PER_HOUR], [200] * server.SIGNUP_MAX_PER_HOUR)
        self.assertEqual(codes[-1], 429)

    def test_login_lockout_cannot_be_used_against_a_victim(self):
        email, _, _ = self.user()
        for _ in range(server.LOGIN_MAX_ATTEMPTS):
            self.c.post("/auth/login", json={"email": email, "password": "mauvais-mdp"}, headers={"X-Forwarded-For": "198.51.100.7"})
        self.assertEqual(self.c.post("/auth/login", json={"email": email, "password": "mauvais-mdp"},
                                     headers={"X-Forwarded-For": "198.51.100.7"}).status_code, 429)
        # le vrai propriétaire, depuis une autre IP, n'est PAS bloqué (v6.1 : il l'était)
        self.assertEqual(self.c.post("/auth/login", json={"email": email, "password": "motdepasse1"},
                                     headers={"X-Forwarded-For": "192.0.2.50"}).status_code, 200)


class TestStaticSecurity(Base):
    def test_internal_files_are_not_served(self):
        for p in ["lumina.db", "lumina_server.py", "migrate_sqlite_to_neon.py", "Dockerfile", "requirements.txt", ".gitignore",
                  ".env", "package.json", "capacitor.config.json", "android/gradle.properties", "tests/test_backend.py",
                  "www/index.html", "static/lumina_server.py", "%2e%2e/lumina_server.py", "../lumina_server.py",
                  "..%2flumina_server.py", "icons/../../lumina_server.py", "DEPLOY.md"]:
            r = self.c.get("/" + p)
            self.assertEqual(r.status_code, 404, f"/{p} -> {r.status_code}")

    def test_hidden_and_non_whitelisted_files_inside_www_are_blocked(self):
        www = server.WEB_DIR
        files = {os.path.join(www, "secret.py"): "x=1", os.path.join(www, ".hidden.html"): "<p>x</p>", os.path.join(www, "leak.sqlite"): "x"}
        for f, c in files.items(): open(f, "w").write(c)
        try:
            for name in ("secret.py", ".hidden.html", "leak.sqlite"):
                self.assertEqual(self.c.get("/" + name).status_code, 404, name)
        finally:
            for f in files: os.remove(f)

    def test_app_files_are_served_with_security_headers(self):
        for p in ["/", "/index.html", "/sw.js", "/manifest.json", "/v7.css", "/ui7.js", "/live.js", "/icons/icon-192.png", "/icons/icon-512.png"]:
            r = self.c.get(p)
            self.assertEqual(r.status_code, 200, p)
            self.assertEqual(r.headers.get("X-Content-Type-Options"), "nosniff")
            self.assertEqual(r.headers.get("X-Frame-Options"), "DENY")
            self.assertIn("camera=(self)", r.headers.get("Permissions-Policy", ""))
        self.assertEqual(self.c.get("/sw.js").headers.get("Cache-Control"), "no-cache")

    def test_public_status_is_minimal_and_admin_endpoints_are_protected(self):
        r = self.c.get("/status").json
        self.assertEqual(set(r), {"status", "version"})
        self.assertNotIn("users", r); self.assertNotIn("keys", r)
        self.assertIn("users", self.c.get("/status", headers={"X-Admin-Token": "admin-test-token"}).json)
        self.assertEqual(self.c.get("/groq_models").status_code, 404)
        self.assertEqual(self.c.get("/groq_models", headers={"X-Admin-Token": "mauvais"}).status_code, 404)
        self.assertEqual(self.c.post("/search_web", json={"query": "x"}).status_code, 401)
        self.assertEqual(self.c.get("/healthz").json, {"ok": True})


class TestChat(Base):
    def test_basic_chat_persists_history(self):
        _, tok, uid = self.user()
        r = self.chat(tok, "bonjour")
        self.assertEqual(r.status_code, 200); self.assertTrue(r.json["ok"])
        row = self.db().execute("SELECT historique FROM conv_memories WHERE user_id=?", (uid,)).fetchone()
        self.assertEqual(json.loads(row[0])[0]["user"], "bonjour")

    def test_limits(self):
        _, tok, _ = self.user()
        self.assertEqual(self.chat(tok, "x" * (server.MAX_MESSAGE_CHARS + 1)).status_code, 413)
        self.assertEqual(self.chat(tok, "ok", conv_id="../../etc").status_code, 400)
        self.assertEqual(self.chat(tok, "ok", image="http://evil/x.png").status_code, 400)
        self.assertEqual(self.chat(tok, "ok", image="data:text/html;base64,AAAA").status_code, 400)
        self.assertEqual(self.chat(tok, "ok", image=JPEG + "A" * (server.MAX_IMAGE_B64 + 1)).status_code, 413)
        big = self.c.post("/chat", data=b"x" * (server.MAX_REQUEST_BYTES + 10), headers={**hdr(tok), "Content-Type": "application/json"})
        self.assertEqual(big.status_code, 413)
        self.assertEqual(self.fake.calls, [])                    # rien n'est parti vers le fournisseur

    def test_chat_rate_limit(self):
        _, tok, _ = self.user()
        codes = [self.chat(tok, f"m{i}").status_code for i in range(server.CHAT_MAX_PER_MIN + 2)]
        self.assertEqual(codes[-1], 429)

    def test_cache_does_not_mix_two_different_images(self):     # régression E1
        _, tok, _ = self.user()
        same = "Analyse cette image en détail."
        a = self.chat(tok, same, image=JPEG + "AAAA").json
        b = self.chat(tok, same, image=JPEG + "BBBB").json
        self.assertNotEqual(a["reply"], b["reply"])
        self.assertEqual(len(self.fake.calls), 2)
        self.assertNotEqual(b["model"], "cache")
        self.assertTrue(any(isinstance(m["content"], list) for m in self.fake.calls[0]["messages"]))

    def test_cache_for_plain_text_and_regenerate_bypasses_it(self):
        _, tok, uid = self.user()
        r1 = self.chat(tok, "Raconte une blague").json
        r2 = self.chat(tok, "Raconte une blague").json
        self.assertEqual(r2["model"], "cache"); self.assertEqual(r1["reply"], r2["reply"])
        r3 = self.chat(tok, "Raconte une blague", regen=True).json
        self.assertNotEqual(r3["model"], "cache"); self.assertNotEqual(r3["reply"], r1["reply"])
        hist = json.loads(self.db().execute("SELECT historique FROM conv_memories WHERE user_id=?", (uid,)).fetchone()[0])
        # le cache ne duplique pas l'historique ; une régénération REMPLACE l'échange précédent
        self.assertEqual([h["user"] for h in hist], ["Raconte une blague"])
        self.assertEqual(hist[0]["assistant"], r3["reply"])
        self.chat(tok, "Raconte une blague", regen=True)
        hist = json.loads(self.db().execute("SELECT historique FROM conv_memories WHERE user_id=?", (uid,)).fetchone()[0])
        self.assertEqual(len(hist), 1)

    def test_provider_outage_returns_503_and_saves_nothing(self):   # régression E5
        _, tok, uid = self.user()
        self.fake.fail = True
        r = self.chat(tok, "panne")
        self.assertEqual(r.status_code, 503); self.assertFalse(r.json["ok"]); self.assertIn("reply", r.json)
        self.assertIsNone(self.db().execute("SELECT 1 FROM conv_memories WHERE user_id=?", (uid,)).fetchone())

    def test_cascade_respects_global_deadline(self):                  # régression M1
        calls = []
        real_sleep = time.sleep
        def slow_post(url, **k):
            calls.append(k.get("timeout")); real_sleep(0.35); raise server.requests.exceptions.Timeout()
        with mock.patch.object(server.requests, "post", slow_post), \
                mock.patch.object(server, "GROQ_TOTAL_TIMEOUT", 2), \
                mock.patch.object(server.time, "sleep", lambda s: real_sleep(0.01)):
            t0 = time.time()
            out = server.real_call_groq([{"role": "user", "content": "x"}], max_tokens=10)
            dt = time.time() - t0
        self.assertFalse(out["ok"])
        self.assertLess(dt, 4.5, f"cascade trop longue : {dt:.1f}s (sans délai global : ~7 s)")
        self.assertTrue(all(t is None or t <= 30 for t in calls))


class TestIsolationAndAccount(Base):
    def test_users_cannot_see_or_delete_each_others_data(self):
        _, a, _ = self.user(); _, b, _ = self.user()
        self.chat(a, "secret de A", conv_id="shared")
        self.chat(b, "message de B", conv_id="shared")
        self.assertEqual(self.c.delete("/conv_memory/shared", headers=hdr(b)).status_code, 200)
        db = self.db()
        self.assertEqual(db.execute("SELECT COUNT(*) FROM conv_memories").fetchone()[0] >= 1, True)
        rows = db.execute("SELECT user_id, historique FROM conv_memories").fetchall()
        self.assertTrue(any("secret de A" in r[1] for r in rows))
        self.assertFalse(any("message de B" in r[1] for r in rows))
        self.chat(a, "apprend que ciel est bleu", conv_id="k")
        self.assertEqual(self.c.get("/get_memory", headers=hdr(b)).json["connaissances"], {})
        self.assertIn("ciel", self.c.get("/get_memory", headers=hdr(a)).json["connaissances"])

    def test_delete_account(self):
        email, tok, uid = self.user(); _, other, ouid = self.user()
        self.chat(tok, "à effacer"); self.chat(other, "à garder")
        self.c.post("/feedback", json={"type": "dislike", "conv_id": "c1"}, headers=hdr(tok))
        self.assertEqual(self.c.delete("/auth/account", json={"password": "mauvais"}, headers=hdr(tok)).status_code, 401)
        self.assertEqual(self.c.delete("/auth/account", json={"password": "motdepasse1"}).status_code, 401)
        self.assertEqual(self.c.delete("/auth/account", json={"password": "motdepasse1"}, headers=hdr(tok)).status_code, 200)
        db = self.db()
        for t in ("users", "sessions", "conv_memories", "user_knowledge", "feedback"):
            col = "id" if t == "users" else "user_id"
            self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {t} WHERE {col}=?", (uid,)).fetchone()[0], 0, t)
        self.assertEqual(self.c.post("/auth/login", json={"email": email, "password": "motdepasse1"}).status_code, 401)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM conv_memories WHERE user_id=?", (ouid,)).fetchone()[0], 1)
        self.assertEqual(self.c.get("/auth/me", headers=hdr(other)).status_code, 200)

    def test_feedback(self):
        _, tok, uid = self.user()
        self.assertEqual(self.c.post("/feedback", json={"type": "like", "message_id": "m1"}, headers=hdr(tok)).status_code, 200)
        self.assertEqual(self.c.post("/feedback", json={"type": "pirate"}, headers=hdr(tok)).status_code, 400)
        self.assertEqual(self.c.post("/feedback", json={"type": "bug_report", "text": "  "}, headers=hdr(tok)).status_code, 400)
        self.assertEqual(self.c.post("/feedback", json={"type": "bug_report", "text": "ça plante"}, headers=hdr(tok)).status_code, 200)
        self.assertEqual(self.c.post("/feedback", json={"type": "like"}).status_code, 401)
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM feedback WHERE user_id=?", (uid,)).fetchone()[0], 2)


class TestLive(Base):
    def live(self, tok, **b):
        body = {"kind": "observe", "conv_id": "lv1", "image": JPEG + "AAAA", "level": "normal", "camera": "user", "recent": []}
        body.update(b)
        return self.c.post("/live/respond", json=body, headers=hdr(tok))

    def test_observe_speaks_when_useful_and_stays_silent_otherwise(self):
        _, tok, uid = self.user()
        r = self.live(tok); self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json["speak"]); self.assertEqual(r.json["text"], "Tu as bien rangé ton bureau.")
        self.fake.observe_text = "[SILENCE]"
        self.assertFalse(self.live(tok).json["speak"])
        self.fake.observe_text = "**Super** travail, continue !"
        self.assertEqual(self.live(tok).json["text"], "Super travail, continue !")      # markdown retiré pour la voix
        call = self.fake.calls[0]
        self.assertEqual(call["reason"], "live"); self.assertLessEqual(call["max_tokens"], 300)
        self.assertIn(call["model"], server.VISION_MODEL_LIST)                           # vision -> modèle vision
        self.assertTrue(any(p.get("type") == "image_url" for p in call["messages"][-1]["content"]))
        # les observations ne sont pas stockées, et aucune image n'est jamais écrite en base
        self.assertIsNone(self.db().execute("SELECT 1 FROM conv_memories WHERE user_id=?", (uid,)).fetchone())

    def test_observe_prompt_includes_recent_comments_and_level(self):
        _, tok, _ = self.user()
        self.live(tok, recent=["Tu cuisines des pâtes."], level="discret", camera="environment")
        msgs = self.fake.calls[0]["messages"]
        self.assertIn("économe", msgs[0]["content"])
        self.assertIn("Tu cuisines des pâtes.", msgs[1]["content"][0]["text"])
        self.assertIn("arrière", msgs[1]["content"][0]["text"])

    def test_turn_saves_text_only(self):
        _, tok, uid = self.user()
        r = self.live(tok, kind="turn", text="Qu'est-ce que je tiens ?")
        self.assertEqual(r.status_code, 200); self.assertTrue(r.json["reply"].startswith("RÉPONSE"))
        raw = self.db().execute("SELECT historique FROM conv_memories WHERE user_id=?", (uid,)).fetchone()[0]
        self.assertIn("[Live] Qu'est-ce que je tiens ?", raw); self.assertNotIn("base64", raw); self.assertNotIn("data:image", raw)
        r = self.live(tok, kind="turn", text="et maintenant ?", image=None)       # sans image : modèle rapide
        self.assertEqual(r.status_code, 200)
        self.assertFalse(any(isinstance(m["content"], list) for m in self.fake.calls[-1]["messages"]))
        self.assertTrue(len([m for m in self.fake.calls[-1]["messages"] if m["role"] == "assistant"]) >= 1)  # contexte repris

    def test_live_validation_and_errors(self):
        _, tok, _ = self.user()
        self.assertEqual(self.live(tok, kind="autre").status_code, 400)
        self.assertEqual(self.live(tok, image=None).status_code, 400)
        self.assertEqual(self.live(tok, image="javascript:alert(1)").status_code, 400)
        self.assertEqual(self.live(tok, image=JPEG + "A" * (server.MAX_LIVE_IMAGE_B64 + 1)).status_code, 413)
        self.assertEqual(self.live(tok, kind="turn", text="").status_code, 400)
        self.assertEqual(self.live(tok, kind="turn", text="x" * 1600).status_code, 413)
        self.assertEqual(self.live(tok, conv_id="a b").status_code, 400)
        self.assertEqual(self.c.post("/live/respond", json={"kind": "observe"}).status_code, 401)
        self.fake.fail = True
        r = self.live(tok); self.assertEqual(r.status_code, 503); self.assertFalse(r.json["speak"])

    def test_live_rate_limit(self):
        _, tok, _ = self.user()
        codes = [self.live(tok).status_code for _ in range(server.LIVE_MAX_PER_MIN + 3)]
        self.assertEqual(codes[-1], 429)

    def stt_post(self, tok, data=None, mime="audio/wav", name="u.wav", **form):
        d = dict(form)
        if data is not None: d["audio"] = (io.BytesIO(data), name, mime)
        return self.c.post("/live/stt", data=d, headers=hdr(tok), content_type="multipart/form-data")

    def test_stt(self):
        _, tok, _ = self.user()
        wav = b"RIFF" + b"\0" * 4000
        r = self.stt_post(tok, wav); self.assertEqual(r.json, {"ok": True, "text": "bonjour lumina"})
        self.assertEqual(self.stt_post(tok, None).status_code, 400)
        self.assertEqual(self.stt_post(tok, b"x" * 100).json["text"], "")                 # trop court : pas d'appel
        self.assertEqual(self.stt.get("calls"), 1)
        self.assertEqual(self.stt_post(tok, wav, mime="application/zip", name="a.zip").status_code, 415)
        self.assertEqual(self.stt_post(tok, b"x" * (server.MAX_AUDIO_BYTES + 5)).status_code, 413)
        self.stt["text"] = "Sous-titrage ST' 501"                                           # hallucination Whisper sur silence
        self.assertEqual(self.stt_post(tok, wav).json["text"], "")
        self.stt["status"] = 500
        self.assertEqual(self.stt_post(tok, wav).status_code, 503)
        self.assertEqual(self.c.post("/live/stt", data={"audio": (io.BytesIO(wav), "u.wav", "audio/wav")}, content_type="multipart/form-data").status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)
