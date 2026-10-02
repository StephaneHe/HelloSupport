"""Render Markdown docs to PDF: Markdown -> HTML (python-markdown) -> PDF (Edge/Chrome headless).

Usage: python tools/md2pdf.py docs/SPEC.md docs/DESIGN_DECISIONS.md
pandoc is not required. The PDF is written next to each Markdown file.
"""

import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import markdown

CSS = """body{font-family:Segoe UI,Arial,sans-serif;font-size:10pt;line-height:1.4;margin:0 .6cm;color:#222}
h1{font-size:17pt;border-bottom:2px solid #335}h2{font-size:13.5pt;color:#335;border-bottom:1px solid #ccd;
margin-top:1.3em;page-break-after:avoid}h3{font-size:11.5pt;page-break-after:avoid}
table{border-collapse:collapse;width:100%;margin:.5em 0;font-size:8.5pt}th,td{border:1px solid #bbb;padding:2px 4px;
vertical-align:top}th{background:#eef}tr{page-break-inside:avoid}
pre{background:#f6f6f6;padding:6px;line-height:1.15;white-space:pre-wrap}code{font-family:Consolas,monospace;font-size:8.5pt}
pre code{font-size:7pt}blockquote{color:#555;border-left:3px solid #ccd;margin-left:0;padding-left:.8em}
@page{size:A4;margin:1.4cm 1cm}"""

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "msedge", "google-chrome", "chromium", "chrome",
]


def find_browser() -> str:
    for b in BROWSERS:
        if Path(b).exists() or shutil.which(b):
            return b
    raise SystemExit("no Edge/Chrome found for headless PDF printing")


LIST_ITEM = re.compile(r"^(\s*)([-*]|\d+\.) ")


def github_lists(text: str) -> str:
    """python-markdown needs a blank line before a list and 4-space nesting; GitHub accepts neither."""
    out, in_code, prev = [], False, ""
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        m = None if in_code else LIST_ITEM.match(line)
        if m:
            line = " " * (len(m.group(1)) * 2) + line.lstrip()  # 2-space nesting -> 4
            if prev.strip() and not LIST_ITEM.match(prev) and not prev.startswith((" ", "|", ">")):
                out.append("")
        out.append(line)
        prev = line
    return "\n".join(out)


def render(md_path: Path, browser: str) -> Path:
    body = markdown.markdown(github_lists(md_path.read_text(encoding="utf-8")), extensions=["tables", "fenced_code"])
    tmp = Path(tempfile.mkdtemp(prefix="md2pdf-"))
    html = tmp / (md_path.stem + ".html")
    html.write_text(f'<!doctype html><html lang="fr"><meta charset="utf-8"><title>{md_path.stem}</title>'
                    f"<style>{CSS}</style><body>{body}</body></html>", encoding="utf-8")
    pdf = md_path.resolve().with_suffix(".pdf")
    pdf.unlink(missing_ok=True)
    subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--user-data-dir={tmp / 'profile'}", f"--print-to-pdf={pdf}", str(html)], check=False)
    for _ in range(60):  # Edge may return before the file is written
        if pdf.exists() and pdf.stat().st_size > 0:
            break
        time.sleep(0.5)
    shutil.rmtree(tmp, ignore_errors=True)
    if not pdf.exists():
        raise SystemExit(f"PDF not produced for {md_path}")
    return pdf


if __name__ == "__main__":
    browser = find_browser()
    for arg in sys.argv[1:]:
        out = render(Path(arg), browser)
        print(f"{out} ({out.stat().st_size // 1024} KB)")
