#!/usr/bin/env sh
# Lance tous les tests disponibles. Aucun secret, aucun accès réseau, aucune base de production.
#   1) backend (unittest, stdlib)    2) initialisation du frontend (Node)    3) navigateur (si Playwright installé)
set -u
cd "$(dirname "$0")/.."
[ -d .venv ] && . .venv/bin/activate
rc=0
echo "== 1/3 Backend =="
python3 -W ignore::ResourceWarning -m unittest discover -s tests -p "test_backend.py" || rc=1
echo "== 2/3 Initialisation du frontend =="
if command -v node >/dev/null 2>&1; then node tests/frontend_boot.test.js || rc=1; else echo "node absent : test non exécuté"; fi
echo "== 3/3 Navigateur (facultatif) =="
if python3 -c "import playwright" 2>/dev/null; then
  python3 -W ignore::ResourceWarning tests/e2e_browser.py || rc=1
else
  echo "playwright absent : tests de bout en bout non exécutés (pip install -r requirements-dev.txt && playwright install chromium)"
fi
exit $rc
