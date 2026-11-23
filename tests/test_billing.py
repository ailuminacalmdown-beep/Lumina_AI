"""Plans et quotas (v8) : logique pure testée sur SQLite en mémoire, sans Flask."""
import json, re, sqlite3, time, unittest

SRC = open(__import__("os").path.join(__import__("os").path.dirname(__file__), "..", "lumina_server.py"), encoding="utf-8").read()
a = SRC.index("def utc_day(")
b = SRC.index('@app.route("/billing/status"')
SCHEMA = re.search(r'_V8_SQL_SQLITE = """(.*?)"""', SRC, re.S).group(1)


class DB:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:"); self.conn.row_factory = sqlite3.Row
        self.conn.executescript("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT);INSERT INTO users VALUES (1,'a@b.c');" + SCHEMA)
    def execute(self, q, p=()): return self.conn.execute(q, p)
    def commit(self): self.conn.commit()


def load(day=2, week=0, images=1, enabled=True, pro=(0, 0, 0)):
    ns = {"time": time, "json": json, "LIMITS_ENABLED": enabled,
          "PLAN_LIMITS": {"free": {"day": day, "week": week, "images": images},
                          "pro": {"day": pro[0], "week": pro[1], "images": pro[2]},
                          "max": {"day": 0, "week": 0, "images": 0}}}
    exec(SRC[a:b], ns)
    return ns


def sub(db, plan, now, start=-10, end=1000):
    db.execute("INSERT INTO subscriptions (user_id,plan,source,starts_at,expires_at,created_at) VALUES (1,?,'manual',?,?,?)",
               (plan, now + start, now + end, now))


class BillingTests(unittest.TestCase):
    def test_gratuit_par_defaut_et_quota_du_jour(self):
        N, db = load(day=2), DB()
        self.assertEqual(N["get_plan"](db, 1), ("free", None))
        self.assertTrue(N["check_quota"](db, 1, 1, False)[0])
        self.assertTrue(N["check_quota"](db, 1, 1, False)[0])
        ok, msg = N["check_quota"](db, 1, 1, False)
        self.assertFalse(ok); self.assertIn("limite d'utilisation du jour", msg)

    def test_prime_coute_plus_d_unites(self):
        N, db = load(day=5), DB()
        self.assertTrue(N["check_quota"](db, 1, 3, False)[0])      # 3 / 5
        self.assertTrue(N["check_quota"](db, 1, 3, False)[0])      # 6 : on bloque après dépassement
        self.assertFalse(N["check_quota"](db, 1, 1, False)[0])

    def test_plafond_hebdomadaire_glissant(self):
        N, db = load(day=0, week=3), DB(); t = time.time()
        for i in range(3):
            self.assertTrue(N["check_quota"](db, 1, 1, False, t + i * 86400)[0])    # 3 jours différents
        ok, msg = N["check_quota"](db, 1, 1, False, t + 3 * 86400)
        self.assertFalse(ok); self.assertIn("semaine", msg)
        self.assertTrue(N["check_quota"](db, 1, 1, False, t + 7 * 86400)[0])        # le 1er jour est sorti de la fenêtre

    def test_quota_photos_et_remboursement(self):
        N, db = load(day=50, images=1), DB()
        self.assertTrue(N["check_quota"](db, 1, 3, True)[0])
        self.assertFalse(N["check_quota"](db, 1, 3, True)[0])
        N["usage_add"](db, 1, "image", -1); N["usage_add"](db, 1, "chat", -3)
        self.assertTrue(N["check_quota"](db, 1, 3, True)[0])

    def test_plans_pro_max_expiration_revocation(self):
        N, db = load(), DB(); now = time.time()
        sub(db, "pro", now); self.assertEqual(N["get_plan"](db, 1)[0], "pro")
        sub(db, "max", now); self.assertEqual(N["get_plan"](db, 1)[0], "max")         # le meilleur plan gagne
        self.assertEqual(N["get_plan"](db, 1, now + 2000)[0], "free")                 # expirés
        db.execute("UPDATE subscriptions SET status='revoked'")
        self.assertEqual(N["get_plan"](db, 1)[0], "free")

    def test_ancien_plan_premium_vaut_pro(self):
        N, db = load(), DB(); now = time.time(); sub(db, "premium", now)
        self.assertEqual(N["get_plan"](db, 1)[0], "pro")

    def test_limites_du_plan_pro_appliquees(self):
        N, db = load(pro=(2, 0, 0)), DB(); now = time.time(); sub(db, "pro", now)
        self.assertTrue(N["check_quota"](db, 1, 1, False)[0]); self.assertTrue(N["check_quota"](db, 1, 1, False)[0])
        self.assertFalse(N["check_quota"](db, 1, 1, False)[0])

    def test_changement_de_jour(self):
        N, db = load(day=1), DB(); t = time.time()
        self.assertTrue(N["check_quota"](db, 1, 1, False, t)[0]); self.assertFalse(N["check_quota"](db, 1, 1, False, t)[0])
        self.assertTrue(N["check_quota"](db, 1, 1, False, t + 86400)[0])

    def test_compteur_de_recherches_web(self):
        N, db = load(), DB()
        N["usage_add"](db, 1, "web", 1); N["usage_add"](db, 1, "web", 1)
        self.assertEqual(N["usage_today"](db, 1)["web"], 2)
        self.assertEqual(N["usage_today"](db, 1, time.time() + 86400)["web"], 0)   # autre jour

    def test_limites_desactivees(self):
        N, db = load(day=1, enabled=False), DB()
        for _ in range(100): self.assertTrue(N["check_quota"](db, 1, 3, True)[0])


if __name__ == "__main__":
    unittest.main()
