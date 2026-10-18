"""The diagrams in docs/architecture/ name only things that exist (standard library only):

    python3 -I -m unittest discover -s scripts/docs/tests

* every relative link resolves to a file or folder in the repository;
* every module path inside a Mermaid block (``services/solver_bridge.py``, ``import-wizard.tsx`` ...) is a file of the
  repository (a suffix match, so ``api/v1/runs.py`` and ``runs.py`` both count);
* every ``GET|POST|PUT|PATCH|DELETE /path`` inside a Mermaid block is a route of a FastAPI router in
  ``smartsched/backend/app/api/v1`` (path parameters compared by position, not by name);
* every entity of an ``erDiagram`` is a ``__tablename__`` of ``smartsched/backend/app/models``;
* every page of the folder is listed in its README, and no page carries a repository address, a branch name or an
  IP address (the repository will be renamed).

A Mermaid line that contains the word ``planned`` is exempt from the module and route checks: it names work that is
designed but not merged (say so in the line). Run ``python3 -I -m unittest scripts/docs/tests/test_architecture_docs.py``
after renaming or moving a module a diagram names.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DOCS = REPO / "docs" / "architecture"
API = REPO / "smartsched" / "backend" / "app" / "api" / "v1"
MODELS = REPO / "smartsched" / "backend" / "app" / "models"

#: folders searched for module names (generated and vendored trees are left out)
SOURCE_ROOTS = ("smartsched/backend", "smartsched/frontend/src", "smartsched/deploy", "infra", "scripts", ".github")
SKIP_PARTS = {"node_modules", "__pycache__", ".venv", ".next", "dist", "build"}
EXTENSIONS = ("py", "ts", "tsx", "sh", "yml", "yaml", "mjs")

MERMAID = re.compile(r"```mermaid\n(.*?)```", re.S)
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
MODULE = re.compile(r"(?<![\w/.\-])([\w./\-]*\w\.(?:" + "|".join(EXTENSIONS) + r"))(?![\w])")
ROUTE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE) (/[\w{}./\-]+)")
ROUTER_DECL = re.compile(r"^(\w+)\s*=\s*APIRouter\(([^)]*)\)", re.M)
PREFIX = re.compile(r"prefix\s*=\s*f?\"([^\"]*)\"")
DECORATOR = re.compile(r"@(\w+)\.(get|post|put|patch|delete)\(\s*f?\"([^\"]*)\"")
TABLENAME = re.compile(r"__tablename__\s*=\s*\"(\w+)\"")
ER_REL = re.compile(r"^\s*(\w+)\s+[|}o.\-]{4,}\s+(\w+)\s*:", re.M)
ER_ENTITY = re.compile(r"^\s*(\w+)\s*\{", re.M)
FORBIDDEN = (
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "an IP address"),
    (re.compile(r"github\.com/|gitlab\.com/", re.I), "a repository address"),
    (re.compile(r"\bclaude/[\w-]+"), "a branch name"),
    (re.compile(r"\.amazonaws\.com|\.compute\.internal", re.I), "a host name"),
)


def pages() -> list[Path]:
    return sorted(DOCS.glob("*.md"))


def mermaid_lines(text: str) -> list[str]:
    return [line for block in MERMAID.findall(text) for line in block.splitlines()]


def source_files() -> list[str]:
    out: list[str] = []
    for root in SOURCE_ROOTS:
        base = REPO / root
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_file() and p.suffix.lstrip(".") in EXTENSIONS and not SKIP_PARTS.intersection(p.parts):
                out.append(p.relative_to(REPO).as_posix())
    return out


def norm_route(path: str) -> str:
    path = path.rstrip(".,)")
    if path.startswith("/api/v1/"):
        path = path[len("/api/v1") :]
    path = re.sub(r"\{[^}]*\}", "{}", path.split("?", 1)[0])
    return path.rstrip("/") or "/"


def backend_routes() -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for f in sorted(API.glob("*.py")):
        src = f.read_text(encoding="utf-8")
        prefixes = {}
        for name, args in ROUTER_DECL.findall(src):
            m = PREFIX.search(args)
            prefixes[name] = m.group(1) if m else ""
        for var, method, path in DECORATOR.findall(src):
            if var in prefixes:
                routes.add((method.upper(), norm_route(prefixes[var] + path)))
    return routes


class ArchitectureDocs(unittest.TestCase):
    def test_folder_has_pages(self) -> None:
        self.assertTrue((DOCS / "README.md").is_file(), "docs/architecture/README.md is the index")
        self.assertGreaterEqual(len(pages()), 2)

    def test_relative_links_resolve(self) -> None:
        missing = []
        for page in pages():
            for target in LINK.findall(page.read_text(encoding="utf-8")):
                if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                    continue
                path = unquote(target.split("#", 1)[0])
                if not (page.parent / path).exists():
                    missing.append(f"{page.name}: {target}")
        self.assertEqual(missing, [], "links to files that do not exist")

    def test_mermaid_modules_exist(self) -> None:
        files = source_files()
        missing = []
        for page in pages():
            for line in mermaid_lines(page.read_text(encoding="utf-8")):
                if "planned" in line.lower():
                    continue
                for token in MODULE.findall(line):
                    token = token.removeprefix("./")
                    if not any(f == token or f.endswith("/" + token) for f in files):
                        missing.append(f"{page.name}: {token}")
        self.assertEqual(missing, [], "diagram names a module that is not in the repository (renamed or removed?)")

    def test_mermaid_routes_exist(self) -> None:
        routes = backend_routes()
        self.assertGreater(len(routes), 100, "the router scan found too few routes; did api/v1 move?")
        missing = []
        for page in pages():
            for line in mermaid_lines(page.read_text(encoding="utf-8")):
                if "planned" in line.lower():
                    continue
                for method, path in ROUTE.findall(line):
                    if (method, norm_route(path)) not in routes:
                        missing.append(f"{page.name}: {method} {path}")
        self.assertEqual(missing, [], "diagram names an API route no router declares")

    def test_er_entities_are_tables(self) -> None:
        tables = {t for f in MODELS.glob("*.py") for t in TABLENAME.findall(f.read_text(encoding="utf-8"))}
        self.assertIn("schedule_runs", tables)
        missing = []
        for page in pages():
            for block in MERMAID.findall(page.read_text(encoding="utf-8")):
                if not block.lstrip().startswith("erDiagram"):
                    continue
                names = {n for pair in ER_REL.findall(block) for n in pair} | set(ER_ENTITY.findall(block))
                missing += [f"{page.name}: {n}" for n in sorted(names - tables)]
        self.assertEqual(missing, [], "ER entity is not a __tablename__ of app/models")

    def test_index_lists_every_page(self) -> None:
        index = (DOCS / "README.md").read_text(encoding="utf-8")
        linked = {t.split("#", 1)[0] for t in LINK.findall(index)}
        unlisted = [p.name for p in pages() if p.name != "README.md" and p.name not in linked]
        self.assertEqual(unlisted, [], "add the page to docs/architecture/README.md")

    def test_no_addresses_or_branch_names(self) -> None:
        found = []
        for page in pages():
            for i, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
                for rx, what in FORBIDDEN:
                    if rx.search(line):
                        found.append(f"{page.name}:{i}: {what}")
        self.assertEqual(found, [], "diagrams must survive the repository rename: no addresses, branches or IPs")


if __name__ == "__main__":
    unittest.main()
