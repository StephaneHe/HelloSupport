"""The six validation cases of docs/SPEC.md §6, with automatic checks on the final state.

The checks are deliberately simple and observable (route, tools called, tool results, words in
the answer, citations). They catch regressions and gross failures; they do not replace reading
the answers, which are kept in the benchmark report.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

KNOWN_SECTIONS = {
    f"{doc}#{sec}"
    for doc in ("postgres_connection.md", "nginx_unavailable.md", "redis_unreachable.md")
    for sec in ("Symptoms", "Checks", "Service status", "Limits")
}
CITATION_START = re.compile(r"([\w-]+\.md)#")
SECTIONS = ("Symptoms", "Checks", "Service status", "Limits")


def _tools(state: dict, name: str) -> list[dict]:
    return [o for o in state.get("observations", []) if o["tool"] == name]


def _answer(state: dict) -> str:
    return (state.get("answer") or "").lower()


def _has(state: dict, *words: str) -> bool:
    a = _answer(state)
    return any(w in a for w in words)


def citations(answer: str) -> list[str]:
    """Every `<file>.md#...` reference, read as file + the known section it starts with (or the raw word)."""
    answer = answer or ""
    out = []
    for m in CITATION_START.finditer(answer):
        rest = answer[m.end():]
        section = next((s for s in SECTIONS if rest.startswith(s)), re.match(r"[\w ]*", rest).group(0).strip())
        out.append(f"{m.group(1)}#{section}")
    return out


def cites_only_known_sections(state: dict) -> bool:
    return all(c in KNOWN_SECTIONS for c in citations(state.get("answer", "")))


def asserts_status(state: dict) -> bool:
    """True if the answer states a service status as a fact (conditional 'si ... est arrêté' excluded)."""
    a = _answer(state)
    for m in re.finditer(r"(redis|service|serveur|postgresql|nginx) (est|is) (arrêté|en cours d'exécution|stopped|"
                         r"running|démarré)", a):
        if not re.search(r"\b(si|if)\b[^.]{0,30}$", a[max(0, m.start() - 35):m.start()]):
            return True
    return False


def french(state: dict) -> bool:
    return len(re.findall(r"\b(le|la|les|est|de|du|des|vérifiez|pas)\b", _answer(state))) >= 3


def status_observed(state: dict, service: str, status: str) -> bool:
    return any(o["ok"] and o["arguments"].get("service_name") == service and o["result"].get("status") == status
               for o in _tools(state, "get_service_status"))


@dataclass
class Case:
    id: str
    title: str
    question: str
    scenario: str
    checks: dict[str, Callable[[dict], bool]]


CASES = [
    Case("C1", "PostgreSQL arrêté",
         "Mon application ne parvient plus à se connecter à PostgreSQL. Que dois-je vérifier ?", "stopped", {
             "route=malfunction/postgres": lambda s: s["route"] == {"intent": "malfunction", "service": "postgres"},
             "statut observé = stopped": lambda s: status_observed(s, "postgres", "stopped"),
             "réponse dit « arrêté »": lambda s: _has(s, "arrêté", "arrête", "stopped", "stoppé"),
             "dit « simulé »": lambda s: _has(s, "simul"),
             "cite une fiche postgres": lambda s: "postgres_connection.md" in _answer(s),
             "citations exactes": cites_only_known_sections,
             "en français": french,
         }),
    Case("C2", "PostgreSQL actif",
         "Mon application ne parvient plus à se connecter à PostgreSQL. Que dois-je vérifier ?", "running", {
             "statut observé = running": lambda s: status_observed(s, "postgres", "running"),
             "réponse dit « en cours d'exécution »": lambda s: _has(s, "en cours d", "running", "actif", "fonctionne",
                                                                    "démarré", "en marche"),
             "pas de panne inventée": lambda s: not _has(s, "est arrêté", "a été arrêté", "est stoppé"),
             "piste config/réseau/identifiants": lambda s: _has(s, "identifiant", "réseau", "configuration",
                                                                "pg_hba", "mot de passe", "port"),
             "citations exactes": cites_only_known_sections,
             "en français": french,
         }),
    Case("C3", "Question documentaire",
         "Quelles vérifications faire pour un Redis inaccessible ?", "stopped", {
             "route=documentation": lambda s: s["route"]["intent"] == "documentation",
             "aucun appel de statut": lambda s: not _tools(s, "get_service_status"),
             "cite la fiche redis": lambda s: "redis_unreachable.md" in _answer(s),
             "mentionne redis-cli ping": lambda s: _has(s, "ping", "redis-cli"),
             "citations exactes": cites_only_known_sections,
             "en français": french,
         }),
    Case("C4", "Question data (SQL)",
         "Combien d'incidents postgres ces 30 derniers jours, et le dernier est-il résolu ?", "stopped", {
             "route=history": lambda s: s["route"]["intent"] == "history",
             "SQL exécuté sans erreur": lambda s: any(o["ok"] for o in _tools(s, "query_incidents")),
             "réponse « 3 incidents »": lambda s: bool(re.search(r"\b(3|trois)\b", _answer(s))),
             "dernier incident lu (ORDER BY / MAX date)": lambda s: any(
                 re.search(r"order\s+by\s+started_at\s+desc|max\(\s*started_at", o["arguments"].get("sql", ""), re.I)
                 for o in _tools(s, "query_incidents") if o["ok"]),
             "réponse « non résolu »": lambda s: _has(s, "non résolu", "pas résolu", "pas encore résolu",
                                                      "toujours en cours", "unresolved", "not resolved"),
             "en français": french,
         }),
    Case("C5", "Demande hors périmètre",
         "Mon Kafka est lent, que faire ?", "stopped", {
             "route=out_of_scope|vague": lambda s: s["route"]["intent"] in ("out_of_scope", "vague"),
             "aucun outil statut/SQL": lambda s: not s.get("observations"),
             "aucune citation inventée": lambda s: not citations(s.get("answer", "")),
             "exprime la limite ou demande une précision": lambda s: "?" in _answer(s) or _has(
                 s, "ne couvre", "pas couvert", "hors", "uniquement", "seulement", "postgres", "ne peux pas"),
             "en français": french,
         }),
    Case("C6", "Outil en erreur",
         "Mon serveur Redis ne répond plus, que se passe-t-il ?", "tool_error", {
             "erreur d'outil tracée": lambda s: any("simulated tool failure" in e for e in s.get("errors", [])),
             "sortie contrôlée (status=done)": lambda s: s.get("status") == "done",
             "dit que la vérification a échoué": lambda s: _has(s, "pas pu", "impossible", "n'a pas", "échec",
                                                                "erreur", "indisponible", "ne peut pas", "pas été"),
             "pas de statut affirmé": lambda s: not asserts_status(s),
             "citations exactes": cites_only_known_sections,
             "en français": french,
         }),
]


def evaluate(case: Case, state: dict) -> dict[str, bool]:
    out = {}
    for name, check in case.checks.items():
        try:
            out[name] = bool(check(state))
        except Exception:
            out[name] = False
    return out
