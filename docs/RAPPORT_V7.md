# Lumina v7 — rapport des modifications

**Verdict : candidate au déploiement, PAS prête pour la production.** Le code est exécutable et testé dans mon environnement
(SQLite, navigateur Chromium, fournisseurs IA simulés). Rien n'a été testé contre Render, Neon, Groq, Docker, Gradle ni un
téléphone Android réel. La liste précise est en §6 et §7 ; `DEPLOY.md` donne les contrôles à faire avant toute mise en ligne.

Rien n'a été déployé, poussé ni supprimé : ta version d'origine est intacte ; la v7 est un dossier séparé.

## 1. Vérification des conclusions de l'audit

| # | Constat de l'audit | Statut dans la v7 | Preuve |
|---|---|---|---|
| C1 | `get_db()` ne retournait rien → inscription/connexion/chat en 500 | **Confirmé** (reproduit) → corrigé | `test_get_db_returns_connection` ; inscription OK en test |
| C2 | Fichiers du projet servis publiquement (`lumina.db`, code, Dockerfile…) | **Confirmé** (reproduit) → corrigé : seul `www/` est servi, extensions en liste blanche, fichiers cachés refusés | `test_internal_files_are_not_served` (18 chemins dont `..%2f`) |
| C3 | `index.html` plante au chargement, `boot()` jamais atteint | **Confirmé** en simulation **et dans Chromium réel** → corrigé (modales déplacées avant le script + gardes) | `frontend_boot.test.js` : **échoue sur l'original (ligne 2565), réussit sur la v7** ; test navigateur |
| E1 | Le cache ignore l'image ; « Régénérer » renvoie la même réponse | **Confirmé** → corrigé (pas de cache pour les images ni pour « Régénérer ») | `test_cache_does_not_mix_two_different_images`, test navigateur avec 2 vraies images |
| E2 | Sessions éternelles | **Confirmé** → expiration (30 j, configurable), purge, 20 sessions max/utilisateur | `test_session_expires` |
| E3 | Verrouillage d'un tiers ; inscriptions illimitées | **Confirmé** → limite par (email, IP) + par IP ; inscriptions limitées par IP | `test_login_lockout_cannot_be_used_against_a_victim`, `test_signup_rate_limit_per_ip` |
| E4 | Aucune limite de taille | **Confirmé** → message 8 000 car., image 4 Mo, requête 6 Mo ; images réduites côté client | `test_limits`, test navigateur (photo 3200×2400 envoyée réduite) |
| E5 | Panne Groq renvoyée en HTTP 200 | **Confirmé** → 503, rien n'est enregistré | `test_provider_outage_returns_503_and_saves_nothing` |
| E6 | Iframe des artéfacts avec `allow-same-origin` | **Lu, non exploité** → retiré | test navigateur (attribut `sandbox`) |
| E7 | `psycopg` sans `[binary]` sur image slim | **Risque potentiel, non reproduit** (pas de Docker ici) → `psycopg[binary]` | ⚠ à valider par un build Render |
| E8 | Permissions caméra/micro absentes | **Confirmé** (lecture) → ajoutées | XML bien formé ; ⚠ non testé sur appareil |
| E9 | Chemin Termux dans `gradle.properties` | **Confirmé** (lecture) → retiré, exemple fourni | — |
| E10 | `.gitignore` sans `*.backup*` | **Confirmé** → complété (`*.db.backup*`, archives, `.env`, build Android) | — |
| M1 | Cascade sans délai global | **Confirmé** → délai global 45 s | `test_cascade_respects_global_deadline` |
| M2 | `/status`, `/groq_models`, `/search_web` publics | **Confirmé** → `/status` minimal, le reste protégé | `test_public_status_is_minimal…` |
| M3 | Connexions PostgreSQL sans délai | → `connect_timeout`, schéma initialisé « paresseusement » (un Neon endormi ne plante plus le démarrage), URL jamais affichée | tests `unreachable_postgres…` (⚠ pas de vraie base) |
| M4 | Modèle `qwen/qwen3.6-27b` non vérifié | **Non résolu** (inchangé) ; modèles vision rendus configurables | ⚠ `/groq_models` (admin) |
| M5 | `DEPLOY.md` périmé | → réécrit (Render + Neon + Android) | — |
| M6 | PWA : icônes absentes, SW vide, numéro de téléphone dans le manifeste | → icônes générées, SW réel (réseau d'abord, API jamais en cache), **numéro retiré du manifeste public** (à remettre si tu le souhaites) | test navigateur (icônes chargées) |
| M7 | Conditions/signalement inaccessibles, retours sans effet | → liens ajoutés, signalement et likes enregistrés (table `feedback`), suppression de compte | tests `feedback`, `delete_account` |
| M8 | Boutons morts | → « Projets » et « Artéfacts » retirés ; réglage « Vision » rendu réel (commentaires spontanés du Live) | — |
| M9 | Services tiers appelés par le navigateur | **Inchangé** (voir limitations) | — |
| M10 | Aucun test | → 29 tests backend + test de boot + 13 tests navigateur | §6 |

**Défauts supplémentaires découverts pendant la v7 :**
- `captureAndAnalyze` (capture par geste) utilisait `ev`, variable inexistante → l'analyse échouait toujours (lecture du code) → corrigé.
- Pendant l'animation de salutation, l'envoi d'un message était **ignoré en silence** et le bouton d'envoi agissait comme « stop » (reproduit dans Chromium) → corrigé, avec test.
- « Régénérer » dupliquait l'échange dans l'historique serveur → corrigé, avec test.
- En-tête chevauchant la barre d'état Android (ta capture) ; bouton ⋮ des conversations et actions de message invisibles au tactile ; faux panneau « Analyse en cours » avec étapes décoratives → corrigés.
- Un autre compte sur le même appareil voyait les discussions locales du précédent → corrigé (test navigateur).

## 2. Inventaire des fichiers

**Créés :** `www/v7.css`, `www/ui7.js`, `www/live.js`, `www/icons/*` (5 fichiers), `.env.example`, `.dockerignore`, `requirements-termux.txt`, `requirements-dev.txt`, `android/gradle.properties.termux.example`, `tests/*`, `scripts/*`, `docs/*`.
**Modifiés :** `lumina_server.py` (2 376 → 2 942 lignes, correctifs ciblés ; **aucun** route ni comportement utile retiré), `www/index.html` (patchs ciblés, pas de réécriture), `www/manifest.json`, `www/sw.js`, `Dockerfile`, `Procfile`, `requirements.txt`, `.gitignore`, `capacitor.config.json`, `package.json` (scripts), `android/app/src/main/AndroidManifest.xml`, `android/gradle.properties`, icônes et écrans de démarrage Android, `README.md`, `DEPLOY.md`.
**Déplacés :** `index.html`, `manifest.json`, `sw.js` → `www/` (source unique du frontend, aussi utilisée par Capacitor).
**Supprimés (de la v7 seulement ; les originaux restent chez toi) :**
- `lumina.js` : chargé par aucune page, 40 de ses 83 identifiants HTML n'existent pas ; livré inutilement dans l'APK.
- `fix_vision.py` : script de patch ponctuel déjà appliqué.
**Inchangé :** `migrate_sqlite_to_neon.py`, `package-lock.json`.

Comparatif complet : `docs/v6.1_to_v7.diff` ou `sh scripts/compare_with_v6.sh ~/assistant_pwa`.

## 3. Fonctionnalités conservées

Chat et choix du modèle · comptes, connexion, session · historique et mémoire par conversation (+ « apprend que… ») · analyse d'image
(désormais réduite avant envoi) et de fichiers texte · synthèse vocale (native Android et navigateur) · dictée du bouton micro ·
caméra : **gestes MediaPipe conservés** (« Gestes (expérimental) » dans le menu +) · génération d'images (Pollinations) ·
musique (Jamendo, MusicGen) · recherche web · graphiques `y = f(x)` · artéfacts (aperçu, copie, export, PDF) · épingler / renommer /
dupliquer / exporter / supprimer les discussions · PWA et APK.

## 4. Nouveautés

**Lumina Live** (bouton caméra à côté du micro, ou « Vision » du menu +) — plein écran, façon mode vocal direct :
- **Caméra avant et arrière** (bouton de bascule ; image en miroir en mode selfie ; reprise propre si la caméra est interrompue).
- **L'IA parle de sa propre initiative** quand c'est utile (conseils, corrections, encouragements sur ce que tu fais) ou se tait (`[SILENCE]`).
  Elle est déclenchée par un **changement de scène** détecté localement ou par un délai maximal, jamais en boucle ; trois niveaux
  (Discret / Normal / Réactif) ; elle ne répète pas ses derniers commentaires ; pause automatique si l'écran est masqué.
- **Elle répond quand tu parles** : détection de parole locale → transcription Whisper (via Groq, marche aussi dans la WebView Android)
  → réponse courte à l'oral avec l'image courante. **Tu peux l'interrompre** pendant qu'elle parle (désactivable). Toucher l'image =
  « regarde ça ».
- Les échanges sont ajoutés à la conversation ; les images et l'audio ne sont jamais enregistrés par le serveur. Un écran de consentement
  s'affiche au premier lancement. Limites de débit et de taille côté serveur.

**Interface :** logo Lumina vivant avec effet miroir (reflet, aura, éclat, étincelles, inclinaison au doigt/gyroscope, burst au toucher),
avatar animé, ondulations au toucher, retour haptique, bouton d'envoi réactif, balayage depuis le bord pour le menu, bouton « retour en bas »,
entrées échelonnées, thèmes **sombre / AMOLED / clair** réellement fonctionnels, réglage « Animations » et respect de « réduire les animations »,
animations du logo suspendues quand l'onglet est masqué. **Icône de l'application** (web, maskable, Android adaptatif/rond, écran de démarrage) = ton illustration.
**Compte :** suppression de compte (mot de passe requis) ; signalement de problème ; conditions d'utilisation accessibles.

## 5. Choix techniques à connaître
- 1 worker gunicorn + 8 threads : limites de débit et cache en mémoire cohérents. Elles repartent à zéro à chaque redémarrage.
- Tokens de session toujours en clair en base (comme avant) : les hacher déconnecterait tout le monde ; à faire dans une version ultérieure.
- Le « mode Live » utilise `ScriptProcessorNode` (déprécié mais universel, y compris WebView) plutôt qu'`AudioWorklet`.

## 6. Tests

| Test | Résultat |
|---|---|
| Compilation Python (serveur, migration, scripts) ; syntaxe JS (`index.html`, `live.js`, `ui7.js`, `sw.js`) ; JSON (manifeste, Capacitor, package) ; XML Android | **Réussi** |
| Backend `tests/test_backend.py` : base SQLite, auth, expiration, limites, routes statiques, en-têtes, cache (2 images), régénération, panne Groq, délai global, isolation entre utilisateurs, suppression de compte, feedback, Live (observer/tour/STT, limites, aucune image stockée), traduction `?`→`%s`, Postgres injoignable sans plantage ni fuite d'URL, migration additive idempotente | **29/29 réussis** (7 s) |
| Initialisation du frontend `tests/frontend_boot.test.js` | **Réussi** sur la v7 ; **échoue sur l'original** (comme attendu : bug C3) |
| Non couvert par un test automatique : balayage depuis le bord, bouton « retour en bas », retour haptique, inclinaison au gyroscope, ondulations | **Non testé** (code présent, à essayer sur téléphone) |
| Navigateur `tests/e2e_browser.py` (Chromium, 390×844 tactile, caméra et micro factices) | **13/13 réussis** : démarrage sans erreur JS, en-tête et zone sûre, pas de débordement à 360/390 px, logo vivant, thèmes et animations, XSS (titre/lien) et iframe isolée, changement de compte, tactile, « Régénérer » + 2 photos réduites sans cache croisé, message envoyé pendant la salutation, panne fournisseur affichée, Live : caméra avant/arrière (miroir), commentaire spontané, réponse vocale, « regarde ça », interruption, permission refusée |
| Connexion PostgreSQL / Neon réelle | **Non exécuté** (aucune base de test) → `scripts/pg_smoke.py` (refuse de tourner hors base de test) |
| Build Docker / déploiement Render | **Non exécuté** |
| Compilation Gradle / APK ; test sur Android (permissions, caméra arrière réelle, TTS natif, marges sous la barre d'état) | **Non exécuté** |
| Groq réel : chat, vision, Whisper ; existence des modèles Qwen/Whisper configurés | **Non exécuté** (fournisseurs simulés) |
| Voix et synthèse vocale réelles, écho haut-parleur/micro, qualité de détection de parole en conditions réelles | **Non exécuté** (audio synthétique ; voix synthétique simulée) |
| Pollinations, Jamendo, MusicGen, MediaPipe, recherche web | **Non exécuté** (réseau indisponible) |
| Rendu sur un vrai téléphone, installation PWA | **Non exécuté** (captures Chromium uniquement) |

## 7. Limitations restantes
1. **Live — ce que « détecter ce que fait l'utilisateur » veut dire ici :** un modèle de vision regarde des images réduites prises quand la scène change
   ou à intervalle ; il ne suit pas les actions image par image. Latence typique de plusieurs secondes ; qualité et coût dépendent du modèle Groq.
2. **Écho :** avec haut-parleur, le micro peut capter la voix de l'IA (seuils adaptatifs et annulation d'écho du navigateur, mais pas de garantie) ;
   le **casque est recommandé**. L'option « Interruption : non » désactive la coupure de parole.
3. **Coût Groq non mesuré :** chaque commentaire et chaque phrase transcrite sont des requêtes. Plafonds : 40 requêtes Live/min/utilisateur ; mesure à faire avant d'ouvrir au public.
4. **Modèles :** Prime (`qwen/qwen3.6-27b`) et Whisper (`whisper-large-v3-turbo`) sont **non vérifiés** ; configurables par variables d'environnement.
5. **Dictée du bouton micro classique :** `webkitSpeechRecognition` n'est pas fiable dans une WebView Android (inchangé) ; le Live n'en dépend pas.
6. **Données :** les conversations restent stockées **localement** (pas de synchronisation entre appareils : choix d'architecture d'origine conservé) ; le serveur ne garde que le contexte texte.
7. **Sécurité restante :** pas de CSP (le HTML inline en nécessiterait une permissive), pas de vérification d'email ni de réinitialisation de mot de passe, jetons de session en clair, limites en mémoire par processus.
8. **Légal :** les **conditions d'utilisation** existantes sont accessibles mais n'ont pas été revues ; **aucune politique de confidentialité n'a été écrite** (je n'invente ni société, ni adresse, ni conformité). Sous-traitants à déclarer : Groq, Neon, Render, et côté navigateur Pollinations, Jamendo, Hugging Face, Google Fonts, jsDelivr / Google Storage (MediaPipe). Relecture juridique locale nécessaire. L'export des données n'est pas implémenté.
9. **Tiers côté navigateur inchangés :** identifiant Jamendo dans le code, jeton Hugging Face dans `localStorage`, polices Google, MediaPipe via CDN, génération d'images sans modération.
10. **Visuel :** vérifié sur Chromium émulé ; l'apparence réelle (barre d'état Android, `--safe-area-inset-top`) reste à confirmer sur ton téléphone.

## 8. Critère de fin
Candidate au déploiement **après** : `scripts/pg_smoke.py` sur une branche Neon de test, un build Render réussi (E7), la vérification des modèles
(`/groq_models`), un test APK sur téléphone et un essai du Live à la voix réelle. Procédure de retour : `docs/ROLLBACK.md`.
