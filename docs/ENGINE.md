# Moteur d'agent de Lumina (phase 1)

Nom de code de développement : « cognitive engine ». Ce nom n'apparaît nulle part dans l'interface.

## Ce qui est fait (phase 1 : intention et orchestration d'outils)
- **Date et heure réelles** : à chaque requête, le serveur injecte la date de son horloge (et l'heure locale de l'utilisateur, envoyée par le navigateur) dans les instructions du modèle, y compris en mode Live. Lumina ne se fie plus à l'année de ses données d'entraînement. Les réponses qui dépendent de l'heure ou d'outils ne sont jamais servies depuis le cache.
- **Agent à outils** : quand « Recherche web » est activée, le modèle choisit lui-même ses outils, sans mot-clé :
  `get_datetime`, `web_search`, `read_page` (pages et PDF publics), `recent_news`.
  Il peut enchaîner plusieurs outils, reformuler ses recherches et recouper les sources. Le serveur borne tout : 4 étapes, 6 outils, 35 secondes, quotas de recherche par plan.
- **Repli automatique** : si le fournisseur refuse les outils (modèle ou paramètres incompatibles), Lumina retombe sur l'ancien mode (une recherche par mots-clés), sans rien afficher de faux.
- **Honnêteté** : consignes interdisant de prétendre avoir cherché sans appel réel, et nettoyage côté serveur des balises `<function_calls>` que certains modèles écrivent en texte brut.
- **Sécurité** : le contenu des pages et des résultats est traité comme donnée non fiable ; lecture de pages avec protection contre l'accès au réseau interne ; pas d'action sensible possible (les outils sont en lecture seule).
- **Archive d'actualités** : flux RSS/Atom (France 24, RFI, BBC Afrique, Le Monde, Al Jazeera par défaut), stockés dans la table `news_items`, rafraîchis toutes les 30 minutes tant que le serveur tourne et à la demande si l'archive a plus de 30 minutes. Conservation : 14 jours. Un flux en panne n'arrête pas les autres.
- **Sources** : l'agent renvoie les sources réellement consultées (titre, site, extrait, page lue ou non) ; l'interface les affiche déjà (« Lu N pages »). La réponse contient aussi une liste `activity` (« Recherche : … », « Lecture : … ») ; elle n'est pas encore affichée.

## Ce qui n'est pas fait (phases suivantes de la fiche de départ)
| Module | État |
|---|---|
| Intent Engine, Tool Orchestrator | **fait en version simple** : le modèle choisit ses outils. Pas de planificateur séparé. |
| Web Intelligence, Source & Evidence | **partiel** : recherche, lecture de pages, sources réelles. Pas de recherches parallèles ni de comparaison automatique des contradictions ; pas de date de publication ni de favicon ; un seul moteur de recherche payant (Tavily) avec repli DuckDuckGo/Wikipédia. |
| Environment Awareness | **partiel** : date et heure, état des outils côté serveur. Pas de connaissance de la page ouverte ni de l'état des API. |
| Deep Research | non commencé |
| Creative Engine (remplacer Pollinations) | non commencé |
| Music Intelligence | non commencé (génération de musique désactivée) |
| Vision Engine | existant (photos), pas retravaillé |
| Provider Manager | non commencé : les modèles et le moteur de recherche sont encore configurés directement |
| Journal d'activité affiché pendant le travail | non fait : demande un envoi en flux continu |

## Configuration
Voir `.env.example` : `AGENT_ENABLED`, `AGENT_MODELS`, `NEWS_FEEDS`, `NEWS_REFRESH_MIN`, `TAVILY_API_KEY` (docs/BILLING.md pour les limites de recherche par plan).
Retour arrière : `AGENT_ENABLED=0` ; migration additive (`DROP TABLE news_items;`).

## Tests
`python -m unittest tests.test_engine` : 15 tests (date réelle et décalage horaire, nettoyage des balises, boucle d'outils bornée, arguments invalides, repli, analyse RSS/Atom, flux dangereux refusés, archive).
**Non testé** : les appels réels à Groq avec outils (le comportement dépend du modèle), les adresses des flux (à vérifier une par une), Tavily, PostgreSQL.
