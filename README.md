---
title: Lumina
emoji: ✨
colorFrom: purple
colorTo: blue
sdk: docker
app_port: 5005
---
# Lumina v7

Assistant IA multimodal : chat, vision en direct (caméra avant/arrière + voix), images, musique, graphiques.
Backend Flask + Groq, base PostgreSQL (Neon) ou SQLite, frontend PWA unique (`www/`), application Android (Capacitor).

> **Statut : candidate au déploiement, pas prête pour la production.** Voir `docs/RAPPORT_V7.md` (tests réalisés,
> tests non réalisés, limitations) et `DEPLOY.md` (contrôles obligatoires).

## Démarrer en local
```bash
cp .env.example .env        # puis y mettre tes propres clés (jamais committées)
sh scripts/run_local.sh     # http://localhost:5005 — SQLite local, la base de production n'est jamais utilisée par défaut
```

## Tester
```bash
sh scripts/run_tests.sh     # backend (29), démarrage du frontend, navigateur (13, si Playwright est installé)
```

## Arborescence
```
lumina_server.py            serveur (API, auth, Live, base de données)
www/                        frontend servi tel quel (et copié dans l'APK) : index.html, v7.css, ui7.js, live.js, sw.js, icons/
android/                    projet Capacitor (permissions caméra/micro, icônes Lumina)
migrate_sqlite_to_neon.py   migration historique SQLite → Neon (inchangée, ne pas relancer sans raison)
tests/                      backend (unittest), boot du frontend (Node), navigateur (Playwright)
scripts/                    run_local.sh, run_tests.sh, compare_with_v6.sh, pg_smoke.py
docs/                       RAPPORT_V7.md, MIGRATION.md, ROLLBACK.md, v6.1_to_v7.diff
```
Créé par Issa Amakendé Abdoulaye Koné.
