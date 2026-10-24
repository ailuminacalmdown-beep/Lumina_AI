"""Outils communs aux tests : serveur Lumina sur base SQLite temporaire, fournisseurs IA simulés.
Aucun secret, aucun appel réseau : Groq (chat, vision, Whisper) est remplacé par des doubles."""
import os, sys, tempfile, threading, types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# flask_cors est facultatif pour les tests (stub si absent).
try:
    import flask_cors  # noqa: F401
except ImportError:
    stub = types.ModuleType("flask_cors"); stub.CORS = lambda *a, **k: None
    sys.modules["flask_cors"] = stub

os.environ.pop("DATABASE_URL", None)
_DB = tempfile.mktemp(suffix=".db", prefix="lumina_test_")
os.environ["SQLITE_PATH"] = _DB
os.environ["GROQ_API_KEYS"] = "test-key-1,test-key-2"      # clés factices
os.environ["ADMIN_TOKEN"] = "admin-test-token"             # valeur factice
os.environ.setdefault("TRUST_PROXY_HOPS", "1")

import lumina_server as server  # noqa: E402


class FakeGroq:
    """Double de call_groq : enregistre les appels, réponses scriptées."""
    def __init__(self):
        self.calls = []
        self.fail = False
        self.observe_text = "Tu as bien rangé ton bureau."
        self.counter = 0

    def __call__(self, messages, preferred_model=None, temperature=0.75, reason_type="chat", max_tokens=4096, deadline_s=None):
        self.calls.append({"messages": messages, "model": preferred_model, "reason": reason_type, "max_tokens": max_tokens})
        if self.fail:
            return {"ok": False, "content": "Tous mes serveurs sont surchargés", "model": None, "reasoning": None}
        self.counter += 1
        last = messages[-1]["content"]
        has_img = isinstance(last, list)
        if reason_type == "live" and has_img and "Que vois-tu de nouveau" in str(last):
            return {"ok": True, "content": self.observe_text, "model": "fake-vision", "reasoning": None}
        return {"ok": True, "content": f"RÉPONSE_{self.counter}", "model": preferred_model or "fake", "reasoning": None}


class FakeResp:
    def __init__(self, status=200, payload=None):
        self.status_code = status; self._p = payload or {}; self.text = ""
    def json(self): return self._p


def install_fakes():
    if not hasattr(server, "real_call_groq"):
        server.real_call_groq = server.call_groq
    fake = FakeGroq(); server.call_groq = fake
    stt = {"text": "bonjour lumina", "status": 200, "calls": 0}
    real_post = server.requests.post
    def fake_post(url, *a, **k):
        if url == server.GROQ_STT_URL:
            stt["calls"] += 1
            return FakeResp(stt["status"], {"text": stt["text"]})
        raise AssertionError("appel réseau inattendu : " + str(url))
    server.requests.post = fake_post
    return fake, stt, real_post


def reset_limits():
    for name in ("LOGIN_LIMITER", "LOGIN_IP_LIMITER", "SIGNUP_LIMITER", "CHAT_LIMITER", "LIVE_LIMITER",
                 "STT_LIMITER", "FEEDBACK_LIMITER", "SEARCH_LIMITER"):
        getattr(server, name)._d.clear()
    server.cache.clear()


def start_http(port):
    from werkzeug.serving import make_server
    srv = make_server("127.0.0.1", port, server.app, threaded=True)
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    return srv
