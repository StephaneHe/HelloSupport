# Démo de bout en bout (enregistrée le 2026-10-02)

Transcription brute de deux exécutions **à froid**, chacune avec un nouveau serveur MCP : modèle par
défaut `qwen2.5-7b-instruct`, LM Studio local, GPU RTX 2070 Super. Pour la rejouer, voir
[`../README.md`](../README.md) (section *Demo*). Le numéro de version affiché est celui du moment de
l'enregistrement.

À observer dans la 1ʳᵉ exécution :
1. **Triage** → `malfunction / postgres` (sortie JSON contrainte, D-17).
2. **Documentaliste** → `search_docs` : 3 sections reclassées par le reranker (D-09). Les ~14 s
   comprennent la fin du chargement du RAG dans le serveur MCP (D-15).
3. **Garde-fou en action** : le technicien répond d'abord **sans** appeler l'outil exigé. La
   réponse est **rejetée** (`answer discarded, retrying`), puis le modèle appelle
   `get_service_status` (D-18).
4. Le diagnostic s'appuie sur l'observation `stopped`, cite `postgres_connection.md#Service status`,
   et se termine par la mention construite par le code : « statut observé en simulation… aucune
   action corrective n'a été exécutée » (D-22).

À observer dans la 2ᵉ exécution (question de données) :
1. **Triage** → `history` : la branche conditionnelle saute le documentaliste (D-16).
2. Le modèle propose 5 requêtes. Le code en écarte 3 (doublons / plafond), puis en exécute 2 en
   lecture seule (D-13, D-18, D-23).
3. La réponse « 3 incidents, le dernier non résolu » est **déduite des lignes renvoyées**
   (`[[3]]`, `[[0]]`).

```text
$ hello-support --version
hello-support 1.7.0

$ hello-support ask "Mon application ne parvient plus à se connecter à PostgreSQL. Que dois-je vérifier ?" --scenario stopped
question: Mon application ne parvient plus à se connecter à PostgreSQL. Que dois-je vérifier ?
scenario: stopped  model: (default)

[   3.4s] triage        LLM 3.42s, tokens 393/22 -> route {'intent': 'malfunction', 'service': 'postgres'}
[   3.4s] documentalist >> active
[   4.0s] documentalist LLM 0.57s, tokens 414/23 -> proposes search_docs
[   4.0s] documentalist tool search_docs({"query": "PostgreSQL connection problems"})
[  17.8s] documentalist   ok in 13.83s: postgres_connection.md#Limits (rerank 10.0), postgres_connection.md#Symptoms (rerank 6.2), postgres_connection.md#Service status (rerank 6.0)
[  21.5s] documentalist LLM 3.71s, tokens 787/77 -> answers
[  21.5s] technician    >> active
[  26.4s] technician    LLM 4.86s, tokens 826/300 -> answers
[  26.4s] technician    LIMIT: a tool call was required but the model answered: answer discarded, retrying
[  26.8s] technician    LLM 0.36s, tokens 841/22 -> proposes get_service_status
[  26.8s] technician    tool get_service_status({"service_name": "postgres"})
[  26.8s] technician      ok in 0.00s: {"service": "postgres", "status": "stopped", "simulated": true, "scenario": "stopped"}
[  29.6s] technician    LLM 2.84s, tokens 707/183 -> answers

========================================================================
Observation: Le service PostgreSQL est enregistré comme arrêté postgres_connection.md#Service status. Cela signifie que les connexions sont immédiatement refusées.

Possible explanation: Comme le service est arrêté, il n'est pas en mesure de traiter les connexions entrantes. Il faut vérifier pourquoi le service a été arrêté (par exemple, espace disque saturé, plantage, maintenance, échec d'une mise à niveau) et consulter les journaux PostgreSQL pour plus de détails.

Suggested check: Examiner les logs PostgreSQL pour identifier la raison de l'arrêt du service. Si le service est arrêté en raison d'un problème critique, il ne devrait pas être redémarré sans résoudre cette cause sous-jacente.

Sources: postgres_connection.md#Service status

— Statut observé en simulation (scénario « stopped ») : postgres = stopped. Aucune action corrective n'a été exécutée.
========================================================================
model qwen2.5-7b-instruct | 31.93s total, LLM 6 calls 15.75s, tokens 3968/627, tools 2 calls 13.84s
trace: runs/20261002-173528.json

$ hello-support ask "Combien d'incidents postgres ces 30 derniers jours, et le dernier est-il résolu ?"
question: Combien d'incidents postgres ces 30 derniers jours, et le dernier est-il résolu ?
scenario: (default)  model: (default)

[   2.8s] triage        LLM 2.78s, tokens 395/21 -> route {'intent': 'history', 'service': 'postgres'}
[   2.8s] technician    >> active
[   7.3s] technician    LLM 4.55s, tokens 695/300 -> proposes query_incidents, query_incidents, query_incidents, query_incidents, query_incidents
[   7.3s] technician    LIMIT: 3 duplicate/extra tool call(s) dropped
[   7.3s] technician    tool query_incidents({"sql": "SELECT COUNT(*) FROM incidents WHERE service = 'postgres' AND started_at >= datetime('now', 'localtime', '-30 days')"})
[   7.3s] technician      ok in 0.01s: {"columns": ["COUNT(*)"], "rows": [[3]], "row_count": 1, "truncated": false}
[   7.3s] technician    tool query_incidents({"sql": "SELECT resolved FROM incidents WHERE service = 'postgres' AND started_at >= datetime('now', 'localtime', '-30 days') ORDER BY started_at DESC LIMIT 1"})
[   7.4s] technician      ok in 0.01s: {"columns": ["resolved"], "rows": [[0]], "row_count": 1, "truncated": false}
[   8.3s] technician    LLM 0.93s, tokens 603/49 -> answers

========================================================================
Observation: Selon les données de l'incidents database, il y a eu 3 incidents PostgreSQL ces 30 derniers jours. Le dernier incident n'est pas résolu.

Sources: incidents database [query_incidents]

— Aucune action corrective n'a été exécutée.
========================================================================
model qwen2.5-7b-instruct | 10.14s total, LLM 3 calls 8.26s, tokens 1693/370, tools 2 calls 0.01s
trace: runs/20261002-173541.json
```
