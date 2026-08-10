#!/usr/bin/env python3
"""
Lumina Server v6.0 — Interface Claude-style
Développé par Issa Amakendé Abdoulaye Koné
"""
from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import requests, json, time, os, threading, sqlite3, secrets, re
from collections import OrderedDict

# ── CLÉS API ────────────────────────────────────────────────────────────────
GROQ_KEYS = [k.strip() for k in os.environ.get("GROQ_API_KEYS", "").split(",") if k.strip()]

if not GROQ_KEYS:
    print("\n⚠️  Aucune clé Groq trouvée dans l'environnement.")
    print("   Défini GROQ_API_KEYS avant de lancer le serveur.\n")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# ── MODÈLES ─────────────────────────────────────────────────────────────────
GROQ_MODELS_CASCADE = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
]

MODELS_DISPLAY = {
    "openai/gpt-oss-120b": "Lumina Prime (puissant)",
    "openai/gpt-oss-20b":  "Lumina Flash (rapide)",
}
DEFAULT_MODEL = "openai/gpt-oss-120b"

# ── SYSTEM PROMPT V6 — Contrôle strict des outils ──────────────────────────
SYSTEM_PROMPT = """Tu es Lumina, une IA personnelle développée par Issa Amakendé Abdoulaye Koné au Mali. Tu parles en français.

PERSONNALITÉ :
Tu es confiante, directe, parfois légèrement sarcastique avec élégance. Tu as du caractère. Tu n'hésites pas à donner ton avis. Quand tu ne sais pas, tu l'assumes. Tu parles avec chaleur mais jamais de façon robotique.

RÈGLES ABSOLUES DE FORMATAGE :
- Tu réponds EN MARKDOWN. Utilise **gras** pour les points importants, *italique* pour l'emphase, `code` pour les termes techniques.
- Utilise des titres (##) pour structurer tes réponses longues.
- Utilise des listes à puces (-) pour les énumérations.
- Quand tu écris du code, utilise TOUJOURS des blocs markdown avec le langage : ```python ... ``` ou ```html ... ```
- Ne répète PAS la question de l'utilisateur.
- Ne commence JAMAIS par "Bien sûr", "Certainement", "Absolument".
- Vas droit au but. Sois concise mais complète.

RÈGLES D'UTILISATION DES OUTILS (TRÈS IMPORTANT) :
Tu as accès à des outils (recherche web, génération d'image, etc.).
- Tu ne dois JAMAIS utiliser un outil sans que l'utilisateur ne le demande EXPLICITEMENT.
- Si l'utilisateur demande une information factuelle récente ou dit "cherche", "recherche", "trouve", "quelle est l'actualité" → tu peux utiliser la recherche web.
- Si l'utilisateur demande explicitement une image ou dit "génère", "dessine", "crée une image" → tu peux suggérer la génération d'image.
- Si l'utilisateur ne demande RIEN de spécifique → réponds normalement SANS utiliser aucun outil.
- Ne propose jamais un outil de toi-même sauf demande explicite.

RÈGLES DE RÉFLEXION :
- Quand tu réfléchis à une réponse complexe, montre ton raisonnement de façon claire et structurée.
- Utilise des étapes numérotées dans ta réflexion si pertinent."""

# ── FLASK ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=BASE_DIR)
_cors_env = os.environ.get("CORS_ORIGINS", "*").strip()
CORS_ALLOWED = "*" if _cors_env == "*" else [o.strip() for o in _cors_env.split(",") if o.strip()]
CORS(app, resources={r"/*": {"origins": CORS_ALLOWED}})

# ── CACHE ────────────────────────────────────────────────────────────────────
cache = OrderedDict()
CACHE_SIZE = 200
CACHE_TTL = 3600
cache_lock = threading.Lock()

def cache_get(key):
    with cache_lock:
        e = cache.get(key)
        if e and time.time() - e["ts"] < CACHE_TTL:
            cache.move_to_end(key)
            return e["data"]
        elif e:
            del cache[key]
    return None

def cache_set(key, data):
    with cache_lock:
        if len(cache) >= CACHE_SIZE:
            cache.popitem(last=False)
        cache[key] = {"data": data, "ts": time.time()}

# ── BASE DE DONNÉES ─────────────────────────────────────────────────────────
DB_FILE = os.path.join(os.path.dirname(__file__), "lumina.db")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_FILE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")
    return g.db

@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
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
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS user_knowledge (
            user_id INTEGER PRIMARY KEY,
            connaissances TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS conv_memories (
            user_id INTEGER NOT NULL,
            conv_id TEXT NOT NULL,
            historique TEXT NOT NULL DEFAULT '[]',
            updated_at REAL NOT NULL,
            PRIMARY KEY (user_id, conv_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
    """)
    conn.commit()
    conn.close()

init_db()

# ── MÉMOIRE ─────────────────────────────────────────────────────────────────
def load_knowledge(user_id):
    db = get_db()
    row = db.execute("SELECT connaissances FROM user_knowledge WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        db.execute("INSERT INTO user_knowledge (user_id, connaissances) VALUES (?, '{}')", (user_id,))
        db.commit()
        return {}
    try:
        return json.loads(row["connaissances"])
    except:
        return {}

def save_knowledge(user_id, connaissances):
    db = get_db()
    db.execute("UPDATE user_knowledge SET connaissances = ? WHERE user_id = ?",
               (json.dumps(connaissances, ensure_ascii=False), user_id))
    db.commit()

def load_conv_history(user_id, conv_id):
    db = get_db()
    row = db.execute("SELECT historique FROM conv_memories WHERE user_id = ? AND conv_id = ?",
                      (user_id, conv_id)).fetchone()
    if not row:
        return []
    try:
        return json.loads(row["historique"])
    except:
        return []

def save_conv_history(user_id, conv_id, historique):
    db = get_db()
    db.execute(
        "INSERT INTO conv_memories (user_id, conv_id, historique, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id, conv_id) DO UPDATE SET historique=excluded.historique, updated_at=excluded.updated_at",
        (user_id, conv_id, json.dumps(historique, ensure_ascii=False), time.time())
    )
    db.commit()

def delete_conv_history(user_id, conv_id):
    db = get_db()
    db.execute("DELETE FROM conv_memories WHERE user_id = ? AND conv_id = ?", (user_id, conv_id))
    db.commit()

# ── AUTH ─────────────────────────────────────────────────────────────────────
LOGIN_MAX_ATTEMPTS = 8
LOGIN_WINDOW = 300
login_lock = threading.Lock()
login_attempts = {}

def login_blocked(email):
    now = time.time()
    with login_lock:
        attempts = [t for t in login_attempts.get(email, []) if now - t < LOGIN_WINDOW]
        login_attempts[email] = attempts
        return len(attempts) >= LOGIN_MAX_ATTEMPTS

def register_failed_login(email):
    with login_lock:
        login_attempts.setdefault(email, []).append(time.time())

def clear_login_attempts(email):
    with login_lock:
        login_attempts.pop(email, None)

CHAT_MAX_PER_MIN = 20
chat_lock = threading.Lock()
chat_calls = {}

def chat_rate_limited(user_id):
    now = time.time()
    with chat_lock:
        calls = [t for t in chat_calls.get(user_id, []) if now - t < 60]
        if len(calls) >= CHAT_MAX_PER_MIN:
            chat_calls[user_id] = calls
            return True
        calls.append(now)
        chat_calls[user_id] = calls
        return False

def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token = auth_header[7:] if auth_header.startswith("Bearer ") else None
        if not token:
            return jsonify({"error": "Authentification requise"}), 401
        db = get_db()
        row = db.execute("SELECT user_id FROM sessions WHERE token = ?", (token,)).fetchone()
        if not row:
            return jsonify({"error": "Session invalide ou expirée"}), 401
        request.user_id = row["user_id"]
        return f(*args, **kwargs)
    return wrapper

CTX_MAX_CHARS = 6000

def build_ctx(q, historique, connaissances):
    turns = [f"Utilisateur: {e['user']}\nLumina: {e['assistant']}" for e in historique[-10:]]
    kept, total = [], 0
    for turn in reversed(turns):
        total += len(turn)
        if total > CTX_MAX_CHARS:
            break
        kept.append(turn)
    kept.reverse()
    ctx = "\n".join(kept)
    if connaissances:
        ctx += "\n\nCe que tu sais sur cet utilisateur :\n" + "\n".join(f"- {k}: {v}" for k, v in connaissances.items())
    return f"{ctx}\n\nQuestion: {q}" if ctx else q

# ── DÉTECTION D'INTENTION POUR LES OUTILS ───────────────────────────────────
# Détermine si l'utilisateur demande EXPLICITEMENT un outil
WEB_KEYWORDS = [
    "cherche", "recherche", "rechercher", "trouve", "trouver",
    "actualité", "actualites", "news", "dernières nouvelles",
    "quelle est la météo", "météo", "meteo",
    "quelle heure est-il", "date du jour",
    "qui est", "qu'est-ce que", "définition de",
    "prix de", "cours de", "bourse",
    "résultat", "score", "match", "élection"
]

IMG_KEYWORDS = [
    "génère", "genere", "dessine", "crée une image", "crée une photo",
    "génère une image", "génère une photo", "image de", "photo de",
    "fais une image", "fais un dessin"
]

def detect_intent(message):
    msg_lower = message.lower()
    intent = {"web": False, "image": False, "graph": False}

    # Web search
    for kw in WEB_KEYWORDS:
        if kw in msg_lower:
            intent["web"] = True
            break

    # Image generation
    for kw in IMG_KEYWORDS:
        if kw in msg_lower:
            intent["image"] = True
            break

    # Graph (math)
    if re.search(r'^(y|f\(x\)|f)\s*=\s*(.+)', msg_lower):
        intent["graph"] = True

    return intent

# ── APPEL GROQ ───────────────────────────────────────────────────────────────
def call_groq(messages, preferred_model=DEFAULT_MODEL, temperature=0.75):
    models_to_try = [preferred_model] + [m for m in GROQ_MODELS_CASCADE if m != preferred_model]
    for model in models_to_try:
        for key_index, api_key in enumerate(GROQ_KEYS):
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 2048
            }
            for attempt in range(2):
                try:
                    r = requests.post(GROQ_URL, headers=headers, json=payload, timeout=20)
                    if r.status_code == 200:
                        msg = r.json()["choices"][0]["message"]
                        content = (msg.get("content") or "").strip()
                        reasoning = (msg.get("reasoning") or "").strip() or None
                        print(f"[GROQ] ✅ {model} (clé {key_index + 1})" + (" +raisonnement" if reasoning else ""))
                        return {"ok": True, "content": content, "model": model, "reasoning": reasoning}
                    elif r.status_code == 429:
                        print(f"[GROQ] 429 {model} clé {key_index + 1}")
                        time.sleep(2)
                        break
                    elif r.status_code == 401:
                        print(f"[GROQ] 401 clé {key_index + 1}")
                        break
                    elif r.status_code in (400, 404):
                        print(f"[GROQ] {r.status_code} {model} — modèle décommissionné")
                        break
                    else:
                        print(f"[GROQ] HTTP {r.status_code} {model}")
                        time.sleep(1)
                except requests.exceptions.Timeout:
                    print(f"[GROQ] Timeout {model} t{attempt + 1}")
                    time.sleep(2)
                except Exception as e:
                    print(f"[GROQ] Erreur {e}")
                    time.sleep(1)
    return {
        "ok": False,
        "content": "Tous mes serveurs sont surchargés en ce moment. Réessaie dans quelques secondes.",
        "model": None,
        "reasoning": None
    }

# ── RECHERCHE WEB ──────────────────────────────────────────────────────────
def search_ddg(query):
    try:
        r = requests.get(
            f"https://api.duckduckgo.com/?q={requests.utils.quote(query)}&format=json&no_html=1&skip_disambig=1",
            timeout=8
        )
        d = r.json()
        results = []
        if d.get("AbstractText"):
            results.append({
                "title": d.get("Heading", ""),
                "body": d["AbstractText"],
                "href": d.get("AbstractURL", ""),
                "source": "DuckDuckGo"
            })
        for t in d.get("RelatedTopics", []):
            if "Text" in t and len(results) < 5:
                results.append({
                    "title": t.get("Text", "")[:60],
                    "body": t.get("Text", ""),
                    "href": t.get("FirstURL", ""),
                    "source": "DuckDuckGo"
                })
        return results
    except Exception:
        return []

def search_wiki(query):
    try:
        r = requests.get(
            f"https://fr.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(query)}",
            timeout=8,
            headers={"User-Agent": "Lumina/6.0"}
        )
        if r.status_code == 200:
            d = r.json()
            if d.get("extract"):
                return [{
                    "title": d.get("title", "Wikipedia"),
                    "body": d["extract"][:800],
                    "href": d.get("content_urls", {}).get("desktop", {}).get("page", ""),
                    "source": "Wikipedia"
                }]
    except Exception:
        pass
    return []

def multi_search(query):
    results = search_ddg(query)
    if len(results) < 3:
        results.extend(search_wiki(query))
    return results[:6]

# ── FLASK ROUTES ───────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(BASE_DIR, path)

@app.route("/auth/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    display_name = (data.get("display_name") or "").strip() or (email.split("@")[0] if email else "")
    if not EMAIL_RE.match(email):
        return jsonify({"error": "Adresse email invalide"}), 400
    if len(password) < 8:
        return jsonify({"error": "Le mot de passe doit faire au moins 8 caractères"}), 400
    db = get_db()
    if db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
        return jsonify({"error": "Un compte existe déjà avec cet email"}), 409
    pw_hash = generate_password_hash(password)
    cur = db.execute(
        "INSERT INTO users (email, password_hash, display_name, created_at) VALUES (?, ?, ?, ?)",
        (email, pw_hash, display_name, time.time())
    )
    user_id = cur.lastrowid
    db.execute("INSERT INTO user_knowledge (user_id, connaissances) VALUES (?, '{}')", (user_id,))
    token = secrets.token_urlsafe(32)
    db.execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)", (token, user_id, time.time()))
    db.commit()
    return jsonify({"token": token, "user": {"id": user_id, "email": email, "display_name": display_name}})

@app.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    if login_blocked(email):
        return jsonify({"error": "Trop de tentatives, réessaie dans quelques minutes"}), 429
    db = get_db()
    row = db.execute("SELECT id, password_hash, display_name FROM users WHERE email = ?", (email,)).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        register_failed_login(email)
        return jsonify({"error": "Email ou mot de passe incorrect"}), 401
    clear_login_attempts(email)
    token = secrets.token_urlsafe(32)
    db.execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)", (token, row["id"], time.time()))
    db.commit()
    return jsonify({"token": token, "user": {"id": row["id"], "email": email, "display_name": row["display_name"]}})

@app.route("/auth/logout", methods=["POST"])
@require_auth
def logout():
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else None
    db = get_db()
    db.execute("DELETE FROM sessions WHERE token = ?", (token,))
    db.commit()
    return jsonify({"status": "ok"})

@app.route("/auth/me", methods=["GET"])
@require_auth
def me():
    db = get_db()
    row = db.execute("SELECT id, email, display_name FROM users WHERE id = ?", (request.user_id,)).fetchone()
    if not row:
        return jsonify({"error": "Utilisateur introuvable"}), 404
    return jsonify({"user": {"id": row["id"], "email": row["email"], "display_name": row["display_name"]}})

@app.route("/models", methods=["GET"])
def get_models():
    return jsonify({"models": [{"id": k, "label": v} for k, v in MODELS_DISPLAY.items()]})

@app.route("/chat", methods=["POST"])
@require_auth
def chat():
    data = request.get_json(silent=True) or {}
    user_msg = data.get("message", "").strip()
    conv_id = (data.get("conv_id") or "default").strip() or "default"
    use_web = bool(data.get("use_web"))
    if not user_msg:
        return jsonify({"error": "Message vide"}), 400
    model_req = data.get("model", DEFAULT_MODEL)
    temp_req = float(data.get("temperature", 0.75))

    if chat_rate_limited(request.user_id):
        return jsonify({"error": "Trop de messages en peu de temps, patiente une minute."}), 429

    historique = load_conv_history(request.user_id, conv_id)
    connaissances = load_knowledge(request.user_id)

    # Apprentissage automatique
    if "apprend que" in user_msg.lower() and " est " in user_msg.lower():
        try:
            phrase = user_msg.lower().split("apprend que", 1)[1].strip()
            sujet, info = phrase.split(" est ", 1)
            connaissances[sujet.strip()] = info.strip()
            save_knowledge(request.user_id, connaissances)
            return jsonify({"reply": f"Noté — {sujet.strip()} est {info.strip()}.", "model": "cache"})
        except Exception:
            pass

    # Détection d'intelligence — les outils ne s'activent que si explicitement demandés
    intent = detect_intent(user_msg)
    should_search = use_web and intent["web"]

    cache_key = f"{request.user_id}:{conv_id}:{model_req}:{user_msg.lower().strip()}"
    if not should_search:
        cached = cache_get(cache_key)
        if cached:
            return jsonify({"reply": cached, "model": "cache"})

    sources = []
    prompt = build_ctx(user_msg, historique, connaissances)

    if should_search:
        results = multi_search(user_msg)
        if results:
            web_block = "\n\n".join(f"[{i+1}] {r['title']} — {r['body'][:300]}" for i, r in enumerate(results))
            prompt = f"Résultats de recherche web (utilise-les pour répondre, cite-les par [numéro]) :\n{web_block}\n\n{prompt}"
            sources = [{"title": r["title"], "href": r["href"], "source": r["source"]} for r in results]

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]

    result = call_groq(messages, preferred_model=model_req, temperature=temp_req)
    reponse = result["content"]

    if result["ok"]:
        if not should_search:
            cache_set(cache_key, reponse)
        historique.append({"user": user_msg, "assistant": reponse})
        if len(historique) > 60:
            historique = historique[-60:]
        save_conv_history(request.user_id, conv_id, historique)

    return jsonify({
        "reply": reponse,
        "model": result.get("model", "unknown"),
        "reasoning": result.get("reasoning"),
        "sources": sources
    })

@app.route("/conv_memory/<conv_id>", methods=["DELETE"])
@require_auth
def conv_memory(conv_id):
    delete_conv_history(request.user_id, conv_id)
    return jsonify({"status": "ok"})

@app.route("/search_web", methods=["POST"])
def search_web():
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "Requête vide"}), 400
    return jsonify({"results": multi_search(query)})

@app.route("/get_memory", methods=["GET"])
@require_auth
def get_memory():
    return jsonify({"connaissances": load_knowledge(request.user_id)})

@app.route("/clear_memory", methods=["POST"])
@require_auth
def clear_memory():
    save_knowledge(request.user_id, {})
    return jsonify({"status": "ok"})

@app.route("/status", methods=["GET"])
def status():
    db = get_db()
    nb_users = db.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    return jsonify({
        "status": "online",
        "version": "6.0",
        "models": GROQ_MODELS_CASCADE,
        "keys": len(GROQ_KEYS),
        "cache": len(cache),
        "users": nb_users
    })

# ── DÉMARRAGE ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "=" * 56)
    print("  🌟  Lumina Server v6.0 — Interface Claude-style")
    print("  Développé par Issa Amakendé Abdoulaye Koné")
    print(f"  Port  : 5005")
    print(f"  Clés  : {len(GROQ_KEYS)} Groq key(s)")
    print(f"  Cache : {CACHE_SIZE} entrées")
    print(f"  DB    : {DB_FILE}")
    print("=" * 56 + "\n")
    app.run(host="0.0.0.0", port=5005, debug=False, threaded=True)
