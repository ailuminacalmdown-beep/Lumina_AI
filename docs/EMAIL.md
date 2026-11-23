# Emails : vérification d'adresse et mot de passe oublié (v9)

## Comment ça marche
- À l'inscription, Lumina envoie un **code à 6 chiffres** (valable 15 minutes, 5 essais). Tant qu'il n'est pas saisi, le chat et le mode Live répondent « Vérifie ton adresse email ».
- « Mot de passe oublié ? » sur l'écran de connexion : email, puis code et nouveau mot de passe. Le changement **ferme toutes les sessions ouvertes** du compte.
- On saisit un code dans l'appli (pas de lien) : ça marche dans l'application Android et dans le navigateur.
- Sécurité : seul le hash du code est stocké ; un nouveau code annule l'ancien ; la réponse à « mot de passe oublié » est la même que l'email existe ou non ; limites par adresse IP, par email et par compte.
- **Les comptes existants sont considérés comme vérifiés** (aucun blocage pour tes utilisateurs actuels).
- **Sans configuration d'email, rien ne change** : pas de vérification, et « mot de passe oublié » répond que le service n'est pas disponible.

## Ce qu'il te faut
1. **Un nom de domaine** à toi (par exemple `lumina.ton-domaine`). Il faut y ajouter les enregistrements DNS (SPF, DKIM) fournis par le service d'envoi, sinon les emails finissent en spam ou sont refusés. Envoyer depuis une adresse `@gmail.com` par un service tiers n'est pas fiable.
2. **Un service d'envoi par API** (HTTPS, donc compatible avec les hébergeurs qui bloquent le SMTP). Le code gère `resend` et `brevo`.

| Service | Offre gratuite (sources secondaires, à confirmer sur leur site) | Remarques |
|---|---|---|
| Resend | 3 000 emails/mois, 100/jour, 1 domaine | emails sans publicité ; le plafond de 100/jour limite à environ 100 inscriptions et demandes de code par jour |
| Brevo | 300 emails/jour | une mention Brevo est ajoutée au pied des emails du plan gratuit |
| Mailgun | 100/jour, 1 domaine | surtout un bac à sable |
| SendGrid | plus de plan gratuit permanent (essai de 60 jours) | à éviter pour démarrer |

Recommandation : **Resend** pour la bêta (propre, simple), **Brevo** si le volume dépasse 100 emails par jour.

## Configuration (variables Render, jamais dans le code)
```
EMAIL_PROVIDER=resend            # ou brevo
EMAIL_API_KEY=...                # secret du service
EMAIL_FROM=no-reply@ton-domaine  # adresse d'un domaine vérifié chez le service
EMAIL_FROM_NAME=Lumina
```

## Tester en local sans service d'email
`EMAIL_PROVIDER=console` affiche les emails (donc les codes) dans le terminal. **Uniquement pour tes tests** : il est ignoré sur Render. Lance ensuite `sh scripts/run_local.sh`, crée un compte, lis le code dans le terminal.

## Migration et retour arrière
Additive : table `email_tokens` et colonne `users.email_verified` (valeur 1 pour les comptes existants). Retour arrière : `DROP TABLE email_tokens;` (la colonne peut rester).

## Tests
`python -m unittest tests.test_email_codes` (7 tests : code correct consommé une fois, mauvais codes et verrouillage après 5 essais, expiration, remplacement, séparation vérification/réinitialisation, hash seul stocké).
**Non testé** : l'envoi réel via Resend ou Brevo (pas de réseau ici), les routes HTTP avec Flask, PostgreSQL.
