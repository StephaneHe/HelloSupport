# User requirements

Every user request about a feature, the documentation or the behavior of HelloSupport is recorded
here with its date, the request **verbatim** (in the language it was made, French) and the automated
test that protects it. These tests are part of the default `pytest` suite, which is replayed before
and after every change.

**A user-requirement test may not be removed or weakened without the user's explicit agreement.**

| ID | Date | Request (verbatim) | Requirement | Test(s) |
|---|---|---|---|---|
| UR-001 | 2026-10-04 | « le diagramme sort mal, peux-tu le faire avec Mermaid ou générer une image directement ? » | Architecture diagrams are Mermaid (rendered by the docs site and GitHub), not ASCII art. | `tests/test_user_requirements.py::test_ur001_architecture_diagrams_are_mermaid_not_ascii_art` |
| UR-002 | 2026-10-04 | « Si les catégories sont fixes, autant les faire figurer dans le schéma. » | The main diagram shows the five triage categories and their paths. | `tests/test_user_requirements.py::test_ur002_diagrams_show_the_five_triage_categories` |
| UR-003 | 2026-10-04 | « je ne vois pas de boucle dans le schéma… les agents ne devraient-ils pas être plus marqués ? » | Agents, router and code are visually typed; the agent loop is drawn; a legend explains the shapes. | `tests/test_user_requirements.py::test_ur003_diagrams_mark_agents_router_and_loops`, `::test_ur003_agent_loop_diagram_and_legend_exist` |
| UR-004 | 2026-10-04 | « out_of_scope et vague vont directement au technicien » (decision: yes) | `out_of_scope` and `vague` questions skip the documentalist; `documentation` still uses it. | `tests/test_workflow_fake_llm.py::test_out_of_scope_and_vague_skip_the_documentalist`, `::test_documentation_still_goes_through_the_documentalist` |
| UR-005 | 2026-10-04 | « démo web … pipeline réel, trace en direct » | Web demo running the real pipeline with a live SSE trace, scenario switch, one question at a time, clear errors. | `tests/test_web.py` (all tests) |
| UR-006 | 2026-10-04 | « Documentation de HelloSupport : il y en a en anglais et en français. Passe tout en anglais. » | **Documentation entirely in English.** | `tests/test_user_requirements.py::test_ur006_published_documentation_is_in_english`, `::test_ur006_language_check_detects_french` |
| UR-007 | 2026-10-04 | « Corrige les écarts doc ↔ code relevés dans docs/REVIEW_DOC_CODE.md […] Si un écart révèle un bug de code, corrige-le avec un test » | The documentation matches the code; each code bug found by the review is fixed and locked by a test: daily re-seed of the incidents database (F-1), the C6 status-claim check (F-3), the required-tool fall-through trace (I-1), the web path (U-6), and the guardrails that had no test (F-4). | `tests/test_guardrails.py` (all tests), `tests/test_cases_postprocess.py::test_status_assertion_ignores_suggested_checks_and_catches_hedged_claims` |
| UR-008 | 2026-10-04 | « Je voudrais ajouter la doc au git, à la manière de git professionnel. » | **Documentation versioned and published professionally**: `mkdocs.yml` and the pages are in git, the site is built in strict mode in CI and published on GitHub Pages, one version per release; private and local-only content is never published. | `tests/test_user_requirements.py::test_ur008_docs_site_builds_in_strict_mode_without_ignored_files`, `::test_ur008_published_site_config_references_nothing_private`, `::test_ur008_ci_builds_strictly_and_publishes_versioned_docs`, `::test_ur008_no_personal_host_or_path_in_tracked_files` |
| UR-009 | 2026-10-04 | « Puis vérifie que le README est correct et assez complet, et rédigé de manière professionnelle en anglais. » | **Professional README in English**: complete set of sections (quick start to author), link and badge to the online documentation, current version badge, valid links; English checked by UR-006. | `tests/test_user_requirements.py::test_ur009_readme_has_the_expected_sections_and_docs_link`, `::test_ur009_readme_links_are_valid`, `::test_ur006_published_documentation_is_in_english[README.md]` |

UR-001 to UR-005 were made before this file existed; they are recorded retroactively with the tests
that already protected them (UR-004, UR-005) or that were added for them (UR-001 to UR-003).

## UR-006 — how the language check works

Simple, dependency-free detection: for each published Markdown file (`README.md`, `CHANGELOG.md`,
`TODO_LIST.md`, `docs/*.md`, `docs/bench/*.md`, `data/kb/*.md`), count common French function words
(*le, la, les, des, est, pour, avec…*) against common English ones (*the, of, and, is, for, with…*).
A file fails if French words exceed **10 %** of the total. The French originals of these documents
scored 76–100 %; the English versions score 0–6 %.

Documented exceptions (removed before counting):

- **Fenced and inline code** — terminal transcripts (e.g. the session in `docs/DEMO.md`), commands, identifiers.
- **Quoted text** (`"…"`, `“…”`, `« … »`) — the validation questions are French on purpose: they are
  test data for cross-lingual retrieval over the English knowledge base. The verbatim requests above
  are quoted for the same reason.
- **`## Answers` sections of `docs/bench/*.md`** — raw model output, kept verbatim, in the language of the question.
- **Not published, not checked**: `CLAUDE.md` (local agent instructions) and `private/`.
