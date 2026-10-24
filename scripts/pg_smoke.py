#!/usr/bin/env python3
"""Test de fumée PostgreSQL (Neon) — NON exécuté pendant le développement faute de base de test.

Vérifie que le code v7 fonctionne réellement sur PostgreSQL : schéma additif, inscription, connexion,
chat (fournisseur IA simulé), expiration de session, suppression de compte, isolation.
Il ne crée QUE ses propres comptes jetables (…@pg-smoke.invalid) et les supprime à la fin.

SÉCURITÉ : refuse de tourner sans TEST_DATABASE_URL et si elle est identique à DATABASE_URL.
Utilise une BRANCHE NEON DÉDIÉE AUX TESTS (jamais la branche « production »).

    pip install -r requirements.txt
    TEST_DATABASE_URL='postgresql://…branche-test…?sslmode=require' CONFIRM_TEST_DB=yes python scripts/pg_smoke.py
"""
import os, sys, time, types

test_url = os.environ.get("TEST_DATABASE_URL", "")
if not test_url or os.environ.get("CONFIRM_TEST_DB") != "yes":
    sys.exit("Refus : définir TEST_DATABASE_URL (branche de TEST) et CONFIRM_TEST_DB=yes.")
if test_url == os.environ.get("DATABASE_URL"):
    sys.exit("Refus : TEST_DATABASE_URL est identique à DATABASE_URL (production ?).")
if "production" in test_url.lower():
    sys.exit("Refus : l'URL mentionne « production ».")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    import flask_cors  # noqa: F401
except ImportError:
    m = types.ModuleType("flask_cors"); m.CORS = lambda *a, **k: None; sys.modules["flask_cors"] = m
os.environ["DATABASE_URL"] = test_url
os.environ.setdefault("GROQ_API_KEYS", "fake")
import lumina_server as s  # noqa: E402

assert s.DATABASE_URL == test_url
s.call_groq = lambda *a, **k: {"ok": True, "content": "réponse de test", "model": "fake", "reasoning": None}

ok = True
def check(name, cond):
    global ok
    print(("OK   " if cond else "ÉCHEC"), name); ok = ok and bool(cond)

c = s.app.test_client()
tag = int(time.time())
a, b = f"a{tag}@pg-smoke.invalid", f"b{tag}@pg-smoke.invalid"
check("schéma initialisé (ensure_schema)", s.ensure_schema())
check("/healthz", c.get("/healthz").status_code == 200)
ra = c.post("/auth/signup", json={"email": a, "password": "motdepasse1"}, headers={"X-Forwarded-For": "198.51.100.1"})
rb = c.post("/auth/signup", json={"email": b, "password": "motdepasse1"}, headers={"X-Forwarded-For": "198.51.100.2"})
check("inscription A et B", ra.status_code == 200 and rb.status_code == 200)
ta, tb = ra.json["token"], rb.json["token"]
H = lambda t: {"Authorization": "Bearer " + t}
check("login", c.post("/auth/login", json={"email": a, "password": "motdepasse1"}, headers={"X-Forwarded-For": "198.51.100.1"}).status_code == 200)
r = c.post("/chat", json={"message": "bonjour", "conv_id": "c1", "model": "openai/gpt-oss-20b"}, headers=H(ta))
check("chat + persistance", r.status_code == 200 and r.json["ok"])
with s.app.app_context():
    db = s.get_db()
    n = db.execute("SELECT COUNT(*) AS n FROM conv_memories WHERE user_id = ?", (ra.json["user"]["id"],)).fetchone()["n"]
    check("historique stocké pour A uniquement", n == 1 and db.execute("SELECT COUNT(*) AS n FROM conv_memories WHERE user_id = ?", (rb.json["user"]["id"],)).fetchone()["n"] == 0)
    db.execute("UPDATE sessions SET created_at = ? WHERE token = ?", (time.time() - s.SESSION_TTL - 60, tb)); db.commit()
check("session expirée refusée", c.get("/auth/me", headers=H(tb)).status_code == 401)
check("feedback", c.post("/feedback", json={"type": "like"}, headers=H(ta)).status_code == 200)
check("suppression du compte A", c.delete("/auth/account", json={"password": "motdepasse1"}, headers=H(ta)).status_code == 200)
with s.app.app_context():                                    # nettoyage du compte B (jetable)
    db = s.get_db()
    for t in ("feedback", "conv_memories", "user_knowledge", "sessions"):
        db.execute(f"DELETE FROM {t} WHERE user_id = ?", (rb.json["user"]["id"],))
    db.execute("DELETE FROM users WHERE id = ?", (rb.json["user"]["id"],)); db.commit()
    left = db.execute("SELECT COUNT(*) AS n FROM users WHERE email LIKE ?", (f"%{tag}@pg-smoke.invalid",)).fetchone()["n"]
check("aucun compte de test résiduel", left == 0)
print("\nRÉSULTAT :", "TOUS LES CONTRÔLES PASSENT" if ok else "ÉCHECS (voir ci-dessus)")
sys.exit(0 if ok else 1)
