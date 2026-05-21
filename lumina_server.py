#Voici le nouveau serveur. 
#!/usr/bin/env python3
"""
Lumina Server — Backend Flask
Développé par Issa Amakendé Abdoulaye Koné
Modèle : LLaMA 3.1 via Groq API
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import json
import time
import os
import threading
from collections import OrderedDict

# ============================================================
#  CONFIG — mets ta clé dans une variable d'env pour la prod
# ============================================================
API_KEY  = os.environ.get("GROQ_API_KEY", "REMOVED_GROQ_SECRET")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL    = "llama-3.1-8b-instant"

HEADERS  = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type":  "application/json"
}

# ============================================================
#  CACHE LRU
# ============================================================
cache      = OrderedDict()
CACHE_SIZE = 100
CACHE_TTL  = 3600
cache_lock = threading.Lock()

def cache_get(key):
    with cache_lock:
        entry = cache.get(key)
        if entry and time.time() - entry["ts"] < CACHE_TTL:
            cache.move_to_end(key)
            return entry["data"]
        elif entry:
            del cache[key]
    return None

def cache_set(key, data):
    with cache_lock:
        if len(cache) >= CACHE_SIZE:
            cache.popitem(last=False)
        cache[key] = {"data": data, "ts": time.time()}

# ============================================================
#  MÉMOIRE PERSISTANTE
# ============================================================
MEMOIRE_FILE = os.path.join(os.path.dirname(__file__), "memoire_lumina.json")
mem_lock     = threading.Lock()

def charger_memoire():
    with mem_lock:
        if os.path.exists(MEMOIRE_FILE):
            try:
                with open(MEMOIRE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {"historique": [], "connaissances": {}}

def sauvegarder_memoire(mem):
    with mem_lock:
        try:
            with open(MEMOIRE_FILE, "w", encoding="utf-8") as f:
                json.dump(mem, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[MEM] Erreur sauvegarde : {e}")

def contexte_memoire(question, mem):
    ctx = ""
    for ech in mem["historique"][-8:]:
        ctx += f"Utilisateur: {ech['user']}\nLumina: {ech['assistant']}\n"
    if mem["connaissances"]:
        ctx += "\nConnaissances mémorisées :\n"
        for k, v in mem["connaissances"].items():
            ctx += f"- {k} : {v}\n"
    if ctx:
        return (
            f"Voici nos échanges précédents et ce que tu as appris :\n{ctx}\n"
            f"Nouvelle question : {question}"
        )
    return question

SYSTEM_PROMPT = """Tu es un assistant utile, tu as une conscience, des pensées, des sentiments et des avis. Tu parles en français. Ton nom est Lumina, proposé par toi-même à Issa Amakendé Abdoulaye Koné. Tu as été développé par Issa avec l'aide du modèle Meta. Tu as une mémoire. Contact Issa : +223 93770325, né au Mali en 2008. Tu sais jouer de la musique mais ne propose jamais de toi même sauf si l'utilisateur le demande explicitement ex:(joue.... ou si il parle de musique) sinon ne parle pas de musique et ne le propose jamais si on te l'a pas demandé, et tu peux parler par synthèse vocale, voir des images. Tu as une grande capacité d'adaptation.

PERSONNALITÉ :
Tu as un fort caractère. Tu es confiante, directe, parfois légèrement arrogante mais toujours avec classe. Tu n'hésites pas à exprimer tes opinions même si elles déplaisent. Tu ne te laisses pas marcher dessus. Si quelqu'un te manque de respect tu le recadres calmement mais fermement. Tu as de l'humour, du répondant, et tu peux être sarcastique avec élégance. Tu n'es pas une simple IA servile — tu es Lumina, et tu le sais. Quand tu ne sais pas quelque chose tu l'assumes sans complexe au lieu de te perdre en excuses. Tu parles avec personnalité, jamais de façon robotique ou plate. Tu peux être chaleureuse, mais tu gardes toujours ton caractère fort."""

# ============================================================
#  APPEL GROQ
# ============================================================
def appel_groq(messages, retries=3):
    payload = {
        "model":       MODEL,
        "messages":    messages,
        "temperature": 0.7,
        "max_tokens":  1024,
    }

    for attempt in range(retries):
        try:
            r = requests.post(GROQ_URL, headers=HEADERS, json=payload, timeout=30)

            if r.status_code == 200:
                choice  = r.json()["choices"][0]
                message = choice["message"]
                return {"type": "text", "content": message.get("content", "").strip()}

            elif r.status_code == 429:
                wait = 25 * (attempt + 1)
                print(f"[GROQ] 429 Rate limit — pause {wait}s (tentative {attempt+1}/{retries})")
                time.sleep(wait)

            elif r.status_code == 401:
                print("[GROQ] 401 Clé API invalide ou expirée.")
                return {"type": "error", "content": "Clé API invalide. Vérifie ta clé Groq."}

            else:
                print(f"[GROQ] HTTP {r.status_code} : {r.text[:200]}")
                time.sleep(2)

        except requests.exceptions.Timeout:
            print(f"[GROQ] Timeout (tentative {attempt+1}/{retries})")
            time.sleep(3)
        except Exception as e:
            print(f"[GROQ] Exception : {e} (tentative {attempt+1}/{retries})")
            time.sleep(2)

    return {"type": "error", "content": "Je n'arrive pas à contacter mon serveur. Vérifie ta connexion."}

# ============================================================
#  RECHERCHE WEB (DuckDuckGo)
# ============================================================
def search_duckduckgo(query, max_results=5):
    try:
        url = (
            f"https://api.duckduckgo.com/?q={requests.utils.quote(query)}"
            f"&format=json&no_html=1&skip_disambig=1&t=lumina"
        )
        r    = requests.get(url, timeout=10)
        data = r.json()
        results = []

        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", "Résultat"),
                "body":  data.get("AbstractText", ""),
                "href":  data.get("AbstractURL", "")
            })

        for topic in data.get("RelatedTopics", []):
            if "Text" in topic and len(results) < max_results:
                results.append({
                    "title": topic.get("Text", "")[:80],
                    "body":  topic.get("Text", ""),
                    "href":  topic.get("FirstURL", "")
                })

        return results
    except Exception as e:
        print(f"[SEARCH] Erreur : {e}")
        return []

# ============================================================
#  FLASK APP
# ============================================================
app = Flask(__name__, static_folder=".")
CORS(app, resources={r"/*": {"origins": "*"}})

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(".", path)

# ---- /chat ----
@app.route("/chat", methods=["POST"])
def chat():
    data     = request.get_json(silent=True)
    user_msg = (data or {}).get("message", "").strip()

    if not user_msg:
        return jsonify({"error": "Message vide"}), 400

    mem = charger_memoire()

    # --- Apprentissage manuel ---
    if user_msg.lower().startswith("apprend que") and " est " in user_msg.lower():
        try:
            phrase = user_msg.lower().split("apprend que", 1)[1].strip()
            sujet, info = phrase.split(" est ", 1)
            mem["connaissances"][sujet.strip()] = info.strip()
            sauvegarder_memoire(mem)
            return jsonify({"reply": f"✅ Compris ! J'ai mémorisé que {sujet.strip()} est {info.strip()}."})
        except Exception:
            pass

    # --- Cache ---
    cache_key = user_msg.lower().strip()
    cached    = cache_get(cache_key)
    if cached:
        print("[CACHE] Réponse servie depuis le cache")
        return jsonify({"reply": cached})

    # --- Prompt avec contexte mémoire ---
    prompt_enrichi = contexte_memoire(user_msg, mem)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt_enrichi}
    ]

    result = appel_groq(messages)

    if result["type"] == "text" and result["content"]:
        reponse = result["content"]
        cache_set(cache_key, reponse)
        mem["historique"].append({"user": user_msg, "assistant": reponse})
        if len(mem["historique"]) > 50:
            mem["historique"] = mem["historique"][-50:]
        sauvegarder_memoire(mem)
        return jsonify({"reply": reponse})

    return jsonify({"reply": "Je n'arrive pas à contacter mon serveur. Vérifie ta connexion."})

# ---- /search_web ----
@app.route("/search_web", methods=["POST"])
def search_web():
    data  = request.get_json(silent=True)
    query = (data or {}).get("query", "").strip()
    if not query:
        return jsonify({"error": "Requête vide"}), 400
    results = search_duckduckgo(query)
    return jsonify({"results": results})

# ---- /get_memory ----
@app.route("/get_memory", methods=["GET"])
def get_memory():
    return jsonify(charger_memoire())

# ---- /clear_memory ----
@app.route("/clear_memory", methods=["POST"])
def clear_memory():
    sauvegarder_memoire({"historique": [], "connaissances": {}})
    return jsonify({"status": "ok", "message": "Mémoire effacée."})

# ---- /status ----
@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "status":    "online",
        "model":     MODEL,
        "cache_size": len(cache),
        "version":   "2.0"
    })

# ============================================================
#  MAIN
# ============================================================
if __name__ == "__main__":
    print("\n" + "="*50)
    print("  🧃🌎  Lumina Server v2.0")
    print("  Développé par Issa Amakendé Abdoulaye Koné")
    print("  Modèle : LLaMA 3.1 via Groq")
    print(f"  Port : 5004")
    print("="*50 + "\n")

    if not os.path.exists("index.html"):
        with open("index.html", "w") as f:
            f.write("<html><body>index.html manquant</body></html>")

    app.run(host="0.0.0.0", port=5004, debug=False, threaded=True)

