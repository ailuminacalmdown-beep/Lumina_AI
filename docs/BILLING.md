# Plans Gratuit / Pro / Max (v8)

## État réel
- Le plan est calculé **uniquement côté serveur** (table `subscriptions`). Le frontend ne peut rien activer.
- **Aucun paiement n'est branché.** Pro et Max ne s'obtiennent que par activation manuelle (ci-dessous). Prestataire à choisir ; il faudra un webhook signé, un contrôle du montant et des doublons, et des tests de bout en bout avant toute mise en service. Le numéro de versement ne doit jamais apparaître dans l'appli ni dans le code.
- Prix affichés : Pro 6 €/mois, Max 15 €/mois (configurables : `PRICE_PRO_EUR`, `PRICE_MAX_EUR`). Ce sont des chiffres à valider, rien ne peut être acheté.

## Limites (point de départ, à recalibrer avec le coût réel de l'API)
Stratégie d'Anthropic en plus petit : un plafond **par jour** et un plafond **par semaine glissante**, des paliers qui sont des multiples les uns des autres, et un message avancé qui consomme plus qu'un message simple.
Unité : message simple = 1 ; message qui passe par le modèle Prime (demande complexe, recherche, photo) = 3.

| | Gratuit | Pro (6 €) | Max (15 €) |
|---|---|---|---|
| Unités / jour | 25 | 150 | 450 |
| Unités / semaine | 125 | 750 | 2 250 |
| Analyses de photos / jour | 3 | 25 | 75 |

Max = 3 × Pro pour 2,5 × le prix. Le plafond hebdomadaire vaut 5 jours pleins : il empêche de consommer tout, tous les jours. Un échec serveur ne consomme rien. Le jour est le jour UTC (= heure de Bamako).

Variables (Render > Environment), 0 = illimité : `FREE_DAILY_UNITS`, `FREE_WEEKLY_UNITS`, `FREE_DAILY_IMAGES`, idem pour `PRO_` et `MAX_`.
`LIMITS_ENABLED=0` désactive toutes les limites (`scripts/run_local.sh` le fait par défaut pour tes tests locaux). **En production la valeur par défaut est 1 : les utilisateurs existants deviennent « Gratuit » avec ces limites dès le déploiement.**

Non limités pour l'instant : le mode Live, la génération d'images (service externe appelé depuis le navigateur) et la musique. Ils demandent chacun leur propre mécanisme.

## Activer / retirer un abonnement manuellement
Depuis Termux, sans écrire le token dans un fichier suivi par Git ni le coller dans une conversation :
```bash
read -rs ADMIN_TOKEN; export ADMIN_TOKEN
curl -s -X POST https://TON-SERVICE/admin/premium/grant \
  -H "X-Admin-Token: $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"email":"utilisateur@exemple.com","plan":"pro","days":30,"reference":"MANUEL-2026-001","reason":"Paiement vérifié à la main"}'
```
- `plan` : `pro` (défaut) ou `max`. `reason` (5 caractères minimum) est obligatoire et journalisée dans `audit_logs`.
- Une même `reference` pour un même utilisateur n'active **jamais deux fois** (réponse `duplicate`).
- Une nouvelle période du même plan s'ajoute à la suite. Si l'utilisateur a Pro et Max actifs, le meilleur plan s'applique.
- Retrait : `POST /admin/premium/revoke` avec `{"email":"…","reason":"…"}`.
- L'ancien plan `premium` (première version de v8) est traité comme `pro`.

## Migration et retour arrière
Additive et idempotente (créée au démarrage) : `subscriptions`, `usage_daily`, `audit_logs`. Aucune donnée existante n'est modifiée.
Retour arrière : `DROP TABLE subscriptions; DROP TABLE usage_daily; DROP TABLE audit_logs;` puis redéployer la version précédente.

## Tests
`python -m unittest tests.test_billing` (9 tests : plans, plafonds jour et semaine, unités, photos, remboursement, expiration, révocation).
Non testé : les routes HTTP avec Flask et Groq, PostgreSQL/Neon, tout paiement réel.
