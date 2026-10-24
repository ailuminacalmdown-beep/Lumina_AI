#!/usr/bin/env sh
# Lance Lumina en local sur http://localhost:5005 (SQLite, aucun accès à Neon).
# Usage : sh scripts/run_local.sh        (Termux inclus)
set -eu
cd "$(dirname "$0")/.."

[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
REQ=requirements.txt
[ -n "${TERMUX_VERSION:-}" ] && REQ=requirements-termux.txt     # pas de psycopg-binary sous Termux
pip install -q -r "$REQ"

if [ -f .env ]; then set -a; . ./.env; set +a; fi

# SÉCURITÉ : en local on n'utilise JAMAIS la base de production par accident.
if [ "${USE_DATABASE_URL:-0}" != "1" ]; then
  unset DATABASE_URL
  echo "→ Base SQLite locale (DATABASE_URL ignorée). Pour viser PostgreSQL : USE_DATABASE_URL=1 (base de TEST uniquement)."
fi
export TRUST_PROXY_HOPS="${TRUST_PROXY_HOPS:-0}"       # pas de proxy devant l'app en local

if [ -z "${GROQ_API_KEYS:-}" ]; then
  echo "⚠  GROQ_API_KEYS absente : le serveur démarre mais /chat répondra « indisponible ». Voir .env.example."
fi
echo "→ http://localhost:${PORT:-5005}"
exec python lumina_server.py
