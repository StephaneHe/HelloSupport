# TODO_LIST — HelloSupport

Convention : `(+ date)` = ajout, `(✔ date)` = fait. Jalons définis dans `docs/SPEC.md` §5.

## Cadrage

- [x] Analyse d'une proposition initiale de projet minimal ; spec finale `docs/SPEC.md` (+ PDF) `(+ 2026-10-02)` `(✔ 2026-10-02)`
- [x] Spec validée (100 % local) ; ajout du livrable `DESIGN_DECISIONS.md` `(+ 2026-10-02)` `(✔ 2026-10-02)`
- [x] Télécharger les modèles LM Studio (SLM 3–4 B + qwen2.5-7b-instruct Q4_K_M) `(+ 2026-10-02)` `(✔ 2026-10-02)`

## Jalons

- [x] J0 — Socle (uv, version, llm.py, smoke test SLM + 7 B, tool calling factice) `(+ 2026-10-02)` `(✔ 2026-10-02)`
- [x] J1 — RAG (fiches, ST → Chroma → reranker, commande `search`, GPU) `(+ 2026-10-02)` `(✔ 2026-10-02)`
- [x] J2 — Données + MCP (scenarios, SQLite incidents, sql_guard, serveur MCP 3 outils) `(+ 2026-10-02)` `(✔ 2026-10-02)`
- [x] J3 — Agents + orchestration LangGraph (état, limites, trace) `(+ 2026-10-02)` `(✔ 2026-10-02)`
- [x] J4 — Corrections : C4 (raisonnement SQL incohérent) ; C3 (format sans « Observation ») ; sources sans altération (`Service_status`) `(+ 2026-10-02)` `(✔ 2026-10-02)`
- [x] J4 — Validation (6 cas réels + pytest LLM factice, BENCH.md) : 7 B 18/18, SLM 15/18 `(+ 2026-10-02)` `(✔ 2026-10-02)`
- [ ] Connu, non corrigé : le SLM invente des identifiants de source quand l'outil de statut échoue (C6) `(+ 2026-10-02)`
- [x] J5 — Bench SLM vs 7 B, DESIGN_DECISIONS consolidé + PDF, README, release `(+ 2026-10-02)` `(✔ 2026-10-02)`
- [x] Publication open source : README anglais, licence MIT, historique neuf sans documents personnels `(+ 2026-10-02)` `(✔ 2026-10-02)`

## Journal de décisions

- [x] Ajouter les entrées `D-xx` à chaque jalon dans `docs/DESIGN_DECISIONS.md` (28 décisions, consolidé + PDF) `(+ 2026-10-02)` `(✔ 2026-10-02)`

## Pistes (hors hello world, cf. SPEC §10)

- [ ] Mesurer l'hybride « triage par le SLM, réponse par le 7 B » avec `hello-support bench` (D-25) `(+ 2026-10-02)`
- [ ] PostgreSQL + pgvector (incidents et vecteurs dans le même moteur) `(+ 2026-10-02)`
- [ ] Checkpointer LangGraph (reprise, human-in-the-loop) `(+ 2026-10-02)`
- [ ] Évaluation RAG (recall@k, MRR avant/après rerank) sur un jeu de questions `(+ 2026-10-02)`
- [ ] MCP en streamable HTTP (serveur d'outils séparé) ; vLLM pour un vrai test de débit `(+ 2026-10-02)`
