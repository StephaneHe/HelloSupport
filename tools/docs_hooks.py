"""MkDocs hooks: build the documentation site from the repository exactly as it is versioned.

- `docs/` is the docs directory. The hook adds the documents kept at the repository root (README
  as the home page, CHANGELOG, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, TODO_LIST, LICENSE,
  .env.example), the knowledge-base sheets (`data/kb/`), an index of the benchmark reports and a
  downloads page.
- Files ignored by git are never published, even if they sit in `docs/`.
- Documents are written for GitHub (links relative to the repository). Links are rewritten to the
  site page when the target is published, and to the file on GitHub otherwise (source code).
"""

import logging
import posixpath
import re
import subprocess
from pathlib import Path

from mkdocs.structure.files import File, Files

log = logging.getLogger("mkdocs.hooks.hellosupport")
ROOT = Path(__file__).resolve().parents[1]

# repository path -> site path
ROOT_PAGES = {
    "README.md": "index.md", "CHANGELOG.md": "changelog.md", "CONTRIBUTING.md": "contributing.md",
    "SECURITY.md": "security.md", "CODE_OF_CONDUCT.md": "code-of-conduct.md", "TODO_LIST.md": "todo.md",
}
DIRECTORY_PAGES = {"docs/bench": "reports.md", "data/kb": "kb/index.md"}
LINK = re.compile(r"(\]\()([^)\s]+)(\))")
FENCE = re.compile(r"^(```|~~~).*?^\1", re.S | re.M)
MERMAID = re.compile(r"^```mermaid\n.*?^```", re.S | re.M)


def _generated(config, src_uri: str, repo_path: str, content: str | None = None, src: Path | None = None) -> File:
    f = File.generated(config, src_uri, content=content, abs_src_path=str(src) if src else None)
    f.repo_path = repo_path
    return f


def _ignored(paths: list[str]) -> set[str]:
    """Paths (relative to the repository) that git ignores."""
    try:
        # NUL-separated: no newline translation on Windows.
        out = subprocess.run(["git", "check-ignore", "--stdin", "-z"], cwd=ROOT, input="\0".join(paths).encode(),
                             capture_output=True, check=False)
    except OSError as e:
        log.warning("git not available, cannot exclude ignored files: %s", e)
        return set()
    if out.returncode not in (0, 1):  # 1 = nothing ignored
        log.warning("git check-ignore failed: %s", out.stderr.decode(errors="replace").strip())
    return {p for p in out.stdout.decode().split("\0") if p}


def on_files(files: Files, config) -> Files:
    docs = [f for f in files if not f.generated_by]
    for f in docs:
        f.repo_path = f"docs/{f.src_uri}"
    for path in _ignored([f.repo_path for f in docs]):
        files.remove(files.get_file_from_path(path.removeprefix("docs/")))

    for repo, site in ROOT_PAGES.items():
        if (ROOT / repo).exists():
            files.append(_generated(config, site, repo, src=ROOT / repo))
    for sheet in sorted((ROOT / "data" / "kb").glob("*.md")):
        files.append(_generated(config, f"kb/{sheet.name}", f"data/kb/{sheet.name}", src=sheet))
    sheets = "\n".join(f"- [{s.stem.replace('_', ' ').capitalize()}]({s.name})"
                       for s in sorted((ROOT / "data" / "kb").glob("*.md")))
    files.append(_generated(config, "kb/index.md", "data/kb", (
        "# Knowledge base\n\nThe three troubleshooting sheets searched by the documentalist agent (one chunk per "
        "section, cited as `<sheet>.md#<section>`).\n\n" + sheets + "\n")))
    files.append(_generated(config, "license.md", "LICENSE",
                            "# License\n\n```text\n" + (ROOT / "LICENSE").read_text(encoding="utf-8") + "```\n"))
    files.append(_generated(config, "configuration.md", ".env.example", (
        "# Configuration\n\nCopy `.env.example` to `.env` (gitignored). Every variable is optional; the "
        "defaults are documented in the README.\n\n```bash\n"
        + (ROOT / ".env.example").read_text(encoding="utf-8") + "```\n")))
    reports = sorted(f.src_uri for f in files if f.src_uri.startswith("bench/") and f.src_uri.endswith(".md"))
    files.append(_generated(config, "reports.md", "docs/bench", (
        "# Benchmark reports\n\nOne report per `hello-support bench` run, with every model answer. Answers are "
        "raw model output, in the language of the question. How to read them: [BENCH](BENCH.md).\n\n"
        + "\n".join(f"- [{posixpath.basename(r)[:-3]}]({r})" for r in reversed(reports)) + "\n")))
    files.append(_generated(config, "downloads.md", "downloads", "# Downloads\n"))  # filled in on_page_markdown
    return files


def _site_paths(files: Files) -> dict[str, str]:
    paths = {getattr(f, "repo_path", f"docs/{f.src_uri}"): f.src_uri for f in files}
    paths.update(DIRECTORY_PAGES)
    return paths


def _rewrite(target: str, page_repo: str, page_site: str, paths: dict[str, str], repo_url: str) -> str:
    if re.match(r"^[a-zA-Z][a-zA-Z+.-]*:|^#|^/", target):
        return target
    path, _, anchor = target.partition("#")
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(page_repo), path))
    suffix = f"#{anchor}" if anchor else ""
    if resolved in paths:
        return posixpath.relpath(paths[resolved], posixpath.dirname(page_site) or ".") + suffix
    if (ROOT / resolved).exists() and not resolved.startswith(".."):
        kind = "tree" if (ROOT / resolved).is_dir() else "blob"
        return f"{repo_url.rstrip('/')}/{kind}/main/{resolved}{suffix}"
    return target  # left as is: the strict build reports it


def on_page_markdown(markdown: str, page, config, files: Files) -> str:
    if page.file.src_uri == "downloads.md":
        pdfs = sorted((f for f in files if f.src_uri.endswith(".pdf")), key=lambda f: f.src_uri)
        rows = "\n".join(f"| {Path(f.src_uri).stem.replace('_', ' ')} | [{Path(f.src_uri).name}]({f.src_uri}) |"
                         for f in pdfs)
        return ("# Downloads\n\nPDF exports of the main documents (with their diagrams).\n\n"
                "| Document | File |\n|---|---|\n" + rows + "\n")
    page_repo = getattr(page.file, "repo_path", f"docs/{page.file.src_uri}")
    paths = _site_paths(files)

    def fix_links(text: str) -> str:
        return LINK.sub(lambda m: m.group(1) + _rewrite(m.group(2), page_repo, page.file.src_uri, paths,
                                                        config.repo_url or "") + m.group(3), text)

    # Rewrite links outside code blocks only; wrap diagrams so that they scroll on small screens.
    out, last = [], 0
    for m in FENCE.finditer(markdown):
        out.append(fix_links(markdown[last:m.start()]))
        block = m.group(0)
        if MERMAID.fullmatch(block):
            block = f'<div class="diagram-scroll" markdown>\n\n{block}\n\n</div>'
        out.append(block)
        last = m.end()
    out.append(fix_links(markdown[last:]))
    return "".join(out)
