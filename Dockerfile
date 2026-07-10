FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5005

# --timeout 120 : un chat peut passer par plusieurs modèles/clés Groq en cascade
# avant de répondre si les premiers échouent (voir call_groq) ; large marge pour
# ne pas couper une requête légitime en plein milieu.
CMD ["gunicorn", "lumina_server:app", "--bind", "0.0.0.0:5005", "--workers", "2", "--threads", "4", "--timeout", "120"]
