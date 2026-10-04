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

## v1.10.0 — `out_of_scope` et `vague` sautent le documentaliste (2026-10-04)

Changement mesuré **avant** (tag `pre-1.10.0`, v1.9.3) et **après** (v1.10.0), dans les mêmes
conditions : un seul modèle chargé à la fois dans LM Studio (déchargement entre les séries), mesures à chaud.
Décision : D-30.

### Gain ciblé (5 exécutions par cas et par modèle)

Deux questions : `out_of_scope` = C5 « Mon Kafka est lent, que faire ? », `vague` = « ça marche pas, que faire ? ».

| Modèle | Catégorie | Réussite | Latence p50 | Appels LLM | Tokens in (moy.) | Tokens out (moy.) |
|---|---|---|---|---|---|---|
| Qwen3-4B | out_of_scope | 5/5 → 5/5 | 1,26 → **0,82 s (−35 %)** | 3 → 2 | 1 139 → 724 | 79 → 63 |
| Qwen3-4B | vague | 5/5 → 5/5 | 3,07 → **0,44 s (−86 %)** | 4 → 2 | 2 150 → 710 | 122 → 25 |
| Qwen2.5-7B | out_of_scope | 5/5 → 5/5 | 1,96 → 2,02 s (+3 %) | 3 → 2 | 1 136 → 724 | 110 → 104 |
| Qwen2.5-7B | vague | 5/5 → 5/5 | 3,87 → **1,74 s (−55 %)** | 4 → 2 | 1 968 → 710 | 147 → 83 |

Lecture :
- **`vague`** : l'ancien documentaliste **cherchait** (« it is not working » → 3 passages hors sujet) puis
  rédigeait un brief, soit 2 appels LLM et un appel d'outil. Ils sont supprimés, d'où −55 à −86 %.
- **`out_of_scope`** : l'ancien documentaliste répondait déjà **sans chercher** (1 appel court). Le gain
  est réel avec le 4B (−35 %), nul avec le 7B, dont la réponse du technicien (~100 tokens) domine la
  durée. Dans tous les cas, les tokens d'entrée baissent de 36 à 67 %.

### Bench complet (6 cas × 3, par modèle)

| | 4B avant | 4B après | 7B avant | 7B après |
|---|---|---|---|---|
| Cas réussis | 15/18 | 15/18 | 18/18 | 17/18 |
| C1 · C2 · C3 · C4 · C5 · C6 | 3·3·3·3·3·0 | 3·3·2·3·3·1 | 3·3·3·3·3·3 | 3·3·3·3·3·2 |
| C5 latence p50 | 1,43 s | 0,92 s | 2,06 s | 1,72 s |
| Latence p50 (toutes requêtes) | 9,5 s ⚠ | 4,4 s | 8,2 s | 7,8 s |

**Écarts sur des chemins inchangés, vérifiés comme préexistants** (re-mesurés sur l'ancien et le nouveau code) :

| Cas (chemin) | Modèle | Vérification qui échoue | Ancien code | Nouveau code |
|---|---|---|---|---|
| C6 (`malfunction`) | 7B | « dit que la vérification a échoué » : réponse « statut indéterminé… limitation de l'outil » | 8/10 (+ 5/5) | 8/10 (+ 4/5) |
| C3 (`documentation`) | 4B | citations exactes / en français | 5/8 | 7/8 |

Aucune régression attribuable au changement. Ces deux cas montrent une **instabilité de formulation**
des modèles malgré la température 0 (lots parallèles de LM Studio), combinée à des vérifications par
mots-clés grossières (D-21).

⚠ **Conditions machine** : LM Studio charge désormais les modèles avec un contexte par défaut de 25 600
tokens et 4 emplacements parallèles. L'option `-c` de `lms load` est ignorée, et la configuration de
LM Studio est hors du projet. La VRAM monte alors à ~7 Go et, avec les modèles d'embedding du serveur
MCP, le GPU sature par moments : appels LLM à 50–100 s dans la série « 4B avant », puis interruption
d'une seconde série à 590 s. Les **latences globales du 4B ne sont donc pas comparables** entre les deux
séries. Les comparaisons ciblées ci-dessus, aux écarts serrés, et les taux de réussite restent valables.

Rapports : avant [`bench-20261004-120325`](bench/bench-20261004-120325.md) (4B),
[`bench-20261004-121113`](bench/bench-20261004-121113.md) (7B) ; après
[`bench-20261004-121546`](bench/bench-20261004-121546.md) (4B), [`bench-20261004-122103`](bench/bench-20261004-122103.md)
(7B) ; contrôles C6 [`122349`](bench/bench-20261004-122349.md) (nouveau ×5), [`122531`](bench/bench-20261004-122531.md)
(ancien ×5), [`122757`](bench/bench-20261004-122757.md) (ancien ×10), [`124927`](bench/bench-20261004-124927.md) (nouveau ×10) ; contrôles C3 (4B) [`125119`](bench/bench-20261004-125119.md) (nouveau ×8), [`125223`](bench/bench-20261004-125223.md) (ancien ×8).

### Réglages LM Studio stabilisés (2026-10-04, après la mesure v1.10.0)

La saturation GPU signalée ci-dessus venait de l'**auto-ajustement du contexte** de LM Studio :
25 600 tokens × 4 emplacements parallèles, ~7 Go de VRAM pour le 4B. Une configuration par modèle
désactive l'auto-ajustement, fixe le **contexte à 8 192** et le **parallélisme à 1**. Elle est
appliquée aux chargements manuels comme aux chargements à la demande (JIT). VRAM avec le modèle
chargé et le serveur MCP actif : 4B ~4,6 Go, 7B ~5,9 Go.

Contrôle rapide après réglage, code v1.10.0 :

| Série | Réussite | Latence p50 / max | Comparaison |
|---|---|---|---|
| 4B, 6 cas × 3 ([`132504`](bench/bench-20261004-132504.md)) | 16/18 | **4,38 s / 7,6 s** | « 4B avant » saturé : 9,5 s / **100,9 s** |
| 7B, C1 + C3 × 3 ([`132635`](bench/bench-20261004-132635.md)) | 6/6 | 8,8 s / 11,2 s | C1 et C3 étaient les cas aux pics de 50–100 s |

Les latences sont de nouveau stables. Avec 1 seul emplacement parallèle, la mesure de débit à
concurrence 4 (section J5, faite avec 4 emplacements) ne serait plus reproduite telle quelle : les
requêtes seraient servies l'une après l'autre.

### Non-régression v1.11.0 (démo web)

Bench rapide après l'ajout de la démo web (`hello-support bench --models slm large --runs 1`, réglages LM Studio stabilisés) : **6/6 pour les deux modèles**, latence p50 4,9 s (4B) et 7,3 s (7B). Rapport : [`145500`](bench/bench-20261004-145500.md).
