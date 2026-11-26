"""Moteur (date réelle, nettoyage, boucle d'outils, archive d'actualités) : tests sans réseau ni Flask."""
import os, re, sqlite3, sys, time, unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import lumina_engine as E

SRC = open(os.path.join(os.path.dirname(__file__), "..", "lumina_server.py"), encoding="utf-8").read()
NEWS_SQL = re.search(r'_V10_SQL_SQLITE = """(.*?)"""', SRC, re.S).group(1)

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Journal Test</title>
<item><title>Election au Mali : les r&#233;sultats</title><link>https://ex.org/a</link><description>&lt;p&gt;Les &lt;b&gt;r&#233;sultats&lt;/b&gt; tombent.&lt;/p&gt;</description><pubDate>Mon, 23 Nov 2026 10:00:00 GMT</pubDate></item>
<item><title>Sans lien</title><description>x</description></item>
<item><title>Foot : la finale</title><link>https://ex.org/b</link><pubDate>Mon, 23 Nov 2026 12:30:00 +0000</pubDate></item>
</channel></rss>"""
ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Atom Test</title>
<entry><title>Pluie sur Bamako</title><link href="https://ex.org/c"/><summary>Orage</summary><updated>2026-11-23T08:00:00Z</updated></entry></feed>"""


class DB:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:"); self.conn.row_factory = sqlite3.Row
        self.conn.executescript(NEWS_SQL)
    def execute(self, q, p=()): return self.conn.execute(q, p)
    def commit(self): self.conn.commit()


class DateTests(unittest.TestCase):
    def test_date_reelle_et_annee(self):
        t = datetime(2026, 11, 24, 14, 5, tzinfo=timezone.utc)
        l = E.date_line(t)
        self.assertIn("mardi 24 novembre 2026", l); self.assertIn("14:05", l); self.assertIn("Nous sommes en 2026", l)

    def test_decalage_client(self):
        t = datetime(2026, 11, 24, 23, 30, tzinfo=timezone.utc)
        l = E.date_line(t, 60)           # Paris en hiver : on est déjà le lendemain
        self.assertIn("mercredi 25 novembre 2026", l); self.assertIn("00:30", l); self.assertIn("UTC+01:00", l)

    def test_premier_du_mois_et_offset_invalide(self):
        self.assertIn("1er janvier", E.date_line(datetime(2027, 1, 1, 12, 0, tzinfo=timezone.utc)))
        for bad in ("abc", None, 5000, -9999): self.assertIsNone(E.clean_offset(bad))
        self.assertEqual(E.clean_offset("-180"), -180)


class SanitizerTests(unittest.TestCase):
    def test_retire_les_pseudo_appels(self):
        txt = 'Je cherche.\n<function_calls>\n<invoke name="web_search">\n<parameter name="query">x</parameter>\n</invoke>\n</function_calls>\nVoici.'
        out = E.strip_tool_markup(txt)
        self.assertNotIn("function_calls", out); self.assertNotIn("invoke", out); self.assertIn("Voici.", out)

    def test_bloc_non_ferme_et_texte_normal(self):
        self.assertEqual(E.strip_tool_markup("Avant <function_calls><invoke name='a'>"), "Avant")
        self.assertEqual(E.strip_tool_markup("Un <b>texte</b> normal avec a < b."), "Un <b>texte</b> normal avec a < b.")
        self.assertEqual(E.strip_tool_markup(None), "")


class AgentTests(unittest.TestCase):
    def call(self, name, args, cid="c1"):
        import json
        return {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}

    def test_outil_puis_reponse(self):
        seen = []
        def chat_fn(msgs, tools):
            if not any(m["role"] == "tool" for m in msgs):
                return {"content": "", "tool_calls": [self.call("web_search", {"query": "singuila"})], "model": "m"}
            return {"content": "Réponse finale [1]", "tool_calls": [], "reasoning": "r", "model": "m"}
        def impl(name, args): seen.append((name, args)); return "Recherche : singuila", "[1] page"
        r = E.run_agent(chat_fn, [{"role": "user", "content": "q"}], impl)
        self.assertEqual(seen, [("web_search", {"query": "singuila"})])
        self.assertEqual(r["tools_used"], 1); self.assertEqual(r["activity"], ["Recherche : singuila"]); self.assertIn("finale", r["content"])

    def test_sans_outil_une_seule_etape(self):
        n = []
        def chat_fn(msgs, tools): n.append(1); return {"content": "Bonjour", "tool_calls": []}
        r = E.run_agent(chat_fn, [], lambda *a: ("", ""))
        self.assertEqual(len(n), 1); self.assertEqual(r["tools_used"], 0)

    def test_boucle_infinie_bornee_et_derniere_etape_sans_outils(self):
        tools_offered = []
        def chat_fn(msgs, tools):
            tools_offered.append(bool(tools))
            return {"content": "fin" if not tools else "", "tool_calls": [] if not tools else [self.call("web_search", {"query": "x"})]}
        r = E.run_agent(chat_fn, [], lambda n, a: ("Recherche", "ok"), max_steps=3)
        self.assertEqual(tools_offered, [True, True, False]); self.assertEqual(r["content"], "fin")

    def test_limite_d_outils(self):
        calls = []
        def chat_fn(msgs, tools):
            if tools: return {"content": "", "tool_calls": [self.call("web_search", {"query": "x"}, f"c{i}") for i in range(3)]}
            return {"content": "ok", "tool_calls": []}
        def impl(n, a): calls.append(n); return "L", "r"
        E.run_agent(chat_fn, [], impl, max_steps=4, max_tool_calls=4)
        self.assertEqual(len(calls), 4)

    def test_arguments_invalides_ne_plantent_pas(self):
        def chat_fn(msgs, tools):
            if tools: return {"content": "", "tool_calls": [{"id": "x", "function": {"name": "read_page", "arguments": "{pas du json"}}]}
            return {"content": "ok", "tool_calls": []}
        got = []
        E.run_agent(chat_fn, [], lambda n, a: (got.append(a), ("L", "r"))[1], max_steps=2)
        self.assertEqual(got, [{}])

    def test_reponse_vide_ou_fournisseur_refuse(self):
        with self.assertRaises(E.EngineUnavailable): E.run_agent(lambda m, t: {"content": "", "tool_calls": []}, [], lambda *a: ("", ""))
        def boom(m, t): raise E.EngineUnavailable("HTTP 400")
        with self.assertRaises(E.EngineUnavailable): E.run_agent(boom, [], lambda *a: ("", ""))

    def test_balises_nettoyees_dans_la_reponse_finale(self):
        r = E.run_agent(lambda m, t: {"content": "Salut <function_calls><invoke name='x'></invoke></function_calls>", "tool_calls": []}, [], lambda *a: ("", ""))
        self.assertEqual(r["content"], "Salut")


class NewsTests(unittest.TestCase):
    def test_parse_rss_et_atom(self):
        a = E.parse_feed(RSS)
        self.assertEqual([x["url"] for x in a], ["https://ex.org/a", "https://ex.org/b"])       # l'élément sans lien est ignoré
        self.assertEqual(a[0]["title"], "Élection au Mali : les résultats".replace("Élection", "Election"))
        self.assertEqual(a[0]["summary"], "Les résultats tombent."); self.assertEqual(a[0]["source"], "Journal Test")
        self.assertTrue(a[0]["published_at"] > 1.7e9)
        b = E.parse_feed(ATOM); self.assertEqual(b[0]["url"], "https://ex.org/c"); self.assertEqual(b[0]["source"], "Atom Test")

    def test_flux_dangereux_ou_invalide_refuses(self):
        self.assertEqual(E.parse_feed(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel><item><title>t</title><link>https://x</link></item></channel></rss>'), [])
        self.assertEqual(E.parse_feed(b"pas du xml"), [])
        self.assertEqual(E.parse_feed(b"x" * 2_000_000), [])
        self.assertEqual(E.parse_feed(RSS.replace(b"https://ex.org/a", b"javascript:alert(1)")).__len__(), 1)

    def test_archive_upsert_recherche_et_purge(self):
        db, now = DB(), 1795000000.0
        items = E.parse_feed(RSS) + E.parse_feed(ATOM)
        self.assertEqual(E.news_upsert(db, items, now), 3)
        self.assertEqual(E.news_upsert(db, items, now + 10), 3)                                   # pas de doublon
        self.assertEqual(db.execute("SELECT COUNT(*) AS n FROM news_items").fetchone()["n"], 3)
        t = db.execute("SELECT MAX(published_at) AS t FROM news_items").fetchone()["t"]
        res = E.news_query(db, "mali", 72, 8, now=t + 3600)
        self.assertEqual([r["url"] for r in res], ["https://ex.org/a"])
        self.assertEqual(len(E.news_query(db, "", 72, 8, now=t + 3600)), 3)
        self.assertEqual(E.news_query(db, "mali", 1, 8, now=t + 7 * 3600), [])                    # fenêtre trop courte
        self.assertEqual(E.news_last_fetch(db), now + 10)                                          # dernier passage enregistré
        E.news_prune(db, 14 * 86400, now=t + 30 * 86400); self.assertEqual(E.news_query(db, "", 336, 8, now=t + 30 * 86400), [])
        self.assertEqual(E.news_last_fetch(db), 0.0)                                               # archive vide après purge


if __name__ == "__main__":
    unittest.main()
