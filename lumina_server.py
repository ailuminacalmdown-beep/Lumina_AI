#!/usr/bin/env python3
"""
Lumina Server v6.1 — Interface Claude-style
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
VISION_MODELS = {
    PRIME_MODEL,
}


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

app = Flask(__name__, static_folder=BASE_DIR)

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

DB_FILE = os.path.join(BASE_DIR, "lumina.db")

EMAIL_RE = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
)

class DBConnection:

    def __init__(self, conn, postgres=False):
        self.conn = conn
        self.postgres = postgres

    def execute(self, query, params=()):
        if self.postgres:
            query = query.replace("?", "%s")
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
                row_factory=dict_row
            )

            g.db = DBConnection(
                conn,
                postgres=True
            )

        else:
            conn = sqlite3.connect(
                DB_FILE,
                timeout=10
            )

            conn.row_factory = sqlite3.Row

            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 5000")

            g.db = DBConnection(
                conn,
                postgres=False
            )

@app.teardown_appcontext
def close_db(exception=None):

    db = g.pop("db", None)

    if db is not None:
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

init_db()


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

LOGIN_MAX_ATTEMPTS = 8
LOGIN_WINDOW = 300

login_lock = threading.Lock()
login_attempts = {}


def login_blocked(email):

    now = time.time()

    with login_lock:

        attempts = [
            t
            for t in login_attempts.get(email, [])
            if now - t < LOGIN_WINDOW
        ]

        login_attempts[email] = attempts

        return len(attempts) >= LOGIN_MAX_ATTEMPTS


def register_failed_login(email):

    with login_lock:

        login_attempts.setdefault(
            email,
            []
        ).append(time.time())


def clear_login_attempts(email):

    with login_lock:
        login_attempts.pop(email, None)


# ══════════════════════════════════════════════════════════════════════════════
# RATE LIMIT CHAT
# ══════════════════════════════════════════════════════════════════════════════

CHAT_MAX_PER_MIN = 20

chat_lock = threading.Lock()
chat_calls = {}


def chat_rate_limited(user_id):

    now = time.time()

    with chat_lock:

        calls = [
            t
            for t in chat_calls.get(user_id, [])
            if now - t < 60
        ]

        if len(calls) >= CHAT_MAX_PER_MIN:

            chat_calls[user_id] = calls

            return True

        calls.append(now)

        chat_calls[user_id] = calls

        return False


# ══════════════════════════════════════════════════════════════════════════════
# AUTH DECORATOR
# ══════════════════════════════════════════════════════════════════════════════

def require_auth(f):

    @wraps(f)
    def wrapper(*args, **kwargs):

        auth_header = request.headers.get(
            "Authorization",
            ""
        )

        token = (
            auth_header[7:]
            if auth_header.startswith("Bearer ")
            else None
        )

        if not token:

            return jsonify({
                "error": "Authentification requise"
            }), 401

        db = get_db()

        row = db.execute(
            """
            SELECT user_id
            FROM sessions
            WHERE token = ?
            """,
            (token,)
        ).fetchone()

        if not row:

            return jsonify({
                "error": "Session invalide ou expirée"
            }), 401

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
    reason_type="chat"
):

    preferred_model = normalize_model(
        preferred_model
    )

    is_mm = is_multimodal(messages)

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

        settings = reasoning_settings(
            model,
            reason_type
        )

        for key_index, api_key in enumerate(GROQ_KEYS):

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 4096,
            }

            payload.update(settings)

            for attempt in range(2):

                try:

                    r = requests.post(
                        GROQ_URL,
                        headers=headers,
                        json=payload,
                        timeout=30
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

@app.route("/")
def index():

    return send_from_directory(
        BASE_DIR,
        "index.html"
    )


@app.route("/<path:path>")
def static_files(path):

    return send_from_directory(
        BASE_DIR,
        path
    )


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

    if login_blocked(email):

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

        register_failed_login(email)

        return jsonify({
            "error": (
                "Email ou mot de passe incorrect"
            )
        }), 401

    clear_login_attempts(email)

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

    if not should_search:

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

        if not should_search:

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
    })


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
def search_web():

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

@app.route(
    "/status",
    methods=["GET"]
)
def status():

    db = get_db()

    nb_users = db.execute(
        """
        SELECT COUNT(*) AS n
        FROM users
        """
    ).fetchone()["n"]

    return jsonify({

        "status": "online",

        "version": "6.1",

        "default_model":
            DEFAULT_MODEL,

        "flash_model":
            FLASH_MODEL,

        "prime_model":
            PRIME_MODEL,

        "models":
            GROQ_MODELS_CASCADE,

        "keys":
            len(GROQ_KEYS),

        "cache":
            len(cache),

        "cache_size":
            CACHE_SIZE,

        "users":
            nb_users,

        "chat_limit_per_minute":
            CHAT_MAX_PER_MIN,

        "api":
            GROQ_URL
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
        "  🌟  Lumina Server v6.1 — Interface Claude-style"
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
        port=5005,
        debug=False,
        threaded=True
    )
