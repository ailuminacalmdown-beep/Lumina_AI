from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os

app = Flask(__name__, static_folder='.')
CORS(app)

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_msg = data.get('message', '')
    if not user_msg:
        return jsonify({'reply': 'Message vide'})
    # Réponse locale, sans API
    reply = f"Je te réponds : {user_msg}. (mode test local)"
    return jsonify({'reply': reply})

if __name__ == '__main__':
    print("\n🧪 Serveur local (sans Groq) sur http://localhost:5002\n")
    app.run(host='0.0.0.0', port=5002, debug=False)
