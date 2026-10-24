# Déployer Lumina v7 (Render + Neon + Android)

> Cette procédure **n'a pas été exécutée** pendant le développement (pas d'accès à Render, Neon, Docker ni au SDK
> Android). Les points marqués ⚠ sont à vérifier chez toi à la première mise en ligne.
> Ne déploie rien tant que les « Contrôles avant mise en production » (fin de ce fichier) ne sont pas cochés.

## 1. Variables d'environnement (Render → Environment)

| Variable | Obligatoire | Rôle |
|---|---|---|
| `GROQ_API_KEYS` | oui | Une ou plusieurs clés Groq séparées par des virgules (rotation automatique). **Jamais dans le code.** |
| `DATABASE_URL` | oui (prod) | Chaîne **pooled** Neon (hôte `…-pooler…`) avec `?sslmode=require`. Absente = SQLite éphémère (perdue à chaque redéploiement). |
| `CORS_ORIGINS` | recommandé | `https://lumina-ai-sjyp.onrender.com,https://localhost,capacitor://localhost` — **`https://localhost` est l'origine de l'APK** ; sans lui l'appli Android serait bloquée. Défaut `*`. |
| `TRUST_PROXY_HOPS` | oui sur Render | `1` (un proxy Render devant l'appli) : nécessaire pour que les limites par IP voient la vraie IP. |
| `ADMIN_TOKEN` | facultatif | Long jeton aléatoire. Donne accès à `/status` détaillé et `/groq_models` via l'en-tête `X-Admin-Token`. Vide = désactivé. |
| `SESSION_TTL_DAYS` | non | Durée d'une session (défaut 30). |
| `GROQ_TOTAL_TIMEOUT` | non | Délai global de la cascade de modèles, en secondes (défaut 45). |
| `GROQ_VISION_MODELS` | non | Modèles compatibles image, séparés par des virgules (défaut : le modèle « Prime »). ⚠ À vérifier : voir §5. |
| `GROQ_STT_MODEL` | non | Modèle de transcription du mode Live (défaut `whisper-large-v3-turbo`). ⚠ À vérifier. |
| `MAX_MESSAGE_CHARS`, `LIVE_MAX_PER_MIN`, `SIGNUP_MAX_PER_HOUR`, `DB_CONNECT_TIMEOUT` | non | Plafonds de coût / abus (défauts dans `.env.example`). |

`.env.example` ne contient que des noms et des valeurs factices.

## 2. Render

1. Service existant **Lumina_AI** (Docker). Le `Dockerfile` v7 :
   - n'embarque que `lumina_server.py`, `migrate_sqlite_to_neon.py` et `www/` (voir `.dockerignore`) ;
   - tourne en utilisateur non-root, **1 worker gunicorn + 8 threads** (cache, limites de débit et verrous sont en mémoire ;
     un seul worker les garde cohérents) ;
   - installe `psycopg[binary]` : aucune bibliothèque système à ajouter.
2. **Health Check Path** : `/healthz` (répond 200 si la base répond, 503 sinon ; ne révèle aucune configuration).
3. Renseigner les variables du §1, puis déployer **depuis une branche de test d'abord** si possible.
4. ⚠ Premier démarrage : lire les logs. Attendus : aucune ligne `[DB] initialisation impossible`. Si elle apparaît,
   le serveur reste en ligne et réessaie à la requête suivante (réponses 503 « Base de données indisponible » en attendant).
5. Le plan gratuit met le service en veille : le premier appel est lent (démarrage à froid), c'est normal.

## 3. Neon

- **Production** : projet `Lumina`, branche `production`, base `neondb` (inchangé). La migration v7 est **additive**
  (voir `docs/MIGRATION.md`) : une table `feedback` et deux index, créés au démarrage (`CREATE … IF NOT EXISTS`).
  Aucune donnée existante n'est lue ni modifiée.
- **Avant le premier déploiement v7** : crée une **branche Neon de sauvegarde** (copie instantanée de `production`).
- **Tests PostgreSQL** : crée une branche dédiée `test` (jamais `production`) puis :
  `TEST_DATABASE_URL='…' CONFIRM_TEST_DB=yes python scripts/pg_smoke.py` (refuse de tourner sinon).
- Neon met la base en veille : la première connexion après inactivité peut prendre quelques secondes
  (`DB_CONNECT_TIMEOUT=10` par défaut ; monte à 20 si tu vois des 503 au réveil).

## 4. Android (Capacitor)

Prérequis : Node ≥ 22, JDK 21, SDK Android (compileSdk 36). Le `webDir` est `www/` (source unique du frontend).

```bash
npm ci                      # dépendances Capacitor (package-lock.json fourni)
npx cap sync android        # copie www/ dans android/app/src/main/assets/public (dossier ignoré par Git)
cd android && ./gradlew assembleDebug
```

- **Termux** : copie `android/gradle.properties.termux.example` dans `~/.gradle/gradle.properties` (le chemin Termux
  n'est plus dans le dépôt : il bloquait toute compilation hors de ton téléphone).
- **Permissions** (ajoutées au manifeste) : `CAMERA`, `RECORD_AUDIO`, `MODIFY_AUDIO_SETTINGS` — requises par le mode Live.
  `allowBackup` est désormais `false` (le jeton de session n'est plus sauvegardé dans le cloud Android).
- **URL de l'API dans l'APK** : `www/index.html` (`const BASE = …`) pointe vers `https://lumina-ai-sjyp.onrender.com`.
  Si l'URL du service change, modifier cette ligne puis refaire `npx cap sync`.
- **Icônes** : lanceur adaptatif, rond et écran de démarrage générés depuis l'illustration fournie
  (`android/app/src/main/res/mipmap-*`, `drawable*/splash.png`).
- ⚠ **Non compilé ici.** À tester sur appareil : demande de permission caméra/micro, caméra arrière, synthèse vocale native,
  rendu sous la barre d'état (marges `--safe-area-inset-top`).

## 5. À vérifier chez toi après déploiement (avec `ADMIN_TOKEN`)

```bash
curl -s -H "X-Admin-Token: $ADMIN_TOKEN" https://lumina-ai-sjyp.onrender.com/status        # version 7.0, base « postgresql »
curl -s -H "X-Admin-Token: $ADMIN_TOKEN" https://lumina-ai-sjyp.onrender.com/groq_models    # le modèle vision et whisper existent-ils ?
curl -s -o /dev/null -w "%{http_code}\n" https://lumina-ai-sjyp.onrender.com/lumina_server.py   # attendu : 404
```

## 6. Contrôles avant mise en production

- [ ] `scripts/run_tests.sh` : tout passe.
- [ ] `scripts/pg_smoke.py` passe sur une **branche Neon de test**.
- [ ] Branche Neon de sauvegarde créée.
- [ ] Logs Render sans erreur au démarrage ; `/healthz` = 200 ; fichiers internes = 404.
- [ ] Inscription, connexion, message, redémarrage du service puis rechargement : la conversation et le compte persistent.
- [ ] `/groq_models` confirme le modèle vision et le modèle de transcription ; ajuster `GROQ_VISION_MODELS` / `GROQ_STT_MODEL` sinon.
- [ ] APK : test sur un vrai téléphone (caméra avant/arrière, micro, permissions, en-tête sous la barre d'état).
- [ ] Mode Live testé **avec voix réelle** (casque et haut-parleur) : coût Groq par session mesuré.
- [ ] Pages légales relues par une personne compétente (voir `docs/RAPPORT_V7.md`, « Limitations »).
