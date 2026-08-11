# Déployer Lumina

## 1. Variables d'environnement

Obligatoire :
```
GROQ_API_KEY_1=ta_cle_groq
```
Optionnelles :
```
GROQ_API_KEY_2=...          # clé de secours (rotation automatique si la 1ère est à quota)
GROQ_API_KEY_3=...
CORS_ORIGINS=https://ton-domaine.com   # défaut "*" — à restreindre une fois le domaine connu
```

Ne mets jamais ces valeurs dans le code. Le serveur refuse de démarrer utilement sans elles (il tourne, mais `/chat` renverra toujours le message de repli).

## 2. Lancer en local (développement)

```bash
pip install -r requirements.txt
export GROQ_API_KEY_1="ta_cle_groq"
python lumina_server.py
```
Ouvre `http://localhost:5005`.

## 3. Lancer en production

Ne jamais utiliser `python lumina_server.py` en production : c'est un serveur de développement Flask, pas fait pour tenir une vraie charge. Utilise gunicorn (déjà dans `requirements.txt`) :

```bash
gunicorn lumina_server:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120
```

Un `Procfile` et un `Dockerfile` sont fournis et font déjà ça — la plupart des plateformes les détectent automatiquement.

## 4. Où héberger

Le vrai piège pour cette appli précisément : `lumina.db` (comptes, mots de passe hachés, mémoire) est un **fichier local**. Beaucoup d'offres gratuites (Render free, Railway sans volume, la plupart des plateformes "serverless") ont un **disque éphémère** : le fichier est effacé à chaque redémarrage ou redéploiement. Sur ce genre d'offre, tes utilisateurs perdraient leur compte du jour au lendemain sans prévenir.

Deux options honnêtes :
- **Un petit serveur avec disque persistant** (Fly.io avec un volume, ou une offre équivalente) — quelques dollars/mois, `lumina.db` survit aux redéploiements. Le Dockerfile fourni fonctionne tel quel.
- **PythonAnywhere** (plan payant, pas le gratuit — le gratuit restreint les appels sortants, ce qui bloquerait les appels à Groq) — stockage persistant par défaut, plus simple si tu préfères éviter Docker.

Si un jour tu dois répartir la charge sur plusieurs serveurs, `lumina.db` (un fichier local) ne suffira plus — il faudra migrer vers une vraie base hébergée (Postgres). Pas la peine d'y penser avant d'en avoir vraiment besoin.

## 5. HTTPS — non négociable

L'app envoie maintenant des mots de passe (à l'inscription/connexion). Servir ça en `http://` pur les expose en clair sur le réseau. Toutes les plateformes citées ci-dessus fournissent HTTPS automatiquement (certificat géré pour toi) — assure-toi juste que l'app finale est bien accédée en `https://`, jamais en `http://` direct vers le port 5005.

## 6. Checklist avant mise en ligne

- [ ] `GROQ_API_KEY_1` définie en variable d'environnement sur la plateforme (jamais dans le code)
- [ ] Ancienne clé Groq (celle qui a fuité) révoquée sur le dashboard Groq
- [ ] Hébergeur avec disque persistant confirmé (pas de surprise de perte de données)
- [ ] Accès uniquement en HTTPS
- [ ] `CORS_ORIGINS` restreint à ton domaine une fois connu
- [ ] `.gitignore` en place avant le premier `git push` (fourni — vérifie qu'il est bien pris en compte)
