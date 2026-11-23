# Retour à la version précédente

La v7 n'a rien supprimé de ta version d'origine et n'a rien poussé ni déployé. Pour revenir en arrière :

## Code (Git / Render)
1. **Render** : onglet *Events* → ancien déploiement → **Rollback**. C'est le retour le plus rapide.
2. **Git** : `git revert <commit-v7>` (ou `git checkout <ancien-commit> -- .` puis commit). Ton ancien code reste intact
   dans l'historique ; v7 se développe de préférence sur une branche (`git switch -c lumina-v7`).
3. **Fichiers locaux** : l'ancien projet n'a pas été modifié. `scripts/compare_with_v6.sh ~/assistant_pwa` affiche
   toutes les différences ; `docs/v6.1_to_v7.diff` est le même comparatif en fichier.

## Base de données
La migration v7 est **additive** : elle n'a modifié aucune table existante. L'ancien code fonctionne donc sans rien faire
avec la base migrée (il ignore la table `feedback`). Retour complet (facultatif, supprime les retours utilisateurs enregistrés) :

```sql
DROP TABLE IF EXISTS feedback;
DROP INDEX IF EXISTS idx_sessions_user;
DROP INDEX IF EXISTS idx_sessions_created;
```

Si besoin d'un retour *intégral* de la base, restaure la **branche Neon de sauvegarde** créée avant le déploiement
(c'est pour cela que `DEPLOY.md` la demande).

## Effets visibles pour les utilisateurs au retour
- Les sessions v7 restent valides (même table `sessions`).
- La version 6.1 réintroduira ses défauts connus (voir `docs/RAPPORT_V7.md`) : ne la redéploie pas telle quelle sans les correctifs C1/C2.

## Android
Réinstalle l'ancien APK (ou repars de l'ancien dossier `android/`). Les permissions ajoutées par la v7 sont inoffensives
si elles restent déclarées.
