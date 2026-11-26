# Publier Lumina : état réel et ce qui reste

Rédigé à partir de ce qui a été vérifié dans le code. **Rien de ce qui suit n'a été testé sur un téléphone, avec Groq, avec Tavily ou avec PostgreSQL par l'auteur de ce document.** « Fait » veut dire écrit et testé au niveau du code, pas validé en conditions réelles.

## Fait (v8)
- Plans Gratuit / Pro / Max avec plafonds jour et semaine, calculés côté serveur (`docs/BILLING.md`, 10 tests).
- Activation manuelle d'un abonnement par l'administrateur, avec justification obligatoire et journal d'audit.
- Lecture de liens et de pages avec protection contre l'accès au réseau interne ; lecture de PDF publics (pypdf).
- Recherche web avec lecture réelle des pages ; « Lu N pages » n'est affiché que pour des pages réellement lues, sinon « N sources ».
- Mot de passe oublié et vérification d'email par code à 6 chiffres (désactivés tant qu'aucun service d'envoi n'est configuré).
- Politique de confidentialité et conditions d'utilisation : pages publiques `/privacy` et `/terms`, lues aussi dans l'appli ; liens sur l'écran de connexion.
- Suppression de compte dans l'appli (Paramètres > Supprimer mon compte), avec effacement des conversations, de la mémoire, des retours, des sessions et des abonnements.
- Génération de musique retirée de l'interface (elle n'a jamais fonctionné) ; plus de boîtes de dialogue du navigateur.

## À faire avant d'ouvrir au public (par ordre d'importance)
1. **Tester sur ton téléphone**, en HTTPS (Render) et pas en `http://IP:5005` : le micro et la caméra sont bloqués par le navigateur sur une adresse non sécurisée. Parcours minimal : inscription, discussion, photo, lien, recherche web, projet, artéfact, Code, abonnement, suppression de compte.
2. **Lancer toute la suite de tests** avec Flask installé : `python -m unittest discover -s tests`. Je n'ai pas pu les exécuter tous ici.
3. **Configuration de production** (variables Render, jamais dans le code) : `GROQ_API_KEYS`, `DATABASE_URL` (Neon), `ADMIN_TOKEN`, `CORS_ORIGINS` limité à ton domaine (pas `*`), `TAVILY_API_KEY` (facultatif). Vérifier la persistance après un redémarrage et un redéploiement.
4. **Hébergement** : un service gratuit qui s'endort donne des premières réponses très lentes et des échecs. Pour des utilisateurs qui paient, prévoir une offre payante.
5. **Emails (mot de passe oublié, vérification d'adresse)** : le code est écrit et ses 7 tests passent, mais il faut un **nom de domaine**, un compte Resend ou Brevo et les enregistrements DNS, puis un essai réel (`docs/EMAIL.md`). Sans cela, il n'y a aucune récupération de compte.
6. **Paiements** : aucun n'est branché (prestataire à choisir, compte de versement à vérifier, webhook signé, tests de bout en bout). Tant que ce n'est pas fait, Pro et Max ne s'obtiennent que par activation manuelle.
7. **Relecture juridique** des deux pages par un professionnel du pays visé. Elles décrivent le fonctionnement réel, mais tu dois confirmer toi-même : que tu ne vends pas les données, que tu peux répondre aux demandes de copie par email, et l'identité de l'éditeur (complète-la si Æon est une société enregistrée).
8. **Google Play** (si tu publies là) : formulaire de sécurité des données, URL publique de la politique (`https://TON-DOMAINE/privacy`), et vérification des règles sur la suppression de compte (un lien web peut être exigé en plus du bouton dans l'appli) et sur la facturation des services numériques. Je n'ai pas vérifié ces règles à jour.
9. **Partie 9** : voix, micro, lecteur de musique récente (la génération de musique reste désactivée).

## Agent et actualités (v10)
Voir `docs/ENGINE.md`. À vérifier lors de tes essais : qu'une demande récente déclenche bien une recherche (le bandeau « Lu N pages » apparaît), qu'aucune balise `<function_calls>` ne s'affiche, que Lumina donne la bonne date. Si l'agent échoue, l'ancien mode prend le relais sans message d'erreur.

## Limites connues
- Mode Live, génération d'images et musique ne sont pas soumis aux quotas.
- La durée « Réflexion pendant N secondes » n'est disponible qu'à l'affichage de la réponse ; elle n'est pas conservée dans l'historique.
- La recherche gratuite (sans clé Tavily) s'appuie sur DuckDuckGo et Wikipédia : résultats limités.
- Tavily offre un volume gratuit limité par mois : il est réparti par plan (`*_DAILY_WEB`).
