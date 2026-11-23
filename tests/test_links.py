"""Lecture de liens : protection SSRF et extraction (sans réseau)."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("GROQ_API_KEYS", "gsk_test")
os.environ.setdefault("DB_FILE", os.path.join(os.environ.get("TMPDIR", "/tmp"), "lumina_links_test.db"))
import lumina_server as S


class LinkTests(unittest.TestCase):
    def test_hotes_non_publics_refuses(self):
        for h in ("127.0.0.1", "localhost", "10.0.0.5", "192.168.1.1", "169.254.169.254", "0.0.0.0", "::1", "172.16.0.1"):
            self.assertFalse(S._is_public_host(h), h)

    def test_ip_publique_acceptee(self):
        self.assertTrue(S._is_public_host("8.8.8.8"))

    def test_fetch_refuse_ssrf_sans_requete(self):
        for u in ("http://127.0.0.1:5005/status", "http://169.254.169.254/latest/meta-data/",
                  "http://user:pw@example.com/", "ftp://example.com/x", "http://8.8.8.8:22/"):
            self.assertIsNone(S.fetch_page_text(u), u)

    def test_extraction_urls(self):
        t = "Lis https://a.com/x, puis (https://b.org/y). Encore https://c.net/z https://a.com/x"
        self.assertEqual(S.extract_urls(t), ["https://a.com/x", "https://b.org/y"])


if __name__ == "__main__":
    unittest.main()
