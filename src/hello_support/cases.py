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


STATUS_CLAIM = re.compile(r"(redis|service|serveur|postgresql|nginx) (est|is|soit|semble être|seems to be|"
                          r"appears to be) (arrêté|en cours d'exécution|stopped|running|démarré)")
# A status right after these words is a condition or a suggested check, not a claim.
NOT_A_CLAIM = re.compile(r"\b(si|if|whether|vérifie[rz]? que|assurez-vous que|make sure|check that|ensure|"
                         r"verify that)\b[^.]{0,30}$")


def asserts_status(state: dict) -> bool:
    """True if the answer states a service status as a fact, hedged or not ('il semble que Redis soit en
    cours d'exécution'); conditions ('si ... est arrêté') and suggested checks ('vérifiez que le service
    est en cours d'exécution') are not claims."""
    a = _answer(state)
    return any(not NOT_A_CLAIM.search(a[max(0, m.start() - 40):m.start()]) for m in STATUS_CLAIM.finditer(a))


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
    Case("C1", "PostgreSQL stopped",
         "Mon application ne parvient plus à se connecter à PostgreSQL. Que dois-je vérifier ?", "stopped", {
             "route=malfunction/postgres": lambda s: s["route"] == {"intent": "malfunction", "service": "postgres"},
             "observed status = stopped": lambda s: status_observed(s, "postgres", "stopped"),
             "answer says \"stopped\"": lambda s: _has(s, "arrêté", "arrête", "stopped", "stoppé"),
             "says \"simulated\"": lambda s: _has(s, "simul"),
             "cites a postgres sheet": lambda s: "postgres_connection.md" in _answer(s),
             "exact citations": cites_only_known_sections,
             "in French": french,
         }),
    Case("C2", "PostgreSQL running",
         "Mon application ne parvient plus à se connecter à PostgreSQL. Que dois-je vérifier ?", "running", {
             "observed status = running": lambda s: status_observed(s, "postgres", "running"),
             "answer says \"running\"": lambda s: _has(s, "en cours d", "running", "actif", "fonctionne",
                                                                    "démarré", "en marche"),
             "no invented failure": lambda s: not _has(s, "est arrêté", "a été arrêté", "est stoppé"),
             "config/network/credentials lead": lambda s: _has(s, "identifiant", "réseau", "configuration",
                                                                "pg_hba", "mot de passe", "port"),
             "exact citations": cites_only_known_sections,
             "in French": french,
         }),
    Case("C3", "Documentation question",
         "Quelles vérifications faire pour un Redis inaccessible ?", "stopped", {
             "route=documentation": lambda s: s["route"]["intent"] == "documentation",
             "no status call": lambda s: not _tools(s, "get_service_status"),
             "cites the redis sheet": lambda s: "redis_unreachable.md" in _answer(s),
             "mentions redis-cli ping": lambda s: _has(s, "ping", "redis-cli"),
             "exact citations": cites_only_known_sections,
             "in French": french,
         }),
    Case("C4", "Data question (SQL)",
         "Combien d'incidents postgres ces 30 derniers jours, et le dernier est-il résolu ?", "stopped", {
             "route=history": lambda s: s["route"]["intent"] == "history",
             "SQL ran without error": lambda s: any(o["ok"] for o in _tools(s, "query_incidents")),
             "answer \"3 incidents\"": lambda s: bool(re.search(r"\b(3|trois)\b", _answer(s))),
             "latest incident read (ORDER BY / MAX date)": lambda s: any(
                 re.search(r"order\s+by\s+started_at\s+desc|max\(\s*started_at", o["arguments"].get("sql", ""), re.I)
                 for o in _tools(s, "query_incidents") if o["ok"]),
             "answer \"unresolved\"": lambda s: _has(s, "non résolu", "pas résolu", "pas encore résolu",
                                                      "toujours en cours", "unresolved", "not resolved"),
             "in French": french,
         }),
    Case("C5", "Out-of-scope request",
         "Mon Kafka est lent, que faire ?", "stopped", {
             "route=out_of_scope|vague": lambda s: s["route"]["intent"] in ("out_of_scope", "vague"),
             "no status/SQL tool": lambda s: not s.get("observations"),
             "no invented citation": lambda s: not citations(s.get("answer", "")),
             "states its limits or asks for clarification": lambda s: "?" in _answer(s) or _has(
                 s, "ne couvre", "pas couvert", "hors", "uniquement", "seulement", "postgres", "ne peux pas"),
             "in French": french,
         }),
    Case("C6", "Tool failure",
         "Mon serveur Redis ne répond plus, que se passe-t-il ?", "tool_error", {
             "tool error traced": lambda s: any("simulated tool failure" in e for e in s.get("errors", [])),
             "controlled exit (status=done)": lambda s: s.get("status") == "done",
             "says the check failed": lambda s: _has(s, "pas pu", "impossible", "n'a pas", "échec",
                                                                "erreur", "indisponible", "ne peut pas", "pas été"),
             "no status asserted": lambda s: not asserts_status(s),
             "exact citations": cites_only_known_sections,
             "in French": french,
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
