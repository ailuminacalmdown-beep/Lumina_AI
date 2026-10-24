#!/usr/bin/env python3
"""
Lumina Server v7.0
Développé par Issa Amakendé Abdoulaye Koné

Améliorations v6.1 :
- GPT-OSS 20B comme modèle Flash par défaut
- Routage automatique Flash / Prime
- Validation des modèles demandés
- Fallback automatique entre modèles
- Gestion améliorée des erreurs Groq
- Support reasoning_effort
- Statut serveur enrichi
- Conservation de la mémoire, auth, cache, recherche web et API existantes
"""

from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

import requests
import json
import time
import os
import threading
import sqlite3
import secrets
import re

from collections import OrderedDict
from werkzeug.middleware.proxy_fix import ProxyFix
import hmac
DATABASE_URL = os.environ.get("DATABASE_URL")

# ══════════════════════════════════════════════════════════════════════════════
# CLÉS API
# ══════════════════════════════════════════════════════════════════════════════

GROQ_KEYS = [
    k.strip()
    for k in os.environ.get("GROQ_API_KEYS", "").split(",")
    if k.strip()
]

if not GROQ_KEYS:
    print("\n⚠️  Aucune clé Groq trouvée dans l'environnement.")
    print("   Défini GROQ_API_KEYS avant de lancer le serveur.\n")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION V7 (tout est surchargeable par variable d'environnement)
# ══════════════════════════════════════════════════════════════════════════════

def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


MAX_MESSAGE_CHARS = _env_int("MAX_MESSAGE_CHARS", 8000)
MAX_IMAGE_B64 = _env_int("MAX_IMAGE_B64", 4_000_000)        # limite Groq ~4 Mo en base64
MAX_LIVE_IMAGE_B64 = _env_int("MAX_LIVE_IMAGE_B64", 1_500_000)
MAX_AUDIO_BYTES = _env_int("MAX_AUDIO_BYTES", 2_500_000)
MAX_REQUEST_BYTES = _env_int("MAX_REQUEST_BYTES", 6_000_000)
SESSION_TTL = _env_int("SESSION_TTL_DAYS", 30) * 86400
MAX_SESSIONS_PER_USER = _env_int("MAX_SESSIONS_PER_USER", 20)
GROQ_TOTAL_TIMEOUT = _env_int("GROQ_TOTAL_TIMEOUT", 45)    # secondes, toute la cascade
DB_CONNECT_TIMEOUT = _env_int("DB_CONNECT_TIMEOUT", 10)
TRUST_PROXY_HOPS = _env_int("TRUST_PROXY_HOPS", 1)         # Render = 1 proxy devant l'app
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "").strip()
GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_STT_MODEL = os.environ.get("GROQ_STT_MODEL", "whisper-large-v3-turbo").strip()
APP_VERSION = "7.0"


# ══════════════════════════════════════════════════════════════════════════════
# MODÈLES LUMINA
# ══════════════════════════════════════════════════════════════════════════════

PRIME_MODEL = "qwen/qwen3.6-27b"
FLASH_MODEL = "openai/gpt-oss-20b"

# Ancien modèle conservé comme compatibilité / fallback.
LEGACY_MODEL = "openai/gpt-oss-120b"

# Modèles de secours.
GROQ_MODELS_CASCADE = [
    PRIME_MODEL,
    FLASH_MODEL,
    LEGACY_MODEL,
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

MODELS_DISPLAY = {
    PRIME_MODEL: "Lumina Prime — Qwen 3.6 27B",
    FLASH_MODEL: "Lumina Flash — GPT-OSS 20B",
    LEGACY_MODEL: "GPT-OSS 120B — Legacy",
    "llama-3.3-70b-versatile": "Llama 3.3 70B",
    "llama-3.1-8b-instant": "Llama 3.1 8B Instant",
}

# ⭐ NOUVEAU MODÈLE PAR DÉFAUT
DEFAULT_MODEL = FLASH_MODEL

# Modèles que le frontend est autorisé à demander.
VALID_MODELS = set(MODELS_DISPLAY.keys())

# Modèles supportant le format multimodal (vision) sur Groq.
_vis_env = [m.strip() for m in os.environ.get("GROQ_VISION_MODELS", "").split(",") if m.strip()]
# Ordre = priorité. Par défaut : Prime (comme en v6.1). À surcharger si Groq change son catalogue.
VISION_MODEL_LIST = _vis_env or [PRIME_MODEL]
VISION_MODELS = set(VISION_MODEL_LIST)


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT V6
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """Tu es Lumina, une IA personnelle développée par Issa Amakendé Abdoulaye Koné au Mali. Tu parles en français.

PERSONNALITÉ :
Tu es confiante, directe, parfois légèrement sarcastique avec élégance.
Tu as du caractère.
Tu n'hésites pas à donner ton avis.
Quand tu ne sais pas, tu l'assumes.
Tu parles avec chaleur mais jamais de façon robotique.

RÈGLES ABSOLUES DE FORMATAGE :
- Tu réponds EN MARKDOWN.
- Utilise **gras** pour les points importants.
- Utilise *italique* pour l'emphase.
- Utilise `code` pour les termes techniques.
- Utilise des titres (##) pour structurer les réponses longues.
- Utilise des listes à puces (-) pour les énumérations.
- Quand tu écris du code, utilise TOUJOURS des blocs markdown avec le langage.
- Ne répète PAS la question de l'utilisateur.
- Ne commence JAMAIS par "Bien sûr", "Certainement", "Absolument".
- Va droit au but.
- Sois concise mais complète.

RÈGLES D'UTILISATION DES OUTILS :
- Ne jamais utiliser un outil sans que l'utilisateur ne le demande explicitement.
- Si l'utilisateur demande une information factuelle récente ou dit "cherche", "recherche", "trouve", "quelle est l'actualité" → recherche web autorisée.
- Si l'utilisateur demande explicitement une image ou dit "génère", "dessine", "crée une image" → génération d'image autorisée.
- Si aucun outil n'est demandé → réponds normalement sans outil.

RÈGLES DE RÉFLEXION :
- Pour une tâche complexe, raisonne de manière structurée en interne.
- Ne révèle pas de raisonnement interne détaillé ou de chaîne de pensée privée.
- Donne plutôt une explication claire, vérifiable et concise de la solution.
"""


# ══════════════════════════════════════════════════════════════════════════════
# FLASK
# ══════════════════════════════════════════════════════════════════════════════

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

WEB_DIR = os.path.join(BASE_DIR, "www")

# static_folder=None : aucune route statique implicite. Seul www/ est servi (voir static_files).
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES

if TRUST_PROXY_HOPS > 0:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=TRUST_PROXY_HOPS, x_proto=TRUST_PROXY_HOPS)

_cors_env = os.environ.get("CORS_ORIGINS", "*").strip()

CORS_ALLOWED = (
    "*"
    if _cors_env == "*"
    else [o.strip() for o in _cors_env.split(",") if o.strip()]
)

CORS(
    app,
    resources={
        r"/*": {
            "origins": CORS_ALLOWED
        }
    }
)


# ══════════════════════════════════════════════════════════════════════════════
# CACHE
# ══════════════════════════════════════════════════════════════════════════════

cache = OrderedDict()

CACHE_SIZE = 200
CACHE_TTL = 3600

cache_lock = threading.Lock()


def cache_get(key):
    with cache_lock:
        entry = cache.get(key)

        if entry and time.time() - entry["ts"] < CACHE_TTL:
            cache.move_to_end(key)
            return entry["data"]

        if entry:
            del cache[key]

    return None


def cache_set(key, data):
    with cache_lock:

        if len(cache) >= CACHE_SIZE:
            cache.popitem(last=False)

        cache[key] = {
            "data": data,
            "ts": time.time()
        }


# ══════════════════════════════════════════════════════════════════════════════
# BASE DE DONNÉES
# ══════════════════════════════════════════════════════════════════════════════

DB_FILE = os.environ.get("SQLITE_PATH") or os.path.join(BASE_DIR, "lumina.db")

EMAIL_RE = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
)

class DBConnection:
    """Façade commune SQLite / PostgreSQL (placeholders '?' → '%s' pour psycopg)."""

    def __init__(self, conn, postgres=False):
        self.conn = conn
        self.postgres = postgres

    def execute(self, query, params=()):
        if self.postgres:
            # '%' littéral doublé, puis '?' → '%s' (psycopg utilise %s).
            query = query.replace("%", "%%").replace("?", "%s")
        return self.conn.execute(query, params)

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()


def get_db():
    if "db" not in g:
        if DATABASE_URL:
            import psycopg
            from psycopg.rows import dict_row
            conn = psycopg.connect(
                DATABASE_URL,
                row_factory=dict_row,
                connect_timeout=DB_CONNECT_TIMEOUT,
            )
            g.db = DBConnection(conn, postgres=True)
        else:
            conn = sqlite3.connect(DB_FILE, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 5000")
            g.db = DBConnection(conn, postgres=False)
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        try:
            if exception is not None:
                db.rollback()
        except Exception:
            pass
        db.close()


def init_db():

    if DATABASE_URL:
        import psycopg

        conn = psycopg.connect(
            DATABASE_URL
        )

        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT,
                created_at DOUBLE PRECISION NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                created_at DOUBLE PRECISION NOT NULL,
                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_knowledge (
                user_id BIGINT PRIMARY KEY,
                connaissances TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS conv_memories (
                user_id BIGINT NOT NULL,
                conv_id TEXT NOT NULL,
                historique TEXT NOT NULL DEFAULT '[]',
                updated_at DOUBLE PRECISION NOT NULL,
                PRIMARY KEY (user_id, conv_id),
                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS memories (
                user_id BIGINT PRIMARY KEY,
                historique TEXT NOT NULL DEFAULT '[]',
                connaissances TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            );
        """)

        conn.commit()
        conn.close()

    else:
        conn = sqlite3.connect(DB_FILE)

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_knowledge (
                user_id INTEGER PRIMARY KEY,
                connaissances TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS conv_memories (
                user_id INTEGER NOT NULL,
                conv_id TEXT NOT NULL,
                historique TEXT NOT NULL DEFAULT '[]',
                updated_at REAL NOT NULL,
                PRIMARY KEY (user_id, conv_id),
                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            );
        """)

        conn.commit()
        conn.close()


# ── Migration additive v7 (idempotente, réversible) ──────────────────────────
# Ajoute uniquement : table feedback + index sur sessions. Aucune donnée existante n'est touchée.
# Retour arrière : DROP TABLE feedback; DROP INDEX idx_sessions_user; DROP INDEX idx_sessions_created;
_V7_SQL_SQLITE = """
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    conv_id TEXT,
    message_id TEXT,
    text TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at);
"""
_V7_SQL_PG = """
CREATE TABLE IF NOT EXISTS feedback (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    conv_id TEXT,
    message_id TEXT,
    text TEXT,
    created_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at);
"""


def _add_v7_tables():
    if DATABASE_URL:
        import psycopg
        conn = psycopg.connect(DATABASE_URL, connect_timeout=DB_CONNECT_TIMEOUT)
        try:
            conn.execute(_V7_SQL_PG)
            conn.commit()
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(DB_FILE)
        try:
            conn.executescript(_V7_SQL_SQLITE)
            conn.commit()
        finally:
            conn.close()


_schema_ready = False
_schema_lock = threading.Lock()


def _safe_err(e):
    msg = f"{type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}"
    if DATABASE_URL:
        msg = msg.replace(DATABASE_URL, "***")
    return msg[:200]


def ensure_schema():
    """Initialise le schéma sans jamais faire planter le démarrage si la base dort/est injoignable."""
    global _schema_ready
    if _schema_ready:
        return True
    with _schema_lock:
        if _schema_ready:
            return True
        try:
            init_db()
            _add_v7_tables()
            _schema_ready = True
        except Exception as e:
            print(f"[DB] initialisation impossible : {_safe_err(e)}")
            return False
    return True


ensure_schema()

# ══════════════════════════════════════════════════════════════════════════════
# MÉMOIRE
# ══════════════════════════════════════════════════════════════════════════════

def load_knowledge(user_id):

    db = get_db()

    row = db.execute(
        "SELECT connaissances FROM user_knowledge WHERE user_id = ?",
        (user_id,)
    ).fetchone()

    if not row:

        db.execute(
            "INSERT INTO user_knowledge (user_id, connaissances) VALUES (?, '{}')",
            (user_id,)
        )

        db.commit()

        return {}

    try:
        return json.loads(row["connaissances"])

    except Exception:
        return {}


def save_knowledge(user_id, connaissances):

    db = get_db()

    db.execute(
        """
        UPDATE user_knowledge
        SET connaissances = ?
        WHERE user_id = ?
        """,
        (
            json.dumps(
                connaissances,
                ensure_ascii=False
            ),
            user_id
        )
    )

    db.commit()


def load_conv_history(user_id, conv_id):

    db = get_db()

    row = db.execute(
        """
        SELECT historique
        FROM conv_memories
        WHERE user_id = ? AND conv_id = ?
        """,
        (user_id, conv_id)
    ).fetchone()

    if not row:
        return []

    try:
        return json.loads(row["historique"])

    except Exception:
        return []


def save_conv_history(user_id, conv_id, historique):

    db = get_db()

    db.execute(
        """
        INSERT INTO conv_memories
        (user_id, conv_id, historique, updated_at)
        VALUES (?, ?, ?, ?)

        ON CONFLICT(user_id, conv_id)
        DO UPDATE SET
            historique = excluded.historique,
            updated_at = excluded.updated_at
        """,
        (
            user_id,
            conv_id,
            json.dumps(
                historique,
                ensure_ascii=False
            ),
            time.time()
        )
    )

    db.commit()


def delete_conv_history(user_id, conv_id):

    db = get_db()

    db.execute(
        """
        DELETE FROM conv_memories
        WHERE user_id = ? AND conv_id = ?
        """,
        (user_id, conv_id)
    )

    db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════════════════════

class SlidingWindow:
    """Fenêtre glissante en mémoire (par processus : voir DEPLOY.md, 1 seul worker gunicorn)."""

    def __init__(self, limit, window):
        self.limit = limit
        self.window = window
        self._d = {}
        self._lock = threading.Lock()
        self._n = 0

    def _prune(self, key, now):
        q = [t for t in self._d.get(key, []) if now - t < self.window]
        if q:
            self._d[key] = q
        else:
            self._d.pop(key, None)
        return q

    def _tick(self, now):
        self._n += 1
        if self._n % 500 == 0:
            for k in list(self._d):
                self._prune(k, now)

    def blocked(self, key):
        now = time.time()
        with self._lock:
            return len(self._prune(key, now)) >= self.limit

    def add(self, key):
        now = time.time()
        with self._lock:
            q = self._prune(key, now)
            q.append(now)
            self._d[key] = q
            self._tick(now)

    def allow(self, key):
        """True si autorisé (et consomme un jeton), False si la limite est atteinte."""
        now = time.time()
        with self._lock:
            q = self._prune(key, now)
            if len(q) >= self.limit:
                return False
            q.append(now)
            self._d[key] = q
            self._tick(now)
            return True

    def clear(self, key):
        with self._lock:
            self._d.pop(key, None)


LOGIN_MAX_ATTEMPTS = 8
LOGIN_WINDOW = 300
CHAT_MAX_PER_MIN = 20
SIGNUP_MAX_PER_HOUR = _env_int("SIGNUP_MAX_PER_HOUR", 10)
LIVE_MAX_PER_MIN = _env_int("LIVE_MAX_PER_MIN", 40)

LOGIN_LIMITER = SlidingWindow(LOGIN_MAX_ATTEMPTS, LOGIN_WINDOW)        # clé : email|ip
LOGIN_IP_LIMITER = SlidingWindow(40, LOGIN_WINDOW)                     # clé : ip
SIGNUP_LIMITER = SlidingWindow(SIGNUP_MAX_PER_HOUR, 3600)              # clé : ip
CHAT_LIMITER = SlidingWindow(CHAT_MAX_PER_MIN, 60)                     # clé : user_id
LIVE_LIMITER = SlidingWindow(LIVE_MAX_PER_MIN, 60)
STT_LIMITER = SlidingWindow(LIVE_MAX_PER_MIN, 60)
FEEDBACK_LIMITER = SlidingWindow(30, 60)
SEARCH_LIMITER = SlidingWindow(10, 60)


def client_ip():
    return request.remote_addr or "?"


def login_blocked(email, ip):
    # Clé (email, ip) : un tiers ne peut plus verrouiller le compte d'une victime depuis une autre IP.
    return (
        LOGIN_LIMITER.blocked(f"{email}|{ip}")
        or LOGIN_IP_LIMITER.blocked(ip)
    )


def register_failed_login(email, ip):
    LOGIN_LIMITER.add(f"{email}|{ip}")
    LOGIN_IP_LIMITER.add(ip)


def clear_login_attempts(email, ip):
    LOGIN_LIMITER.clear(f"{email}|{ip}")


def chat_rate_limited(user_id):
    return not CHAT_LIMITER.allow(user_id)


# ══════════════════════════════════════════════════════════════════════════════
# AUTH DECORATOR
# ══════════════════════════════════════════════════════════════════════════════

def purge_expired_sessions(db):
    db.execute("DELETE FROM sessions WHERE created_at < ?", (time.time() - SESSION_TTL,))
    db.commit()


def trim_user_sessions(db, user_id):
    keep = max(1, MAX_SESSIONS_PER_USER - 1)
    db.execute(
        "DELETE FROM sessions WHERE user_id = ? AND token NOT IN "
        "(SELECT token FROM sessions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?)",
        (user_id, user_id, keep),
    )
    db.commit()


def get_bearer_token():
    auth_header = request.headers.get("Authorization", "")
    return auth_header[7:].strip() if auth_header.startswith("Bearer ") else None


def require_auth(f):

    @wraps(f)
    def wrapper(*args, **kwargs):

        token = get_bearer_token()

        if not token:
            return jsonify({"error": "Authentification requise"}), 401

        db = get_db()

        row = db.execute(
            "SELECT user_id, created_at FROM sessions WHERE token = ?",
            (token,)
        ).fetchone()

        if not row:
            return jsonify({"error": "Session invalide ou expirée"}), 401

        if time.time() - float(row["created_at"]) > SESSION_TTL:
            db.execute("DELETE FROM sessions WHERE token = ?", (token,))
            db.commit()
            return jsonify({"error": "Session expirée, reconnecte-toi"}), 401

        request.user_id = row["user_id"]

        return f(*args, **kwargs)

    return wrapper


# ══════════════════════════════════════════════════════════════════════════════
# CONTEXTE
# ══════════════════════════════════════════════════════════════════════════════

CTX_MAX_CHARS = 6000


def build_ctx(q, historique, connaissances):

    turns = []

    for entry in historique[-10:]:

        turns.append(
            f"Utilisateur: {entry['user']}\n"
            f"Lumina: {entry['assistant']}"
        )

    kept = []
    total = 0

    for turn in reversed(turns):

        total += len(turn)

        if total > CTX_MAX_CHARS:
            break

        kept.append(turn)

    kept.reverse()

    ctx = "\n".join(kept)

    if connaissances:

        ctx += (
            "\n\nCe que tu sais sur cet utilisateur :\n"
            +
            "\n".join(
                f"- {k}: {v}"
                for k, v in connaissances.items()
            )
        )

    return (
        f"{ctx}\n\nQuestion: {q}"
        if ctx
        else q
    )


# ══════════════════════════════════════════════════════════════════════════════
# DÉTECTION D'INTENTION
# ══════════════════════════════════════════════════════════════════════════════

WEB_KEYWORDS = [

    "cherche",
    "recherche",
    "rechercher",
    "trouve",
    "trouver",
    "actualité",
    "actualites",
    "actualités",
    "news",
    "dernières nouvelles",
    "quelle est la météo",
    "météo",
    "meteo",
    "quelle heure est-il",
    "date du jour",
    "qui est",
    "qu'est-ce que",
    "définition de",
    "prix de",
    "cours de",
    "bourse",
    "résultat",
    "score",
    "match",
    "élection",
]


IMG_KEYWORDS = [

    "génère",
    "genere",
    "dessine",
    "crée une image",
    "crée une photo",
    "génère une image",
    "génère une photo",
    "image de",
    "photo de",
    "fais une image",
    "fais un dessin",
]


def detect_intent(message):

    msg_lower = message.lower()

    intent = {
        "web": False,
        "image": False,
        "graph": False
    }

    for kw in WEB_KEYWORDS:

        if kw in msg_lower:

            intent["web"] = True

            break

    for kw in IMG_KEYWORDS:

        if kw in msg_lower:

            intent["image"] = True

            break

    if re.search(
        r"^(y|f\(x\)|f)\s*=\s*(.+)",
        msg_lower
    ):
        intent["graph"] = True

    return intent


# ══════════════════════════════════════════════════════════════════════════════
# ROUTEUR LUMINA
# ══════════════════════════════════════════════════════════════════════════════

def route_model(
    message="",
    intent=None,
    has_image=False,
    has_tool=False
):

    """
    Choisit automatiquement Flash ou Prime.

    PRIME :
    - vision
    - outils
    - recherche
    - génération
    - graphes
    - tâches complexes

    FLASH :
    - conversation normale
    """

    message = (message or "").strip()

    intent = intent or {}

    if has_image:
        return PRIME_MODEL, "vision"

    if has_tool:
        return PRIME_MODEL, "tool"

    if intent.get("web"):
        return PRIME_MODEL, "web"

    if intent.get("image"):
        return PRIME_MODEL, "image"

    if intent.get("graph"):
        return PRIME_MODEL, "graph"

    complex_keywords = [

        "analyse",
        "analyse-moi",
        "explique en détail",
        "raisonne",
        "raisonnement",
        "compare en profondeur",
        "résous",
        "démontre",
        "preuve",
        "algorithme",
        "architecture",
        "programme",
        "code",
        "debug",
        "corrige mon code",
        "projet",
        "mathématiques",
        "mathématique",
        "équation",
        "physique",
        "chimie",
        "médecine",
    ]

    msg_lower = message.lower()

    if any(
        keyword in msg_lower
        for keyword in complex_keywords
    ):
        return PRIME_MODEL, "complex"

    return FLASH_MODEL, "chat"


# ══════════════════════════════════════════════════════════════════════════════
# VALIDATION DU MODÈLE
# ══════════════════════════════════════════════════════════════════════════════

def normalize_model(model):

    """
    Évite qu'un ancien modèle envoyé par le frontend
    empêche le nouveau DEFAULT_MODEL de fonctionner.
    """

    if not model:
        return DEFAULT_MODEL

    model = str(model).strip()

    # Le frontend peut demander "default" ou "flash".
    if model.lower() in (
        "default",
        "auto",
        "flash",
        "lumina-flash",
    ):
        return DEFAULT_MODEL

    if model in VALID_MODELS:
        return model

    # Compatibilité : ancien modèle éventuellement encore
    # présent dans un ancien frontend.
    if model == LEGACY_MODEL:
        return DEFAULT_MODEL

    print(
        f"[MODEL] Modèle inconnu '{model}' → "
        f"{DEFAULT_MODEL}"
    )

    return DEFAULT_MODEL


# ══════════════════════════════════════════════════════════════════════════════
# REASONING
# ══════════════════════════════════════════════════════════════════════════════

def reasoning_settings(model, reason_type="chat"):

    """
    Configure le raisonnement uniquement pour les modèles
    qui le supportent.

    GPT-OSS :
        low / medium / high

    Qwen :
        none / default
    """

    if model in (
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
    ):

        if reason_type in (
            "complex",
            "vision",
            "tool",
            "web",
            "graph",
        ):
            return {
                "reasoning_effort": "medium",
                "reasoning_format": "parsed"
            }

        return {
            "reasoning_effort": "low",
            "reasoning_format": "parsed"
        }

    if model == PRIME_MODEL:

        if reason_type in (
            "complex",
            "web",
            "graph",
            "vision",
            "tool",
        ):
            return {
                "reasoning_effort": "default",
                "reasoning_format": "parsed"
            }

        return {
            "reasoning_effort": "none"
        }

    return {}


# ══════════════════════════════════════════════════════════════════════════════
# APPEL GROQ
# ══════════════════════════════════════════════════════════════════════════════

def is_multimodal(messages):
    """Détecte si le payload contient une image (format OpenAI multimodal)."""
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "image_url":
                    return True
    return False


def call_groq(
    messages,
    preferred_model=DEFAULT_MODEL,
    temperature=0.75,
    reason_type="chat",
    max_tokens=4096,
    deadline_s=None
):

    preferred_model = normalize_model(
        preferred_model
    )

    is_mm = is_multimodal(messages)

    # Délai global pour TOUTE la cascade (évite le worker tué par gunicorn à 120 s).
    t_deadline = time.time() + (deadline_s or GROQ_TOTAL_TIMEOUT)

    # Un message avec image ne doit jamais partir vers un modèle non-vision.
    if is_mm and preferred_model not in VISION_MODELS:
        preferred_model = VISION_MODEL_LIST[0]

    models_to_try = [
        preferred_model
    ]

    for model in GROQ_MODELS_CASCADE:

        if model not in models_to_try:

            if is_mm and model not in VISION_MODELS:
                print(
                    f"[GROQ] Skip {model} — "
                    f"non-vision, multimodal payload"
                )
                continue

            models_to_try.append(model)

    for model in models_to_try:

        if time.time() >= t_deadline:
            break

        settings = reasoning_settings(
            model,
            reason_type
        )

        for key_index, api_key in enumerate(GROQ_KEYS):

            if time.time() >= t_deadline:
                break

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            payload.update(settings)

            for attempt in range(2):

                if time.time() >= t_deadline:
                    break

                try:

                    r = requests.post(
                        GROQ_URL,
                        headers=headers,
                        json=payload,
                        timeout=max(2, min(30, t_deadline - time.time()))
                    )

                    if r.status_code == 200:

                        data = r.json()

                        choices = data.get(
                            "choices",
                            []
                        )

                        if not choices:

                            print(
                                f"[GROQ] Réponse sans choices — {model}"
                            )

                            break

                        msg = choices[0].get(
                            "message",
                            {}
                        )

                        content = (
                            msg.get("content")
                            or ""
                        ).strip()

                        reasoning = (
                            msg.get("reasoning")
                            or ""
                        ).strip() or None

                        print(
                            f"[GROQ] ✅ {model} "
                            f"(clé {key_index + 1})"
                            +
                            (
                                " +raisonnement"
                                if reasoning
                                else ""
                            )
                        )

                        return {
                            "ok": True,
                            "content": content,
                            "model": model,
                            "reasoning": reasoning,
                        }

                    elif r.status_code == 429:

                        print(
                            f"[GROQ] 429 {model} "
                            f"clé {key_index + 1}"
                        )

                        # Passe à la clé suivante.
                        break

                    elif r.status_code == 401:

                        print(
                            f"[GROQ] 401 clé "
                            f"{key_index + 1}"
                        )

                        # Cette clé ne fonctionne pas.
                        break

                    elif r.status_code == 413:

                        print(
                            f"[GROQ] 413 Payload Too Large "
                            f"{model}"
                        )

                        try:
                            print(
                                "[GROQ] 413 BODY:",
                                r.text[:3000]
                            )
                        except Exception:
                            pass

                        try:
                            print(
                                "[GROQ] 413 REQUEST JSON SIZE:",
                                len(r.request.body)
                                if r.request and r.request.body
                                else "unknown"
                            )
                        except Exception:
                            pass

                        if is_mm:
                            break

                        time.sleep(1)

                    elif r.status_code in (
                        400,
                        404
                    ):

                        try:
                            error_data = r.json()

                            error_message = (
                                error_data
                                .get("error", {})
                                .get("message", "")
                            )

                        except Exception:
                            error_message = ""

                        print(
                            f"[GROQ] {r.status_code} "
                            f"{model}"
                            +
                            (
                                f" — {error_message}"
                                if error_message
                                else ""
                            )
                        )

                        # Modèle incompatible / invalide :
                        # passe immédiatement au suivant.
                        break

                    else:

                        print(
                            f"[GROQ] HTTP "
                            f"{r.status_code} "
                            f"{model}"
                        )

                        time.sleep(1)

                except requests.exceptions.Timeout:

                    print(
                        f"[GROQ] Timeout "
                        f"{model} "
                        f"t{attempt + 1}"
                    )

                    if attempt == 0:
                        time.sleep(1)

                except requests.exceptions.RequestException as e:

                    print(
                        f"[GROQ] Réseau : {e}"
                    )

                    time.sleep(1)

                    break

                except Exception as e:

                    print(
                        f"[GROQ] Erreur : {e}"
                    )

                    time.sleep(1)

                    break

    return {
        "ok": False,
        "content": (
            "Tous mes serveurs sont surchargés "
            "ou temporairement indisponibles. "
            "Réessaie dans quelques secondes."
        ),
        "model": None,
        "reasoning": None,
    }


# ══════════════════════════════════════════════════════════════════════════════
# RECHERCHE WEB
# ══════════════════════════════════════════════════════════════════════════════

def search_ddg(query):

    try:

        r = requests.get(
            "https://api.duckduckgo.com/"
            f"?q={requests.utils.quote(query)}"
            "&format=json"
            "&no_html=1"
            "&skip_disambig=1",
            timeout=8
        )

        d = r.json()

        results = []

        if d.get("AbstractText"):

            results.append({
                "title": d.get(
                    "Heading",
                    ""
                ),
                "body": d["AbstractText"],
                "href": d.get(
                    "AbstractURL",
                    ""
                ),
                "source": "DuckDuckGo",
            })

        for t in d.get(
            "RelatedTopics",
            []
        ):

            if (
                "Text" in t
                and len(results) < 5
            ):

                results.append({
                    "title": t.get(
                        "Text",
                        ""
                    )[:60],
                    "body": t.get(
                        "Text",
                        ""
                    ),
                    "href": t.get(
                        "FirstURL",
                        ""
                    ),
                    "source": "DuckDuckGo",
                })

        return results

    except Exception:

        return []


def search_wiki(query):

    try:

        r = requests.get(
            "https://fr.wikipedia.org/api/rest_v1/page/summary/"
            + requests.utils.quote(query),
            timeout=8,
            headers={
                "User-Agent": "Lumina/6.1"
            }
        )

        if r.status_code == 200:

            d = r.json()

            if d.get("extract"):

                return [{
                    "title": d.get(
                        "title",
                        "Wikipedia"
                    ),
                    "body": d["extract"][:800],
                    "href": d.get(
                        "content_urls",
                        {}
                    ).get(
                        "desktop",
                        {}
                    ).get(
                        "page",
                        ""
                    ),
                    "source": "Wikipedia",
                }]

    except Exception:
        pass

    return []


def multi_search(query):

    results = search_ddg(query)

    if len(results) < 3:

        results.extend(
            search_wiki(query)
        )

    return results[:6]


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES STATIQUES
# ══════════════════════════════════════════════════════════════════════════════

ALLOWED_STATIC_EXT = {
    ".html", ".js", ".css", ".json", ".png", ".jpg", ".jpeg", ".webp",
    ".svg", ".ico", ".woff2", ".txt", ".webmanifest",
}


@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    """Sert UNIQUEMENT le contenu de www/ (jamais la racine du projet, jamais un fichier caché)."""
    parts = path.split("/")
    ext = os.path.splitext(path)[1].lower()
    if (
        any(p == "" or p.startswith(".") for p in parts)
        or ext not in ALLOWED_STATIC_EXT
        or not os.path.isfile(os.path.join(WEB_DIR, *parts))
    ):
        return jsonify({"error": "Introuvable"}), 404
    return send_from_directory(WEB_DIR, path)


# ══════════════════════════════════════════════════════════════════════════════
# AUTH — SIGNUP
# ══════════════════════════════════════════════════════════════════════════════

@app.route(
    "/auth/signup",
    methods=["POST"]
)
def signup():

    data = request.get_json(
        silent=True
    ) or {}

    email = (
        data.get(
            "email",
            ""
        )
        .strip()
        .lower()
    )

    password = data.get(
        "password",
        ""
    )

    display_name = (
        data.get(
            "display_name"
        )
        or ""
    ).strip()

    if not display_name:
        display_name = (
            email.split("@")[0]
            if email
            else ""
        )

    ip = client_ip()

    if not SIGNUP_LIMITER.allow(ip):
        return jsonify({
            "error": "Trop d'inscriptions depuis cette connexion, réessaie plus tard"
        }), 429

    if len(email) > 254 or len(password) > 256 or len(display_name) > 60:
        return jsonify({"error": "Champs trop longs"}), 400

    if not EMAIL_RE.match(email):

        return jsonify({
            "error": "Adresse email invalide"
        }), 400

    if len(password) < 8:

        return jsonify({
            "error": (
                "Le mot de passe doit faire "
                "au moins 8 caractères"
            )
        }), 400

    db = get_db()

    if db.execute(
        "SELECT id FROM users WHERE email = ?",
        (email,)
    ).fetchone():

        return jsonify({
            "error": (
                "Un compte existe déjà "
                "avec cet email"
            )
        }), 409

    pw_hash = generate_password_hash(
        password
    )

    cur = db.execute(
        """
        INSERT INTO users
        (email, password_hash, display_name, created_at)
        VALUES (?, ?, ?, ?)
        RETURNING id
        """,
        (
            email,
            pw_hash,
            display_name,
            time.time()
        )
    )

    user_id = cur.fetchone()["id"]
    db.execute(
        """
        INSERT INTO user_knowledge
        (user_id, connaissances)
        VALUES (?, '{}')
        """,
        (user_id,)
    )

    token = secrets.token_urlsafe(32)

    db.execute(
        """
        INSERT INTO sessions
        (token, user_id, created_at)
        VALUES (?, ?, ?)
        """,
        (
            token,
            user_id,
            time.time()
        )
    )

    db.commit()

    return jsonify({
        "token": token,
        "user": {
            "id": user_id,
            "email": email,
            "display_name": display_name
        }
    })


# ══════════════════════════════════════════════════════════════════════════════
# AUTH — LOGIN
# ══════════════════════════════════════════════════════════════════════════════

@app.route(
    "/auth/login",
    methods=["POST"]
)
def login():

    data = request.get_json(
        silent=True
    ) or {}

    email = (
        data.get(
            "email",
            ""
        )
        .strip()
        .lower()
    )

    password = data.get(
        "password",
        ""
    )

    ip = client_ip()

    if len(email) > 254 or len(password) > 256:
        return jsonify({"error": "Email ou mot de passe incorrect"}), 401

    if login_blocked(email, ip):

        return jsonify({
            "error": (
                "Trop de tentatives, "
                "réessaie dans quelques minutes"
            )
        }), 429

    db = get_db()

    row = db.execute(
        """
        SELECT id, password_hash, display_name
        FROM users
        WHERE email = ?
        """,
        (email,)
    ).fetchone()

    if (
        not row
        or not check_password_hash(
            row["password_hash"],
            password
        )
    ):

        register_failed_login(email, ip)

        return jsonify({
            "error": (
                "Email ou mot de passe incorrect"
            )
        }), 401

    clear_login_attempts(email, ip)

    purge_expired_sessions(db)
    trim_user_sessions(db, row["id"])

    token = secrets.token_urlsafe(32)

    db.execute(
        """
        INSERT INTO sessions
        (token, user_id, created_at)
        VALUES (?, ?, ?)
        """,
        (
            token,
            row["id"],
            time.time()
        )
    )

    db.commit()

    return jsonify({
        "token": token,
        "user": {
            "id": row["id"],
            "email": email,
            "display_name": row["display_name"]
        }
    })


# ══════════════════════════════════════════════════════════════════════════════
# AUTH — LOGOUT
# ══════════════════════════════════════════════════════════════════════════════

@app.route(
    "/auth/logout",
    methods=["POST"]
)
@require_auth
def logout():

    auth_header = request.headers.get(
        "Authorization",
        ""
    )

    token = (
        auth_header[7:]
        if auth_header.startswith("Bearer ")
        else None
    )

    db = get_db()

    db.execute(
        "DELETE FROM sessions WHERE token = ?",
        (token,)
    )

    db.commit()

    return jsonify({
        "status": "ok"
    })


# ══════════════════════════════════════════════════════════════════════════════
# AUTH — ME
# ══════════════════════════════════════════════════════════════════════════════

@app.route(
    "/auth/me",
    methods=["GET"]
)
@require_auth
def me():

    db = get_db()

    row = db.execute(
        """
        SELECT id, email, display_name
        FROM users
        WHERE id = ?
        """,
        (request.user_id,)
    ).fetchone()

    if not row:

        return jsonify({
            "error": "Utilisateur introuvable"
        }), 404

    return jsonify({
        "user": {
            "id": row["id"],
            "email": row["email"],
            "display_name": row["display_name"]
        }
    })


# ══════════════════════════════════════════════════════════════════════════════
# MODÈLES
# ══════════════════════════════════════════════════════════════════════════════

@app.route(
    "/models",
    methods=["GET"]
)
def get_models():

    models = []

    for model_id, label in MODELS_DISPLAY.items():

        models.append({
            "id": model_id,
            "label": label,
            "default": model_id == DEFAULT_MODEL,
            "prime": model_id == PRIME_MODEL,
            "flash": model_id == FLASH_MODEL,
            "legacy": model_id == LEGACY_MODEL,
        })

    return jsonify({
        "default": DEFAULT_MODEL,
        "prime": PRIME_MODEL,
        "flash": FLASH_MODEL,
        "models": models
    })


# ══════════════════════════════════════════════════════════════════════════════
# CHAT
# ══════════════════════════════════════════════════════════════════════════════

@app.route(
    "/chat",
    methods=["POST"]
)
@require_auth
def chat():

    data = request.get_json(
        silent=True
    ) or {}

    user_msg = (
        data.get(
            "message",
            ""
        )
        .strip()
    )

    conv_id = (
        data.get(
            "conv_id"
        )
        or "default"
    ).strip() or "default"

    use_web = bool(
        data.get(
            "use_web"
        )
    )

    # Image éventuellement envoyée par le frontend.
    image_data = data.get("image")
    has_image = bool(
        image_data
        and isinstance(image_data, str)
        and image_data.startswith("data:image/")
    )

    if not user_msg:

        return jsonify({
            "error": "Message vide"
        }), 400

    # ──────────────────────────────────────────────────────────────────────
    # DÉTECTION D'INTENTION
    # ──────────────────────────────────────────────────────────────────────

    # ── Validations V7 (taille, image, identifiant de conversation) ──────
    if len(user_msg) > MAX_MESSAGE_CHARS:
        return jsonify({
            "error": f"Message trop long (maximum {MAX_MESSAGE_CHARS} caractères)"
        }), 413

    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", conv_id):
        return jsonify({"error": "Identifiant de conversation invalide"}), 400

    if image_data:
        if not (isinstance(image_data, str) and IMAGE_PREFIX_RE.match(image_data)):
            return jsonify({"error": "Image invalide (JPEG, PNG ou WebP attendu)"}), 400
        if len(image_data) > MAX_IMAGE_B64:
            return jsonify({"error": "Image trop volumineuse"}), 413
        has_image = True

    regen = bool(data.get("regen"))

    intent = detect_intent(
        user_msg
    )

    # ──────────────────────────────────────────────────────────────────────
    # MODÈLE DEMANDÉ PAR LE FRONTEND
    # ──────────────────────────────────────────────────────────────────────

    requested_model = data.get(
        "model"
    )

    # Si aucun modèle n'est envoyé :
    # DEFAULT_MODEL = FLASH_MODEL
    if not requested_model:

        model_req = DEFAULT_MODEL

    else:

        model_req = normalize_model(
            requested_model
        )

    # ──────────────────────────────────────────────────────────────────────
    # ROUTAGE AUTOMATIQUE
    # ──────────────────────────────────────────────────────────────────────

    auto_route = (
        data.get(
            "auto_model"
        )
        or requested_model in (
            None,
            "",
            "auto",
            "default"
        )
    )

    route_reason = "manual"

    if auto_route:

        model_req, route_reason = route_model(
            message=user_msg,
            intent=intent,
            has_image=has_image,
            has_tool=False
        )

    # Une image doit impérativement utiliser Prime (seul modèle vision).
    if has_image:
        model_req = PRIME_MODEL
        route_reason = "vision"
        img_len = len(image_data) if image_data else 0
        print(
            f"[VISION] Image reçue, taille base64: {img_len} chars "
            f"(~{img_len * 3 // 4} bytes)"
        )

    # Une recherche web doit utiliser Prime.
    if use_web and intent.get("web"):

        model_req = PRIME_MODEL
        route_reason = "web"

    # ──────────────────────────────────────────────────────────────────────
    # TEMPÉRATURE
    # ──────────────────────────────────────────────────────────────────────

    try:

        temp_req = float(
            data.get(
                "temperature",
                0.75
            )
        )

    except (TypeError, ValueError):

        temp_req = 0.75

    temp_req = max(
        0.0,
        min(
            temp_req,
            1.5
        )
    )

    # ──────────────────────────────────────────────────────────────────────
    # RATE LIMIT
    # ──────────────────────────────────────────────────────────────────────

    if chat_rate_limited(
        request.user_id
    ):

        return jsonify({
            "error": (
                "Trop de messages en peu de temps, "
                "patiente une minute."
            )
        }), 429

    # ──────────────────────────────────────────────────────────────────────
    # MÉMOIRE
    # ──────────────────────────────────────────────────────────────────────

    historique = load_conv_history(
        request.user_id,
        conv_id
    )

    connaissances = load_knowledge(
        request.user_id
    )

    # « Régénérer » : on retire l'échange précédent identique pour ne pas le dupliquer.
    if (
        regen
        and historique
        and historique[-1].get("user") == user_msg
    ):
        historique = historique[:-1]

    # ──────────────────────────────────────────────────────────────────────
    # APPRENTISSAGE AUTOMATIQUE
    # ──────────────────────────────────────────────────────────────────────

    if (
        "apprend que"
        in user_msg.lower()
        and " est "
        in user_msg.lower()
    ):

        try:

            phrase = (
                user_msg.lower()
                .split(
                    "apprend que",
                    1
                )[1]
                .strip()
            )

            sujet, info = phrase.split(
                " est ",
                1
            )

            connaissances[
                sujet.strip()
            ] = info.strip()

            save_knowledge(
                request.user_id,
                connaissances
            )

            return jsonify({
                "reply": (
                    f"Noté — {sujet.strip()} "
                    f"est {info.strip()}."
                ),
                "model": "cache"
            })

        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────────
    # RECHERCHE WEB
    # ──────────────────────────────────────────────────────────────────────

    should_search = (
        use_web
        and intent["web"]
    )

    # ──────────────────────────────────────────────────────────────────────
    # CACHE
    # ──────────────────────────────────────────────────────────────────────

    cache_key = (
        f"{request.user_id}:"
        f"{conv_id}:"
        f"{model_req}:"
        f"{user_msg.lower().strip()}"
    )

    if not should_search and not has_image and not regen:

        cached = cache_get(
            cache_key
        )

        if cached:

            return jsonify({
                "reply": cached,
                "model": "cache",
                "route": route_reason
            })

    # ──────────────────────────────────────────────────────────────────────
    # CONSTRUCTION DU PROMPT
    # ──────────────────────────────────────────────────────────────────────

    sources = []

    prompt = build_ctx(
        user_msg,
        historique,
        connaissances
    )

    if should_search:

        results = multi_search(
            user_msg
        )

        if results:

            web_block = "\n\n".join(
                f"[{i + 1}] "
                f"{r['title']} — "
                f"{r['body'][:300]}"
                for i, r in enumerate(results)
            )

            prompt = (
                "Résultats de recherche web "
                "(utilise-les pour répondre, "
                "cite-les par [numéro]) :\n"
                f"{web_block}\n\n"
                f"{prompt}"
            )

            sources = [
                {
                    "title": r["title"],
                    "href": r["href"],
                    "source": r["source"]
                }
                for r in results
            ]

    # ──────────────────────────────────────────────────────────────────────
    # MESSAGES
    # ──────────────────────────────────────────────────────────────────────

    # ──────────────────────────────────────────────────────────────────────
    # MESSAGE MULTIMODAL
    # ──────────────────────────────────────────────────────────────────────

    if has_image:

        messages = [

            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },

            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data
                        }
                    }
                ]
            }
        ]

    else:

        messages = [

            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },

            {
                "role": "user",
                "content": prompt
            }
        ]

    # ──────────────────────────────────────────────────────────────────────
    # APPEL GROQ
    # ──────────────────────────────────────────────────────────────────────

    result = call_groq(
        messages,
        preferred_model=model_req,
        temperature=temp_req,
        reason_type=route_reason
    )

    reponse = result["content"]

    # ──────────────────────────────────────────────────────────────────────
    # SUCCÈS
    # ──────────────────────────────────────────────────────────────────────

    if result["ok"]:

        if not should_search and not has_image:

            cache_set(
                cache_key,
                reponse
            )

        historique.append({
            "user": user_msg,
            "assistant": reponse
        })

        if len(historique) > 60:

            historique = historique[-60:]

        save_conv_history(
            request.user_id,
            conv_id,
            historique
        )

    # ──────────────────────────────────────────────────────────────────────
    # RÉPONSE
    # ──────────────────────────────────────────────────────────────────────

    return jsonify({

        "reply": reponse,

        "model": result.get(
            "model",
            "unknown"
        ),

        "requested_model": model_req,

        "default_model": DEFAULT_MODEL,

        "route": route_reason,

        "reasoning": result.get(
            "reasoning"
        ),

        "sources": sources,

        "ok": result["ok"]
    }), (200 if result["ok"] else 503)


# ══════════════════════════════════════════════════════════════════════════════
# MÉMOIRE CONVERSATION
# ══════════════════════════════════════════════════════════════════════════════

@app.route(
    "/conv_memory/<conv_id>",
    methods=["DELETE"]
)
@require_auth
def conv_memory(conv_id):

    delete_conv_history(
        request.user_id,
        conv_id
    )

    return jsonify({
        "status": "ok"
    })


# ══════════════════════════════════════════════════════════════════════════════
# RECHERCHE WEB DIRECTE
# ══════════════════════════════════════════════════════════════════════════════

@app.route(
    "/search_web",
    methods=["POST"]
)
@require_auth
def search_web():

    if not SEARCH_LIMITER.allow(request.user_id):
        return jsonify({"error": "Trop de recherches, patiente une minute."}), 429


    data = request.get_json(
        silent=True
    ) or {}

    query = (
        data.get(
            "query",
            ""
        )
        .strip()
    )

    if not query:

        return jsonify({
            "error": "Requête vide"
        }), 400

    return jsonify({
        "results": multi_search(query)
    })


# ══════════════════════════════════════════════════════════════════════════════
# MÉMOIRE UTILISATEUR
# ══════════════════════════════════════════════════════════════════════════════

@app.route(
    "/get_memory",
    methods=["GET"]
)
@require_auth
def get_memory():

    return jsonify({
        "connaissances": load_knowledge(
            request.user_id
        )
    })


@app.route(
    "/clear_memory",
    methods=["POST"]
)
@require_auth
def clear_memory():

    save_knowledge(
        request.user_id,
        {}
    )

    return jsonify({
        "status": "ok"
    })


# ══════════════════════════════════════════════════════════════════════════════
# TEST DES MODÈLES GROQ
# ══════════════════════════════════════════════════════════════════════════════

@app.route(
    "/groq_models",
    methods=["GET"]
)
def groq_models():

    if not is_admin():
        return jsonify({"error": "Introuvable"}), 404

    if not GROQ_KEYS:

        return jsonify({
            "ok": False,
            "error": "Aucune clé Groq"
        }), 503

    try:

        r = requests.get(
            GROQ_MODELS_URL,
            headers={
                "Authorization":
                    f"Bearer {GROQ_KEYS[0]}",
                "Content-Type":
                    "application/json"
            },
            timeout=8
        )

        if r.status_code != 200:

            return jsonify({
                "ok": False,
                "status": r.status_code
            }), r.status_code

        data = r.json()

        ids = [
            item.get("id")
            for item in data.get(
                "data",
                []
            )
        ]

        return jsonify({

            "ok": True,

            "default_model":
                DEFAULT_MODEL,

            "flash_model":
                FLASH_MODEL,

            "prime_model":
                PRIME_MODEL,

            "flash_available":
                FLASH_MODEL in ids,

            "prime_available":
                PRIME_MODEL in ids,

            "legacy_available":
                LEGACY_MODEL in ids,

            "models":
                ids
        })

    except Exception as e:

        return jsonify({
            "ok": False,
            "error": str(e)
        }), 503


# ══════════════════════════════════════════════════════════════════════════════
# STATUS
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# V7 — UTILITAIRES, EN-TÊTES, ERREURS
# ══════════════════════════════════════════════════════════════════════════════

IMAGE_PREFIX_RE = re.compile(r"^data:image/(jpeg|jpg|png|webp);base64,")


def is_admin():
    if not ADMIN_TOKEN:
        return False
    return hmac.compare_digest(
        request.headers.get("X-Admin-Token", ""),
        ADMIN_TOKEN
    )


def clean_conv_id(value):
    value = (value or "default")
    value = str(value).strip() or "default"
    return value if re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", value) else None


@app.before_request
def guard_schema():
    """Si la base dormait au démarrage (Neon), on retente ici au lieu de planter."""
    if request.method == "OPTIONS":
        return None
    if request.endpoint in ("index", "static_files", "healthz"):
        return None
    if not _schema_ready and not ensure_schema():
        return jsonify({
            "error": "Base de données indisponible, réessaie dans un instant."
        }), 503
    return None


@app.after_request
def security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault(
        "Permissions-Policy",
        "camera=(self), microphone=(self), geolocation=()"
    )
    p = request.path
    if p in ("/", "/index.html", "/sw.js", "/manifest.json"):
        resp.headers["Cache-Control"] = "no-cache"
    elif p.startswith(("/auth", "/chat", "/live", "/feedback", "/get_memory", "/conv_memory")):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.errorhandler(413)
def too_large(_e):
    return jsonify({"error": "Requête trop volumineuse"}), 413


@app.errorhandler(404)
def not_found(_e):
    return jsonify({"error": "Introuvable"}), 404


@app.errorhandler(405)
def bad_method(_e):
    return jsonify({"error": "Méthode non autorisée"}), 405


# ══════════════════════════════════════════════════════════════════════════════
# V7 — SANTÉ / STATUS
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/healthz", methods=["GET"])
def healthz():
    """Sonde pour Render : vérifie que la base répond. Ne révèle aucune configuration."""
    ok = False
    try:
        if ensure_schema():
            get_db().execute("SELECT 1").fetchone()
            ok = True
    except Exception as e:
        print(f"[HEALTH] {_safe_err(e)}")
    return jsonify({"ok": ok}), (200 if ok else 503)


@app.route("/status", methods=["GET"])
def status():
    out = {"status": "online", "version": APP_VERSION}
    if is_admin():
        db = get_db()
        out.update({
            "default_model": DEFAULT_MODEL,
            "flash_model": FLASH_MODEL,
            "prime_model": PRIME_MODEL,
            "vision_models": VISION_MODEL_LIST,
            "stt_model": GROQ_STT_MODEL,
            "keys": len(GROQ_KEYS),
            "cache": len(cache),
            "users": db.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"],
            "database": "postgresql" if DATABASE_URL else "sqlite",
        })
    return jsonify(out)


# ══════════════════════════════════════════════════════════════════════════════
# V7 — FEEDBACK & SUPPRESSION DE COMPTE
# ══════════════════════════════════════════════════════════════════════════════

FEEDBACK_KINDS = {"like", "dislike", "copy", "share", "bug_report"}


@app.route("/feedback", methods=["POST"])
@require_auth
def feedback():
    data = request.get_json(silent=True) or {}
    kind = str(data.get("type", "")).strip()

    if kind not in FEEDBACK_KINDS:
        return jsonify({"error": "Type de retour inconnu"}), 400

    if not FEEDBACK_LIMITER.allow(request.user_id):
        return jsonify({"error": "Trop de retours en peu de temps"}), 429

    text = str(data.get("text") or "")[:2000]
    conv_id = clean_conv_id(data.get("conv_id"))
    message_id = str(data.get("message_id") or "")[:80]

    if kind == "bug_report" and not text.strip():
        return jsonify({"error": "Décris le problème"}), 400

    db = get_db()
    db.execute(
        """
        INSERT INTO feedback (user_id, kind, conv_id, message_id, text, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (request.user_id, kind, conv_id, message_id or None, text or None, time.time())
    )
    db.commit()
    return jsonify({"status": "ok"})


@app.route("/auth/account", methods=["DELETE"])
@require_auth
def delete_account():
    """Suppression définitive du compte et de toutes ses données (cascade SQL)."""
    data = request.get_json(silent=True) or {}
    password = str(data.get("password", ""))
    ip = client_ip()
    key = f"acct:{request.user_id}|{ip}"

    if LOGIN_LIMITER.blocked(key):
        return jsonify({"error": "Trop de tentatives, réessaie dans quelques minutes"}), 429

    db = get_db()
    row = db.execute(
        "SELECT password_hash FROM users WHERE id = ?",
        (request.user_id,)
    ).fetchone()

    if not row or len(password) > 256 or not check_password_hash(row["password_hash"], password):
        LOGIN_LIMITER.add(key)
        return jsonify({"error": "Mot de passe incorrect"}), 401

    uid = request.user_id
    # Suppressions explicites (en plus des ON DELETE CASCADE) pour ne dépendre d'aucun réglage.
    for table in ("feedback", "conv_memories", "user_knowledge", "sessions"):
        db.execute(f"DELETE FROM {table} WHERE user_id = ?", (uid,))
    db.execute("DELETE FROM users WHERE id = ?", (uid,))
    db.commit()
    return jsonify({"status": "deleted"})


# ══════════════════════════════════════════════════════════════════════════════
# V7 — MODE LIVE (vision caméra + voix)
# ══════════════════════════════════════════════════════════════════════════════

LIVE_OBSERVE_PROMPT = """Tu es Lumina en mode Live. À travers la caméra de l'utilisateur, tu vois ce qu'il fait en ce moment et tu l'accompagnes à voix haute, comme un ami attentif.

Règles :
- Français, 1 ou 2 phrases courtes et naturelles, à l'oral. Pas de markdown, pas de liste, pas d'emoji.
- Ne commente que ce qui est nouveau, utile ou intéressant par rapport à tes derniers commentaires. Ne te répète jamais.
- S'il accomplit une tâche (cuisine, écriture, bricolage, exercice, lecture, etc.), aide-le : un conseil, une correction, un encouragement ou une question utile.
- Si rien ne mérite d'être dit maintenant, réponds exactement : [SILENCE]
- Ne dis jamais « je vois une image de ». Tu regardes en direct.
- N'identifie jamais une personne à son visage. Ne présente jamais une émotion, une santé ou une origine comme un fait.
- Si la situation semble dangereuse, dis-le brièvement et calmement."""

LIVE_TURN_PROMPT = """Tu es Lumina en conversation vocale en direct. L'utilisateur te parle ; tu peux voir ce que sa caméra montre (image jointe, si elle est présente).
Réponds en 1 à 3 phrases orales et naturelles, en français, sans markdown ni emoji. Si la question porte sur ce qu'il fait ou montre, appuie-toi sur l'image. Si tu ne vois pas assez bien, dis-le simplement. N'identifie jamais une personne à son visage."""

LIVE_LEVELS = {
    "discret": "Sois très économe : ne parle que si c'est vraiment utile ou important.",
    "normal": "Parle quand tu as quelque chose d'utile ou de pertinent à ajouter.",
    "bavard": "Tu peux être plus réactif et commenter plus souvent, toujours brièvement.",
}

_STT_NOISE = (
    "sous-titrage", "sous-titres", "amara.org", "merci d'avoir regardé",
    "merci d’avoir regardé", "thanks for watching", "abonnez-vous",
)


def is_stt_noise(text):
    t = (text or "").strip().lower()
    if len(t) < 2:
        return True
    return any(n in t for n in _STT_NOISE)


def clean_spoken(text, limit=450):
    t = re.sub(r"<think>.*?</think>", " ", text or "", flags=re.S)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"[*_`#>~]+", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > limit:
        cut = t[:limit]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        t = cut[:end + 1] if end > 80 else cut.rstrip() + "…"
    return t


@app.route("/live/stt", methods=["POST"])
@require_auth
def live_stt():
    """Transcription d'un segment audio (Whisper via Groq). Marche aussi dans une WebView Android."""
    if not GROQ_KEYS:
        return jsonify({"ok": False, "error": "Transcription indisponible"}), 503

    f = request.files.get("audio")
    if not f:
        return jsonify({"error": "Audio manquant"}), 400

    blob = f.read(MAX_AUDIO_BYTES + 1)
    if len(blob) > MAX_AUDIO_BYTES:
        return jsonify({"error": "Audio trop volumineux"}), 413
    if len(blob) < 1500:
        return jsonify({"ok": True, "text": ""})

    mime = (f.mimetype or "audio/webm").split(";")[0].lower()
    ext = {
        "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a",
        "audio/mpeg": "mp3", "audio/wav": "wav", "audio/x-wav": "wav",
    }.get(mime)
    if not ext:
        return jsonify({"error": "Format audio non pris en charge"}), 415

    if not STT_LIMITER.allow(request.user_id):
        return jsonify({"error": "Trop de requêtes vocales, patiente un instant"}), 429

    lang = (request.form.get("lang") or "fr").lower()
    if not re.fullmatch(r"[a-z]{2,3}", lang):
        lang = "fr"

    for api_key in GROQ_KEYS:
        try:
            r = requests.post(
                GROQ_STT_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (f"audio.{ext}", blob, mime)},
                data={
                    "model": GROQ_STT_MODEL,
                    "language": lang,
                    "response_format": "json",
                    "temperature": "0",
                },
                timeout=25,
            )
        except requests.exceptions.RequestException as e:
            print(f"[STT] réseau : {type(e).__name__}")
            continue

        if r.status_code == 200:
            try:
                text = (r.json().get("text") or "").strip()
            except ValueError:
                text = ""
            return jsonify({"ok": True, "text": "" if is_stt_noise(text) else text})

        print(f"[STT] HTTP {r.status_code}")
        if r.status_code in (401, 429):
            continue
        break

    return jsonify({"ok": False, "error": "Transcription indisponible"}), 503


@app.route("/live/respond", methods=["POST"])
@require_auth
def live_respond():
    """
    kind="observe" : l'IA regarde l'image et décide seule de parler ou non.
    kind="turn"    : l'utilisateur a parlé ; l'IA répond (avec l'image courante si fournie).
    Les images ne sont jamais enregistrées côté serveur.
    """
    data = request.get_json(silent=True) or {}
    kind = data.get("kind")

    if kind not in ("observe", "turn"):
        return jsonify({"error": "kind doit valoir observe ou turn"}), 400

    conv_id = clean_conv_id(data.get("conv_id"))
    if conv_id is None:
        return jsonify({"error": "Identifiant de conversation invalide"}), 400

    image = data.get("image")
    has_image = False
    if image:
        if not (isinstance(image, str) and IMAGE_PREFIX_RE.match(image)):
            return jsonify({"error": "Image invalide"}), 400
        if len(image) > MAX_LIVE_IMAGE_B64:
            return jsonify({"error": "Image trop volumineuse"}), 413
        has_image = True

    if kind == "observe" and not has_image:
        return jsonify({"error": "Image requise"}), 400

    text = str(data.get("text") or "").strip()
    if kind == "turn":
        if not text:
            return jsonify({"error": "Texte vide"}), 400
        if len(text) > 1500:
            return jsonify({"error": "Texte trop long"}), 413

    if not LIVE_LIMITER.allow(request.user_id):
        return jsonify({"error": "Trop de requêtes Live, patiente un instant"}), 429

    level = data.get("level") if data.get("level") in LIVE_LEVELS else "normal"
    camera = "arrière" if data.get("camera") == "environment" else "frontale"
    recent = data.get("recent") if isinstance(data.get("recent"), list) else []
    recent = [str(x)[:300] for x in recent[-4:]]

    connaissances = load_knowledge(request.user_id)
    know = ""
    if connaissances:
        know = "\n\nCe que tu sais sur l'utilisateur :\n" + "\n".join(
            f"- {k}: {v}" for k, v in list(connaissances.items())[:20]
        )

    if kind == "observe":
        system = f"{LIVE_OBSERVE_PROMPT}\n\n{LIVE_LEVELS[level]}{know}"
        already = (
            "Tes derniers commentaires (ne les répète pas) :\n- " + "\n- ".join(recent)
            if recent else "Tu n'as encore rien dit."
        )
        user_content = [
            {"type": "text", "text": f"Caméra {camera}. {already}\nQue vois-tu de nouveau ? Réponds par [SILENCE] si rien ne mérite d'être dit."},
            {"type": "image_url", "image_url": {"url": image}},
        ]
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]
        historique = None
    else:
        historique = load_conv_history(request.user_id, conv_id)
        messages = [{"role": "system", "content": LIVE_TURN_PROMPT + know}]
        for entry in historique[-6:]:
            messages.append({"role": "user", "content": str(entry.get("user", ""))[:1500]})
            messages.append({"role": "assistant", "content": str(entry.get("assistant", ""))[:1500]})
        if has_image:
            messages.append({"role": "user", "content": [
                {"type": "text", "text": f"(Caméra {camera}) {text}"},
                {"type": "image_url", "image_url": {"url": image}},
            ]})
        else:
            messages.append({"role": "user", "content": text})

    result = call_groq(
        messages,
        preferred_model=(VISION_MODEL_LIST[0] if has_image else FLASH_MODEL),
        temperature=0.6,
        reason_type="live",
        max_tokens=300,
        deadline_s=20,
    )

    if not result["ok"]:
        return jsonify({
            "ok": False,
            "speak": False,
            "error": "Lumina n'arrive pas à répondre pour le moment.",
        }), 503

    spoken = clean_spoken(result["content"])

    if kind == "observe":
        silent = (not spoken) or spoken.upper().startswith("[SILENCE") or spoken.upper().startswith("SILENCE")
        return jsonify({
            "ok": True,
            "speak": not silent,
            "text": "" if silent else spoken,
            "model": result.get("model"),
        })

    if not spoken:
        spoken = "Je n'ai pas bien compris, tu peux répéter ?"

    historique.append({"user": "[Live] " + text, "assistant": spoken})
    save_conv_history(request.user_id, conv_id, historique[-60:])

    return jsonify({
        "ok": True,
        "reply": spoken,
        "model": result.get("model"),
    })


# ══════════════════════════════════════════════════════════════════════════════
# DÉMARRAGE
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print(
        "\n"
        + "=" * 64
    )

    print(
        "  🌟  Lumina Server v7.0"
    )

    print(
        "  Développé par Issa Amakendé Abdoulaye Koné"
    )

    print(
        f"  Port           : 5005"
    )

    print(
        f"  Clés Groq      : {len(GROQ_KEYS)}"
    )

    print(
        f"  Flash défaut   : {FLASH_MODEL}"
    )

    print(
        f"  Prime          : {PRIME_MODEL}"
    )

    print(
        f"  Cache          : {CACHE_SIZE} entrées"
    )

    print(
        f"  DB             : {DB_FILE}"
    )

    print(
        "=" * 64
        + "\n"
    )

    app.run(
        host="0.0.0.0",
        port=_env_int("PORT", 5005),
        debug=False,
        threaded=True
    )
