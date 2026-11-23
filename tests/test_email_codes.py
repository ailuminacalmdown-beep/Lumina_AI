"""Codes email (v9) : logique pure testée sur SQLite en mémoire, sans Flask ni réseau."""
import hashlib, hmac, os, re, secrets, sqlite3, time, unittest

SRC = open(os.path.join(os.path.dirname(__file__), "..", "lumina_server.py"), encoding="utf-8").read()
a = SRC.index("def _code_hash(")
b = SRC.index("def email_unverified(")
SCHEMA = re.search(r'_V9_SQL_SQLITE = """(.*?)"""', SRC, re.S).group(1)


class DB:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:"); self.conn.row_factory = sqlite3.Row
        self.conn.executescript("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT);INSERT INTO users VALUES (1,'a@b.c');" + SCHEMA)
    def execute(self, q, p=()): return self.conn.execute(q, p)
    def commit(self): self.conn.commit()


def load():
    ns = {"hashlib": hashlib, "hmac": hmac, "secrets": secrets, "time": time, "CODE_TTL_S": 900, "CODE_MAX_ATTEMPTS": 5}
    exec(SRC[a:b], ns)
    return ns


class CodeTests(unittest.TestCase):
    def test_code_correct_consomme_une_seule_fois(self):
        N, db = load(), DB(); c = N["issue_code"](db, 1, "reset")
        self.assertRegex(c, r"^\d{6}$")
        self.assertTrue(N["check_code"](db, 1, "reset", c))
        self.assertFalse(N["check_code"](db, 1, "reset", c))            # déjà utilisé

    def test_mauvais_code_refuse_puis_verrouille_apres_5_essais(self):
        N, db = load(), DB(); c = N["issue_code"](db, 1, "reset"); bad = "000000" if c != "000000" else "111111"
        for _ in range(5): self.assertFalse(N["check_code"](db, 1, "reset", bad))
        self.assertFalse(N["check_code"](db, 1, "reset", c))            # le bon code ne passe plus : épuisé

    def test_expiration(self):
        N, db = load(), DB(); t = time.time(); c = N["issue_code"](db, 1, "verify", t)
        self.assertFalse(N["check_code"](db, 1, "verify", c, t + 901))
        c2 = N["issue_code"](db, 1, "verify", t)
        self.assertTrue(N["check_code"](db, 1, "verify", c2, t + 899))

    def test_nouveau_code_invalide_l_ancien(self):
        N, db = load(), DB(); c1 = N["issue_code"](db, 1, "reset"); c2 = N["issue_code"](db, 1, "reset")
        if c1 != c2: self.assertFalse(N["check_code"](db, 1, "reset", c1))
        self.assertTrue(N["check_code"](db, 1, "reset", c2))

    def test_les_types_sont_separes(self):
        N, db = load(), DB(); c = N["issue_code"](db, 1, "reset")
        self.assertFalse(N["check_code"](db, 1, "verify", c))           # un code de reset ne vérifie pas l'email

    def test_formats_invalides(self):
        N, db = load(), DB(); N["issue_code"](db, 1, "reset")
        for bad in ("", "abc123", "12345", "1234567", None, "12 345"): self.assertFalse(N["check_code"](db, 1, "reset", bad))

    def test_le_code_n_est_pas_stocke_en_clair(self):
        N, db = load(), DB(); c = N["issue_code"](db, 1, "reset")
        self.assertNotIn(c, db.execute("SELECT code_hash FROM email_tokens").fetchone()["code_hash"])


if __name__ == "__main__":
    unittest.main()
