FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Seuls le serveur, le script de migration et le frontend (www/) entrent dans l'image
# (voir .dockerignore). Le serveur ne sert que www/.
COPY lumina_server.py migrate_sqlite_to_neon.py ./
COPY www ./www

RUN useradd --system --create-home lumina && chown -R lumina /app
USER lumina

EXPOSE 5005

HEALTHCHECK --interval=60s --timeout=5s --start-period=40s \
  CMD python -c "import os,urllib.request as u;u.urlopen('http://127.0.0.1:'+os.environ.get('PORT','5005')+'/healthz',timeout=4)" || exit 1

# 1 worker + 8 threads : cache, limites de débit et verrous sont en mémoire (par processus) ;
# un seul worker les garde cohérents. L'appli est surtout en attente réseau (Groq) : les threads suffisent.
# --timeout 120 : au-dessus du délai global de la cascade Groq (GROQ_TOTAL_TIMEOUT, 45 s par défaut).
CMD ["sh", "-c", "exec gunicorn lumina_server:app --bind 0.0.0.0:${PORT:-5005} --workers 1 --threads 8 --timeout 120"]
