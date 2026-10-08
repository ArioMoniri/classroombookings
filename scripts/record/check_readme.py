#!/usr/bin/env python3
"""Check that every relative link and image in the README files points at a file that exists.

    python3 scripts/record/check_readme.py [README.md smartsched/README.md ...]

Checks Markdown links/images, HTML src/srcset/href attributes and in-page anchors (#heading). External
URLs are listed, not fetched. Also lists files in docs/images/screens and docs/images/recordings that no
README references, and the total size of the referenced media. Exit code 1 when something is missing.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MD_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HTML_ATTR = re.compile(r"\b(?:src|srcset|href)=\"([^\"]+)\"")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$", re.M)
MEDIA_DIRS = ["docs/images/screens", "docs/images/recordings"]


def anchor(text: str) -> str:
    """GitHub's heading slug: lower case, punctuation dropped, spaces to hyphens."""
    text = re.sub(r"<[^>]+>", "", text).strip().lower()
    out = []
    for ch in text:
        if ch in (" ", "-"):
            out.append("-")
        elif ch == "_" or unicodedata.category(ch)[0] in ("L", "N"):
            out.append(ch)
    return "".join(out)


def check(readme: Path) -> tuple[list[str], set[Path], list[str]]:
    text = readme.read_text(encoding="utf-8")
    # skip fenced code blocks
    body = re.sub(r"```.*?```", "", text, flags=re.S)
    anchors = {anchor(m.group(2)) for m in HEADING.finditer(body)}
    targets = [m.group(1) for m in MD_LINK.finditer(body)] + [m.group(1) for m in HTML_ATTR.finditer(body)]
    missing, used, external = [], set(), []
    for t in targets:
        for part in t.split(","):
            ref = part.strip().split(" ")[0]
            if not ref:
                continue
            if re.match(r"^(https?:|mailto:)", ref):
                external.append(ref)
                continue
            path, _, frag = ref.partition("#")
            if not path:
                if frag and frag not in anchors:
                    missing.append(f"{readme.relative_to(ROOT)}: anchor #{frag}")
                continue
            target = (readme.parent / path).resolve()
            if not target.exists():
                missing.append(f"{readme.relative_to(ROOT)}: {ref}")
            else:
                used.add(target)
                if frag and target.suffix == ".md":
                    heads = {anchor(m.group(2)) for m in HEADING.finditer(target.read_text(encoding="utf-8"))}
                    if frag not in heads:
                        missing.append(f"{readme.relative_to(ROOT)}: {ref} (no such heading)")
    return missing, used, external


def main(argv: list[str]) -> int:
    files = [ROOT / a for a in argv] or [ROOT / "README.md", ROOT / "smartsched/README.md"]
    missing: list[str] = []
    used: set[Path] = set()
    external: list[str] = []
    for f in files:
        m, u, e = check(f)
        missing += m
        used |= u
        external += e
    media = [p for p in used if any(str(p).startswith(str(ROOT / d)) for d in MEDIA_DIRS + ["docs/images/lottie"])]
    total = sum(p.stat().st_size for p in media)
    print(f"checked {len(files)} file(s): {len(used)} local targets, {len(set(external))} external links (not fetched)")
    print(f"referenced media: {len(media)} files, {total / 1e6:.2f} MB")
    unused = []
    for d in MEDIA_DIRS:
        for p in sorted((ROOT / d).glob("*")):
            if p.is_file() and p not in used and p.name != "MANIFEST.md" and not p.name.endswith(".mp4") or (p.suffix == ".mp4" and p not in used):
                if p.is_file() and p not in used and p.name != "MANIFEST.md":
                    unused.append(str(p.relative_to(ROOT)))
    if unused:
        print("not referenced by any README:\n  " + "\n  ".join(unused))
    if missing:
        print("MISSING:\n  " + "\n  ".join(missing))
        return 1
    print("every link and image exists")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
