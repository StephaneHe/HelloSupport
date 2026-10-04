"""User requirements (docs/USER_REQUIREMENTS.md): each requirement is locked by a test here or referenced there.

These tests must not be removed or weakened without the user's explicit agreement.
"""

import re
import subprocess
import sys
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
    files = [ROOT / "README.md", ROOT / "CHANGELOG.md", ROOT / "TODO_LIST.md", ROOT / "CONTRIBUTING.md",
             ROOT / "SECURITY.md", ROOT / "CODE_OF_CONDUCT.md"]
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


# ---------------------------------------------------------------- UR-008: documentation versioned and published
# Local-only names that must never appear in a published file (assembled so this file does not contain them).
PRIVATE_MARKERS = ["private/", "CONSTITUTION", "CLAUDE.md", "docsite", "webdemo", "mkdocs.local"]
PERSONAL_MARKERS = ["stephane" + ":51", "I:" + r"\Dev", "I:" + "/Dev", "C:" + r"\Users\steph", "/c/" + "Users/steph"]


def test_ur008_docs_site_builds_in_strict_mode_without_ignored_files(tmp_path):
    out = subprocess.run([sys.executable, "-m", "mkdocs", "build", "--strict", "-q", "-d", str(tmp_path / "site")],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    site = tmp_path / "site"
    for page in ["index.html", "SPEC/index.html", "DESIGN_DECISIONS/index.html", "BENCH/index.html", "reports/index.html",
                 "kb/postgres_connection/index.html", "changelog/index.html", "contributing/index.html",
                 "security/index.html", "license/index.html"]:
        assert (site / page).exists(), page
    assert not (site / "CONSTITUTION").exists() and not (site / "private").exists()  # git-ignored: never published


def test_ur008_published_site_config_references_nothing_private():
    text = (ROOT / "mkdocs.yml").read_text(encoding="utf-8") + (ROOT / "tools" / "docs_hooks.py").read_text(encoding="utf-8")
    found = [m for m in PRIVATE_MARKERS + PERSONAL_MARKERS if m in text]
    assert not found, f"published docs configuration mentions local-only names: {found}"


def test_ur008_ci_builds_strictly_and_publishes_versioned_docs():
    wf = (ROOT / ".github" / "workflows" / "docs.yml").read_text(encoding="utf-8")
    assert "pull_request" in wf and "mkdocs build --strict" in wf
    assert "mike deploy" in wf and "latest" in wf and "tags:" in wf


def test_ur008_no_personal_host_or_path_in_tracked_files():
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True).stdout.split("\0")
    hits = []
    for rel in filter(None, tracked):
        path = ROOT / rel
        if path.suffix in {".pdf", ".png", ".lock"} or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        hits += [f"{rel}: {m}" for m in PERSONAL_MARKERS if m in text]
    assert not hits, hits


# ---------------------------------------------------------------- UR-009: professional README in English
README_SECTIONS = ["Quick start", "Architecture", "Measured results", "Requirements", "Installation", "Usage", "Demo",
                   "Web demo", "Tests", "Documentation", "Known limitations", "Roadmap", "Contributing", "Security",
                   "License", "Author"]


def github_slug(heading: str) -> str:
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def test_ur009_readme_has_the_expected_sections_and_docs_link():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    headings = re.findall(r"^## (.+)$", text, re.M)
    missing = [s for s in README_SECTIONS if s not in headings]
    assert not missing, f"README sections missing: {missing}"
    assert "https://stephanehe.github.io/HelloSupport/" in text and "actions/workflows/docs.yml/badge.svg" in text
    from hello_support import __version__
    assert f"version-{__version__}-blue" in text, "README version badge out of date"


def test_ur009_readme_links_are_valid():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    prose = re.sub(r"```.*?```", " ", text, flags=re.S)
    slugs = {github_slug(h) for h in re.findall(r"^#{1,6} (.+)$", prose, re.M)}
    broken = []
    for target in re.findall(r"\]\(([^)\s]+)\)", prose):
        if re.match(r"^[a-z]+:", target):
            continue
        path, _, anchor = target.partition("#")
        if not path:
            if anchor not in slugs:
                broken.append(target)
        elif not (ROOT / path).exists():
            broken.append(target)
    assert not broken, f"broken README links: {broken}"
