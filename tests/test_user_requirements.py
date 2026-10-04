"""User requirements (docs/USER_REQUIREMENTS.md): each requirement is locked by a test here or referenced there.

These tests must not be removed or weakened without the user's explicit agreement.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------- UR-006: documentation entirely in English
FRENCH = set("le la les des du de un une et est sont pas pour dans avec sur que qui au aux ce cette ces ou "
             "par mais plus nous vous il elle ils on être avoir fait été très aussi comme donc".split())
ENGLISH = set("the of and to in is are for with on that this it as be by an or not from at which was "
              "were has have will can each when its into than".split())
MAX_FRENCH_RATIO = 0.10  # share of French function words among (French + English) function words

# Documented exceptions (see docs/USER_REQUIREMENTS.md, UR-006):
#  - fenced code and inline code (terminal transcripts, commands, identifiers);
#  - text in double quotes: the validation questions are French test DATA (cross-lingual retrieval);
#  - in benchmark reports, the "## Answers" section: raw model output, in the language of the question;
#  - CLAUDE.md (fleet instruction file, not published) and private/ (not published).


def published_markdown() -> list[Path]:
    files = [ROOT / "README.md", ROOT / "CHANGELOG.md", ROOT / "TODO_LIST.md"]
    files += sorted((ROOT / "docs").glob("*.md")) + sorted((ROOT / "docs" / "bench").glob("*.md"))
    files += sorted((ROOT / "data" / "kb").glob("*.md"))
    return [f for f in files if f.exists()]


def prose(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if path.parent.name == "bench":
        text = text.split("\n## Answers\n")[0]
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", " ", text)
    text = re.sub(r"\"[^\"\n]*\"|“[^”\n]*”|«[^»\n]*»", " ", text)
    return text


def french_ratio(text: str) -> tuple[float, int, int]:
    words = re.findall(r"[a-zàâçéèêëîïôûùüÿœ]+", text.lower())
    fr = sum(w in FRENCH for w in words)
    en = sum(w in ENGLISH for w in words)
    return (fr / (fr + en) if fr + en else 0.0), fr, en


@pytest.mark.parametrize("path", published_markdown(), ids=lambda p: str(p.relative_to(ROOT)))
def test_ur006_published_documentation_is_in_english(path):
    ratio, fr, en = french_ratio(prose(path))
    assert ratio <= MAX_FRENCH_RATIO, f"{path.name}: {fr} French vs {en} English function words ({ratio:.0%})"


def test_ur006_language_check_detects_french():
    ratio, _, _ = french_ratio("Le service est arrêté et les connexions sont refusées pour cette application.")
    assert ratio > 0.9
    assert french_ratio("The service is stopped and connections are refused for this application.")[0] == 0


# ---------------------------------------------------------------- UR-001..003: diagrams on the documentation site
DIAGRAM_DOCS = ["README.md", "docs/SPEC.md", "docs/DESIGN_DECISIONS.md"]
CATEGORIES = ["malfunction", "documentation", "history", "out_of_scope", "vague"]


def mermaid_blocks(rel: str) -> list[str]:
    return re.findall(r"```mermaid\n(.*?)```", (ROOT / rel).read_text(encoding="utf-8"), re.S)


@pytest.mark.parametrize("rel", DIAGRAM_DOCS)
def test_ur001_architecture_diagrams_are_mermaid_not_ascii_art(rel):
    text = (ROOT / rel).read_text(encoding="utf-8")
    assert mermaid_blocks(rel), f"{rel}: no Mermaid diagram"
    assert not re.search(r"[┌└┐┘│├┤┬┴]", text), f"{rel}: ASCII-art box drawing left"


@pytest.mark.parametrize("rel", DIAGRAM_DOCS)
def test_ur002_diagrams_show_the_five_triage_categories(rel):
    main = mermaid_blocks(rel)[0]
    missing = [c for c in CATEGORIES if c not in main]
    assert not missing, f"{rel}: categories missing from the diagram: {missing}"


@pytest.mark.parametrize("rel", DIAGRAM_DOCS)
def test_ur003_diagrams_mark_agents_router_and_loops(rel):
    main = mermaid_blocks(rel)[0]
    assert "AGENT" in main and "ROUTER" in main, f"{rel}: agents/router not marked"
    assert "↻" in main, f"{rel}: agent loop not shown"
    assert "classDef agent" in main and "classDef router" in main, f"{rel}: no distinct styles"


@pytest.mark.parametrize("rel", ["README.md", "docs/DESIGN_DECISIONS.md"])
def test_ur003_agent_loop_diagram_and_legend_exist(rel):
    blocks = mermaid_blocks(rel)
    assert len(blocks) >= 2 and "MAX_LLM_CALLS" in blocks[1], f"{rel}: agent-loop diagram missing"
    assert "Legend" in (ROOT / rel).read_text(encoding="utf-8")
