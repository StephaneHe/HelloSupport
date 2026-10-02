"""Deterministic post-processing of the technician's answer (facts the code knows, not the model).

- Citations: small models rewrite labels ("Service_status", "[...]"); map near-matches back to
  the exact `doc_id#section` ids of the knowledge base and flag the unknown ones.
- Simulation footer: whether a status was simulated, and that nothing was executed, are facts
  from the tool results; the code states them instead of hoping the model does.
"""

import re

from .retrieval import load_chunks

CITATION = re.compile(r"\[?([\w-]+\.md)#([A-Za-z][A-Za-z_ ]*[A-Za-z])\]?")


def _known() -> dict[str, str]:
    return {f"{c.doc_id}#{c.section}".lower(): f"{c.doc_id}#{c.section}" for c in load_chunks()}


def normalize_citations(answer: str) -> tuple[str, list[str]]:
    """Return the answer with canonical citations, and the citations that match no known section."""
    known, unknown = _known(), []

    def fix(m: re.Match) -> str:
        key = f"{m.group(1)}#{m.group(2).replace('_', ' ')}".lower()
        # The lazy section match may swallow following words ("Checks and ..."): try shorter prefixes.
        words = key.split("#")[1].split(" ")
        for n in range(len(words), 0, -1):
            cand = f"{m.group(1).lower()}#{' '.join(words[:n])}"
            if cand in known:
                rest = " ".join(m.group(2).replace("_", " ").split(" ")[n:])
                return known[cand] + (f" {rest}" if rest else "")
        unknown.append(m.group(0))
        return m.group(0)

    return CITATION.sub(fix, answer), unknown


def looks_french(text: str) -> bool:
    return len(re.findall(r"\b(le|la|les|est|de|du|des|que|mon|ma|ne|pas|ces|d|l|pour|combien|quelles?)\b", text.lower())) >= 2


def simulation_footer(observations: list[dict], question: str) -> str:
    statuses = [o for o in observations if o["tool"] == "get_service_status" and o["ok"]
                and isinstance(o["result"], dict) and o["result"].get("simulated")]
    fr = looks_french(question)
    parts = []
    if statuses:
        obs = ", ".join(f"{o['result']['service']} = {o['result']['status']}" for o in statuses)
        scenario = statuses[0]["result"].get("scenario")
        parts.append(f"Statut observé en simulation (scénario « {scenario} ») : {obs}." if fr
                     else f"Status observed in simulation (scenario '{scenario}'): {obs}.")
    parts.append("Aucune action corrective n'a été exécutée." if fr else "No corrective action was executed.")
    return "\n\n— " + " ".join(parts)
