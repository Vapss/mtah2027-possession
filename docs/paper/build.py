"""Build the technical document: figures, then one self-contained HTML, then the PDF.

    python docs/paper/figures.py
    python docs/paper/build.py --team "<team name>" --repo <public URL> --out runs/paper/<team>.pdf

`paper.html` is the source. This script inlines the figures (as data URIs, so the file stands
alone), fills the team, repository, date and the submission's SHA-256, and prints it to PDF with a
headless Chromium (Chrome or Edge; `--browser` or the `CHROME` variable to choose one). Nothing
here reads match data: the SHA-256 is computed from the submission file only.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html as html_lib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DELIVERY = REPO / "configs" / "delivery.json"
CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome",
    "chromium",
    "chromium-browser",
    "microsoft-edge",
)


def browser(explicit: str | None) -> str:
    for candidate in (explicit, os.environ.get("CHROME"), *CANDIDATES):
        if not candidate:
            continue
        found = candidate if Path(candidate).is_file() else shutil.which(candidate)
        if found:
            return found
    raise FileNotFoundError("no Chrome/Edge found: pass --browser or set CHROME")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_sha256() -> str:
    """The delivery reference must not be derived from the candidate being checked."""
    digest = json.loads(DELIVERY.read_text(encoding="utf-8"))["submission_sha256"]
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("delivery manifest must contain a complete SHA-256 digest")
    return digest


def render(team: str, repo: str, sha: str, date: str, revision: str) -> str:
    """Render only the recorded delivery, with a checkout command for this paper's revision."""
    expected = expected_sha256()
    if sha != expected:
        raise ValueError(f"Submission SHA-256 mismatch: expected {expected}, got {sha}")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("revision must be a full Git commit SHA")
    html = (HERE / "paper.html").read_text(encoding="utf-8")

    def figure(match: re.Match) -> str:
        data = (HERE / match.group(1)).read_bytes()
        encoded = base64.b64encode(data).decode("ascii")
        return f'<img alt="" src="data:image/svg+xml;base64,{encoded}" style="max-width:100%">'

    html = re.sub(r"\{\{FIG:([\w.-]+)\}\}", figure, html)
    fields = {
        "TEAM": team,
        "REPO": repo,
        "SHA": sha,
        "EXPECTED_SHA": expected,
        "DATE": date,
        "REVISION": revision,
    }
    for key, value in fields.items():
        if not value.strip():
            raise ValueError(f"{key.lower()} must not be empty")
        html = html.replace("{{" + key + "}}", html_lib.escape(value.strip()))
    left = re.findall(r"\{\{[A-Z:]+[^}]*\}\}", html)
    if left:
        raise ValueError(f"unfilled placeholders: {sorted(set(left))}")
    return html


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--team", required=True, help="the team name exactly as registered")
    parser.add_argument("--repo", required=True, help="the public repository URL")
    parser.add_argument("--submission", type=Path, default=REPO / "submissions/engine.csv")
    parser.add_argument("--date", required=True, help='title-line date, e.g. "November 2026"')
    parser.add_argument("--out", type=Path, required=True, help="the PDF to write")
    parser.add_argument("--browser", help="path to Chrome or Edge")
    args = parser.parse_args(argv)
    if not args.out.stem or args.out.suffix.lower() != ".pdf":
        parser.error(f"--out must name a .pdf file, got {args.out}")

    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, check=True, capture_output=True, text=True
    ).stdout.strip()
    html = render(args.team, args.repo, sha256(args.submission), args.date, revision)
    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    page = out.with_suffix(".html")
    page.write_text(html, encoding="utf-8", newline="\n")
    subprocess.run(
        [
            browser(args.browser),
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={out}",
            page.as_uri(),
        ],
        check=True,
        capture_output=True,
    )
    if not out.is_file() or out.stat().st_size == 0:
        raise RuntimeError(f"the browser wrote no PDF at {out}")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB) and {page.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
