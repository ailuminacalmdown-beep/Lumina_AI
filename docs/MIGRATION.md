# Migration de schéma v6.1 → v7

**Type : additive uniquement.** Exécutée automatiquement au démarrage par `ensure_schema()` (idempotente : `IF NOT EXISTS`).
Testée sur SQLite (tests automatisés). **Non testée sur PostgreSQL/Neon** faute de base de test : utiliser `scripts/pg_smoke.py`
sur une branche de test avant la production.

| Objet | SQLite | PostgreSQL |
|---|---|---|
| Table `feedback` (retours « j'aime », « je n'aime pas », signalements) | `id INTEGER PK AUTOINCREMENT`, `user_id` FK → `users` **ON DELETE CASCADE** | `id BIGINT IDENTITY`, `user_id BIGINT` FK → `users` **ON DELETE CASCADE** |
| Index `idx_sessions_user` (sessions par utilisateur) | oui | oui |
| Index `idx_sessions_created` (purge des sessions expirées) | oui | oui |

- Aucune colonne ajoutée ou modifiée sur `users`, `sessions`, `user_knowledge`, `conv_memories`, `memories`.
- Aucune donnée existante n'est lue, déplacée ni supprimée.
- Les sessions existantes restent valides (elles expirent selon `SESSION_TTL_DAYS`, 30 jours par défaut, à partir de leur `created_at`).
- Les tokens de session restent stockés en clair dans la base (comme en v6.1) : les hacher invaliderait toutes les sessions
  actives ; amélioration recommandée pour une version ultérieure.
- `migrate_sqlite_to_neon.py` n'est pas modifié (idempotent, une transaction, aucun `DROP`/`TRUNCATE`). Ne pas le relancer sans raison.

**Retour arrière** : voir `docs/ROLLBACK.md`.
