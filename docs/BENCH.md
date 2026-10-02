# BENCH — mesures et observations

> Chiffres **mesurés** sur la machine de dev (Windows 11, RTX 2070 Super 8 Go, Python 3.12,
> torch 2.6.0+cu124), sauf mention contraire. Mesures ponctuelles : un seul passage, pas de
> statistiques. Elles servent à raisonner, pas à conclure sur la performance en général.

## J1 — RAG : recherche vectorielle puis reranking (2026-10-02)

Pipeline : 12 sections (3 fiches × 4) → `paraphrase-multilingual-MiniLM-L12-v2` → Chroma
(cosinus, top-5) → `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` → top-2. Device : `cuda`.

Commande : `hello-support search "<question>"` (colonnes : rang final, rang vectoriel, cosinus,
score du reranker).

### « connexion refusée postgres » (FR, fiches en anglais)

| final | vecteur | cosinus | rerank | section |
|---|---|---|---|---|
| **1** | 2 | 0.507 | 7.41 | postgres_connection.md#Service status |
| **2** | 5 | 0.465 | 7.30 | postgres_connection.md#Symptoms |
| 3 | 1 | 0.519 | 2.70 | postgres_connection.md#Checks |
| 4 | 3 | 0.486 | -2.03 | nginx_unavailable.md#Service status |
| 5 | 4 | 0.474 | -2.92 | nginx_unavailable.md#Symptoms |

→ **Le reranking change l'ordre** : la section *Symptoms* (qui contient littéralement
« connection refused ») passe de la 5ᵉ à la 2ᵉ place. Deux sections **nginx** étaient devant
elle en recherche vectorielle seule. Sans reranking, le top-2 aurait été *Checks* et
*Service status* : correct, mais sans la section symptômes.

### « My website shows 502 Bad Gateway »

| final | vecteur | cosinus | rerank | section |
|---|---|---|---|---|
| **1** | 1 | 0.600 | 3.88 | nginx_unavailable.md#Symptoms |
| **2** | 5 | 0.451 | -4.30 | nginx_unavailable.md#Checks |
| 3 | 2 | 0.503 | -7.08 | nginx_unavailable.md#Service status |

→ *Checks* (qui explique 502 = upstream en panne) passe de la 5ᵉ à la 2ᵉ place.

### « Que vérifier si Redis répond NOAUTH ? »

Top-2 : `redis_unreachable.md#Checks` (6.08), puis `#Symptoms` (-0.76, remontée du rang 3 au rang 2).

### « Kafka consumer lag is growing » (hors base)

| final | vecteur | cosinus | rerank | section |
|---|---|---|---|---|
| 1 | 2 | 0.122 | -9.25 | redis_unreachable.md#Symptoms |
| 2 | 3 | 0.120 | -9.65 | redis_unreachable.md#Limits |
| 5 | 1 | 0.212 | -10.56 | postgres_connection.md#Limits |

→ La recherche vectorielle **renvoie toujours des voisins**, même quand rien ne correspond.
Tous les scores du reranker sont ≤ -9.2, alors que les passages utiles des autres requêtes
sont ≥ -4.3. D'où un seuil grossier `RELEVANCE_THRESHOLD = -5` qui marque les passages
« hors sujet ». Il permet à l'agent de répondre « pas couvert » (cas C5).

### Latences (J1)

| Étape | Mesure |
|---|---|
| Import de `sentence_transformers` (à froid) | ~15 s (coût fixe local : chargement de `transformers`, pas du réseau) |
| Chargement complet du `Retriever` (imports + 2 modèles sur GPU + Chroma + échauffement) | ~27 s |
| Première requête sans échauffement (initialisation des kernels CUDA) | ~2,9 s |
| Requête après échauffement (encodage + Chroma + reranking de 5 paires) | ~0,4–0,6 s |
| Construction de l'index (12 sections) | incluse dans le premier chargement ; réutilisé ensuite (empreinte du contenu) |

Le coût de chargement est payé **une fois par session** du serveur MCP (J2), pas à chaque question.

## J3 — Agents + orchestration : premiers essais réels (2026-10-02)

Modèle par défaut : `qwen2.5-7b-instruct` (Q4_K_M), température 0. Une exécution par cas :
**ce n'est pas encore l'évaluation J4**. Les traces complètes sont dans `runs/` (gitignoré).

### Le modèle choisit-il d'observer ? (avant le triage, cf. D-17)

Entrée réelle du technicien (question + brief + 3 passages), outils proposés en `tool_choice=auto`,
3 essais :

| Modèle | Entrée complète | Sans brief | Question en dernier |
|---|---|---|---|
| Qwen2.5-7B | 0/3 | 0/3 | 0/3 |
| Qwen3-4B-2507 | 0/3 | 0/3 | 0/3 |

### Triage par sortie structurée (6 questions types)

| Modèle | Correct | Erreurs |
|---|---|---|
| Qwen2.5-7B | 4/6 | Kafka → `vague` (attendu `out_of_scope`) ; « ça marche pas » → `malfunction` sans service (requalifié en `vague` par le code) |
| Qwen3-4B-2507 | 4/6 | « ne parvient plus à se connecter… que vérifier ? » → `documentation` (prompt précisé ensuite) ; « ça marche pas » → `malfunction/postgres` |

Latence du triage : ~0,3 s à chaud, ~3–9 s pour le premier appel (chargement du modèle par LM Studio).

### Exécutions de bout en bout après triage + garde-fous (7 B)

| Cas | Comportement observé | Durée totale |
|---|---|---|
| C1 postgres `stopped` | `get_service_status(postgres)` → `stopped` ; diagnostic « service arrêté, lire les logs avant de relancer », source `Service status` | ~41 s |
| C2 postgres `running` | → `running` (simulé) ; conclusion différente : réseau / config / identifiants | ~40 s |
| C3 Redis documentaire | aucun appel de statut ; liste de vérifications sourcées (une « Observation » inventée dans la 1ʳᵉ version, d'où la consigne ajoutée) | ~44 s |
| C4 incidents postgres 30 j | SQL valide `COUNT(*), MAX(resolved)` → `[3, 1]` ; « 3 incidents » ✔ ; « le dernier n'est pas résolu » est **vrai mais non déduit** du résultat ✘ | ~7 s |
| C5 « Mon Kafka est lent » | demande de précision, aucune fiche inventée | ~6,5 s |
| C5 « ça marche pas » | « Quel service ? » | ~32 s |
| C6 Redis `tool_error` | erreur d'outil tracée ; réponse « statut non vérifiable » + pistes sourcées ; avant correctif : 46 appels dupliqués en 18 s | ~40 s |

Sur ~40 s, ~21–27 s correspondent au **chargement du RAG** dans le serveur MCP (une fois par
session). Les appels LLM totalisent ~11–13 s pour 4–5 appels, et ~2 300–3 000 tokens en entrée.

## J4 — Validation : 6 cas × 3 exécutions × 2 modèles (2026-10-02)

Commande : `hello-support bench --models slm large --runs 3`. Vérifications automatiques par cas
(`src/hello_support/cases.py`), mesures **à chaud** (session MCP et modèle déjà chargés).
Rapports complets avec **toutes les réponses** : [`bench/bench-20261002-172401.md`](bench/bench-20261002-172401.md)
(avant correctifs) et [`bench/bench-20261002-173250.md`](bench/bench-20261002-173250.md) (après).

### Avant / après les correctifs de J4

| | SLM Qwen3-4B avant | SLM après | 7 B avant | 7 B après |
|---|---|---|---|---|
| Cas réussis | 7/18 | **15/18** | 10/18 | **18/18** |
| Vérifications réussies | 81/108 | 105/108 | 98/108 | 108/108 |

Correctifs entre les deux runs, chacun motivé par un échec observé :
- **D-22** : citations normalisées et mention de simulation ajoutée par le code ;
- **D-23** : requêtes SQL dans la même étape ;
- **D-24** : règles et exemples dans le triage.

Deux vérifications étaient elles-mêmes **fausses** et ont été corrigées :
- l'analyse des citations séparées par un espace ;
- un « statut affirmé » détecté dans une phrase conditionnelle « si le serveur Redis est arrêté ».

### Résultat final (run n° 2)

| Indicateur | `qwen/qwen3-4b-2507` | `qwen2.5-7b-instruct` |
|---|---|---|
| Cas réussis (toutes vérifications) | 15/18 | 18/18 |
| Vérifications réussies | 105/108 | 108/108 |
| Latence p50 / max par requête | 5.96 s / 11.52 s | 9.04 s / 15.65 s |
| Appels LLM par requête (moy.) | 4.5 | 4.22 |
| Tokens in / out par requête (moy.) | 2774 / 347 | 2602 / 391 |
| Débit de génération (tokens out / s LLM) | 57.9 | 45.3 |
| Requêtes / min (séquentiel) | 9.9 | 6.9 |
| Coût local | 0 € (électricité non comptée) | 0 € |
| Coût estimé si API OpenAI gpt-4o-mini, /1000 req. | ~0.62 $ | ~0.62 $ |
| Coût estimé si API Anthropic Claude Haiku 4.5, /1000 req. | ~4.51 $ | ~4.56 $ |

| Cas | SLM (réussites · latence p50) | 7 B |
|---|---|---|
| C1 PostgreSQL arrêté | 3/3 · 9.6 s | 3/3 · 13.7 s |
| C2 PostgreSQL actif | 3/3 · 9.0 s | 3/3 · 9.0 s |
| C3 Question documentaire | 3/3 · 5.7 s | 3/3 · 9.1 s |
| C4 Question data (SQL) | 3/3 · 3.5 s | 3/3 · 7.7 s |
| C5 Demande hors périmètre | 3/3 · 1.5 s | 3/3 · 2.1 s |
| C6 Outil en erreur | **0/3** · 6.6 s | 3/3 · 11.2 s |

**Échecs restants (SLM, C6)** : le SLM **invente des identifiants de source**
(`unreachable.md#Checks`, `[service_status#Service status]`) quand l'outil de statut échoue. Le
post-traitement les signale dans la trace, mais ne les corrige pas, et c'est voulu.

**Limites de lecture** :
- les vérifications par mots-clés sont grossières (D-21) ;
- température 0, donc les 3 exécutions sont très proches : la variance mesurée est surtout celle
  de la latence ;
- en relecture, le 7 B présente parfois les symptômes de la fiche comme des « logs observés »
  (C6), ce que les vérifications ne détectent pas.

Les **coûts cloud** sont des **estimations** : tokens mesurés × prix publics indicatifs
(`REFERENCE_PRICES_USD_PER_MTOK`, à revérifier), aucun appel ni compte.

Démarrage à froid d'une session (RAG + chargement du modèle par LM Studio) : 20–26 s.

## J5 — Débit du serving (2026-10-02)

Commande : `hello-support throughput --models slm large --concurrency 1 4 --requests 8`.
La même requête de génération (~160 tokens max, température 0,7) est envoyée 8 fois, une à la
fois puis par 4 en parallèle, au serveur LM Studio (RTX 2070 Super 8 Go).

| Modèle | Concurrence | Requêtes | Durée | Tokens out/s (agrégé) | Req/min | Latence p50 / max |
|---|---|---|---|---|---|---|
| `qwen/qwen3-4b-2507` | 1 | 8 | 8.61 s | 106.6 | 55.7 | 1.06 s / 1.18 s |
| `qwen/qwen3-4b-2507` | 4 | 8 | 5.34 s | 172.6 | 90.0 | 1.78 s / 4.17 s |
| `qwen2.5-7b-instruct` | 1 | 8 | 14.13 s | 71.1 | 34.0 | 1.62 s / 2.24 s |
| `qwen2.5-7b-instruct` | 4 | 8 | 8.26 s | 127.6 | 58.1 | 3.69 s / 6.29 s |

Lecture :
- **Taille du modèle** : à concurrence 1, le 4 B génère ~1,5× plus vite que le 7 B (107 contre
  71 tokens/s).
- **Concurrence** : à 4 requêtes simultanées, le débit agrégé est multiplié par **1,6 (4 B) à
  1,8 (7 B)**, mais la latence individuelle **double**. C'est le compromis débit / latence d'un
  serveur qui traite plusieurs requêtes en parallèle.
- **Écart avec le bench** : le débit de génération y est plus bas (58 et 45 tokens/s) parce que
  le temps LLM inclut le traitement de prompts de ~600–900 tokens (contexte RAG, résultats
  d'outils) et plusieurs appels courts.

Ce n'est pas un test de charge : une seule machine, LM Studio (outil desktop), 8 requêtes. Un vrai
test de débit se ferait avec vLLM (batching continu) et une montée en charge progressive
(« pour aller plus loin »).
