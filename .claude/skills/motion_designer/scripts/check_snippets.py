#!/usr/bin/env python3
"""Validate the motion_designer skill.

1. SKILL.md frontmatter parses as YAML and has name/description/allowed-tools.
2. Every ```ts / ```tsx block in SKILL.md and references/*.md type-checks
   against motion v14 + React 19 types (strict mode, same options as the app).

Usage:
  python3 -I .claude/skills/motion_designer/scripts/check_snippets.py <dir-with-node_modules> [--keep]

<dir-with-node_modules> must contain node_modules with motion@14, react@19,
@types/react@19, @dnd-kit/core, @playwright/test and typescript. The app
itself works: smartsched/frontend. A scratch install works too:
  npm i motion@14.0.0 react@19 react-dom@19 @types/react@19 @types/react-dom@19 \
        typescript@5 @dnd-kit/core@6.3.1 @playwright/test@1.56.1 @types/node@22
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
FENCE = re.compile(r"^```(tsx|ts)\s*$\n(.*?)^```\s*$", re.M | re.S)


def check_frontmatter() -> list[str]:
    errors: list[str] = []
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return ["SKILL.md: missing frontmatter opener"]
    end = text.find("\n---\n", 4)
    if end < 0:
        return ["SKILL.md: missing frontmatter closer"]
    raw = text[4:end]
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(raw)
    except ImportError:
        errors.append("PyYAML not installed; frontmatter only checked for keys")
        data = {k.strip(): v.strip() for k, v in (l.split(":", 1) for l in raw.splitlines() if ":" in l)}
    except Exception as exc:  # noqa: BLE001
        return [f"SKILL.md frontmatter is not valid YAML: {exc}"]
    if not isinstance(data, dict):
        return ["SKILL.md frontmatter is not a mapping"]
    for key in ("name", "description", "allowed-tools"):
        if not data.get(key):
            errors.append(f"SKILL.md frontmatter missing '{key}'")
    if data.get("name") != "motion_designer":
        errors.append("frontmatter name must be motion_designer")
    if len(str(data.get("description", ""))) > 1024:
        errors.append("description longer than 1024 chars")
    return errors


def extract(out: Path) -> list[Path]:
    files: list[Path] = []
    docs = [SKILL / "SKILL.md", *sorted((SKILL / "references").glob("*.md"))]
    for doc in docs:
        for i, m in enumerate(FENCE.finditer(doc.read_text(encoding="utf-8"))):
            lang, body = m.group(1), m.group(2)
            name = f"{doc.stem}-{i:02d}.{lang}"
            p = out / "snippets" / name
            p.parent.mkdir(parents=True, exist_ok=True)
            # every snippet is its own module
            if "import " not in body and "export " not in body:
                body += "\nexport {};\n"
            p.write_text(body, encoding="utf-8")
            files.append(p)
    return files


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    nm_root = Path(sys.argv[1]).resolve()
    keep = "--keep" in sys.argv
    problems = check_frontmatter()
    for p in problems:
        print("FRONTMATTER:", p)

    work = Path(tempfile.mkdtemp(prefix="motion-snippets-"))
    try:
        (work / "lib").mkdir()
        shutil.copy(SKILL / "references" / "motion-tokens.ts", work / "lib" / "motion.ts")
        files = extract(work)
        os.symlink(nm_root / "node_modules", work / "node_modules")
        (work / "globals.d.ts").write_text(
            'declare module "*.css";\n', encoding="utf-8"
        )
        tsconfig = {
            "compilerOptions": {
                "target": "ES2020",
                "lib": ["dom", "dom.iterable", "esnext"],
                "strict": True,
                "noEmit": True,
                "skipLibCheck": True,
                "esModuleInterop": True,
                "module": "esnext",
                "moduleResolution": "bundler",
                "jsx": "react-jsx",
                "isolatedModules": True,
                "types": ["node"],
                "paths": {"@/lib/motion": ["./lib/motion.ts"]},
            },
            "include": ["lib/*.ts", "snippets/*", "globals.d.ts"],
        }
        (work / "tsconfig.json").write_text(json.dumps(tsconfig, indent=2), encoding="utf-8")
        tsc = nm_root / "node_modules" / ".bin" / "tsc"
        res = subprocess.run([str(tsc), "-p", "."], capture_output=True, text=True, cwd=work)
        print(f"snippets: {len(files)} files + lib/motion.ts")
        out = (res.stdout + res.stderr).replace(str(work) + "/", "")
        if out.strip():
            print(out)
        ok = res.returncode == 0 and not [p for p in problems if "PyYAML" not in p]
        print("RESULT:", "PASS" if ok else "FAIL")
        if keep:
            print("kept:", work)
        return 0 if ok else 1
    finally:
        if not keep:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
