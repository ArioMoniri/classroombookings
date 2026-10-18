"""Tests of scripts/docs/sync_docs.py (standard library only):

    python3 -I -m unittest discover -s scripts/docs/tests

Idempotence and stale detection on the real docs, prose around the blocks kept byte for byte, malformed markers
refused, and every generator checked against the real repository files by an independent reading of its source.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
_spec = importlib.util.spec_from_file_location("sync_docs", HERE.parent / "sync_docs.py")
if _spec is None or _spec.loader is None:
    raise ImportError("scripts/docs/sync_docs.py not found")
sd = importlib.util.module_from_spec(_spec)
sys.modules["sync_docs"] = sd
_spec.loader.exec_module(sd)


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = sd.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def ctx(target: str = "docs/STATUS.md", **args: str) -> object:
    return sd.Context(root=REPO, target=REPO / target, args=dict(args))


class FakeGenerators:
    """Swap the generator table for the duration of a test."""

    def __init__(self, **gens: object) -> None:
        self.gens = gens

    def __enter__(self) -> None:
        self.saved = dict(sd.GENERATORS)
        sd.GENERATORS.clear()
        sd.GENERATORS.update(self.gens)

    def __exit__(self, *exc: object) -> None:
        sd.GENERATORS.clear()
        sd.GENERATORS.update(self.saved)


# --------------------------------------------------------------------------------------------------
# markers, idempotence, preservation, stale detection
# --------------------------------------------------------------------------------------------------


class MarkerTests(unittest.TestCase):
    TEXT = (
        "# Title\n\nProse   with  odd   spacing.\t\n\n"
        "<!-- AUTO:alpha -->\nold alpha\n<!-- /AUTO:alpha -->\n"
        "between *the* blocks\n"
        "  <!-- AUTO:beta n=2 -->\n<!-- /AUTO:beta -->\n"
        "```md\n<!-- AUTO:alpha -->\nan example, never rewritten\n<!-- /AUTO:alpha -->\n```\n"
        "inline `<!-- AUTO:alpha -->` mention stays\n"
        "tail without newline"
    )

    def render(self, text: str) -> tuple[str, list[object], list[str]]:
        with FakeGenerators(alpha=lambda c: "A\n| x |", beta=lambda c: f"B{c.args['n']}"):
            return sd.render_text(text, sd.Context(root=REPO, target=REPO / "x.md"), "x.md")

    def test_only_the_blocks_change_and_prose_is_kept_byte_for_byte(self) -> None:
        new, blocks, stale = self.render(self.TEXT)
        self.assertEqual([b.label for b in blocks], ["alpha", "beta n=2"])
        self.assertEqual(stale, ["alpha", "beta n=2"])
        self.assertIn("<!-- AUTO:alpha -->\n\nA\n| x |\n\n<!-- /AUTO:alpha -->\n", new)
        self.assertIn("  <!-- AUTO:beta n=2 -->\n\nB2\n\n<!-- /AUTO:beta -->\n", new)
        # strip the generated bodies: what is left must be the original text exactly
        def outside(t: str) -> str:
            return re.sub(r"(?m)(^[ \t]*<!-- AUTO:(\w+)[^\n]*-->\n).*?(^[ \t]*<!-- /AUTO:\2 -->)", r"\1\3", t,
                          count=2, flags=re.S)
        self.assertEqual(outside(new), outside(self.TEXT))
        self.assertIn("```md\n<!-- AUTO:alpha -->\nan example, never rewritten\n", new)
        self.assertTrue(new.endswith("inline `<!-- AUTO:alpha -->` mention stays\ntail without newline"))

    def test_second_run_is_a_no_op(self) -> None:
        once, _, _ = self.render(self.TEXT)
        twice, _, stale = self.render(once)
        self.assertEqual(twice, once)
        self.assertEqual(stale, [])

    def test_crlf_files_keep_crlf(self) -> None:
        text = "a\r\n<!-- AUTO:beta n=1 -->\r\n<!-- /AUTO:beta -->\r\nb\r\n"
        new, _, _ = self.render(text)
        self.assertEqual(new, "a\r\n<!-- AUTO:beta n=1 -->\r\n\r\nB1\r\n\r\n<!-- /AUTO:beta -->\r\nb\r\n")

    def test_malformed_markers_are_refused(self) -> None:
        bad = {
            "never closed": "<!-- AUTO:alpha -->\nx\n",
            "closes a block": "<!-- /AUTO:alpha -->\n",
            "opens inside": "<!-- AUTO:alpha -->\n<!-- AUTO:beta n=1 -->\n<!-- /AUTO:beta -->\n<!-- /AUTO:alpha -->\n",
            "malformed": "<!-- AUTO:Alpha -->\n",
            "unknown block": "<!-- AUTO:gamma -->\n<!-- /AUTO:gamma -->\n",
        }
        for why, text in bad.items():
            with self.subTest(why), self.assertRaisesRegex(sd.SyncError, why):
                self.render(text)

    def test_volatile_block_is_rewritten_but_never_stale_and_kept_without_git(self) -> None:
        text = "<!-- AUTO:last-updated -->\nold\n<!-- /AUTO:last-updated -->\n"
        with FakeGenerators(**{"last-updated": lambda c: "new"}):
            new, _, stale = sd.render_text(text, sd.Context(root=REPO, target=REPO / "x.md"))
        self.assertIn("\nnew\n", new)
        self.assertEqual(stale, [])
        with FakeGenerators(**{"last-updated": lambda c: None}):  # no git: keep the text
            new, _, _ = sd.render_text(text, sd.Context(root=REPO, target=REPO / "x.md"))
        self.assertEqual(new, text)

    def test_check_no_blocks_are_rewritten_but_never_stale(self) -> None:
        new, blocks, stale = self.render("<!-- AUTO:beta n=3 check=no -->\nold\n<!-- /AUTO:beta -->\n")
        self.assertIn("\nB3\n", new)
        self.assertEqual(blocks[0].args, {"n": "3", "check": "no"})
        self.assertEqual(stale, [])

    def test_git_head_without_a_repository_is_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(sd.git_head(Path(tmp)))


class CliTests(unittest.TestCase):
    """--check / --list / write on a scratch tree with a copy of one real source (the Alembic chain)."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        shutil.copytree(REPO / sd.VERSIONS, self.tmp / sd.VERSIONS, ignore=shutil.ignore_patterns("__pycache__"))
        (self.tmp / "docs").mkdir()
        self.doc = self.tmp / "docs" / "ARCH.md"
        self.doc.write_text("# Arch\n\nkeep me\n\n<!-- AUTO:migrations -->\n<!-- /AUTO:migrations -->\n\nend\n",
                            encoding="utf-8")
        self.readme = self.tmp / "README.md"
        self.readme.write_text("# No markers here\n", encoding="utf-8")

    def test_check_write_check(self) -> None:
        code, out, _ = run("--root", str(self.tmp), "--check")
        self.assertEqual(code, 1)
        self.assertIn("STALE docs/ARCH.md: migrations", out)
        before = self.readme.stat().st_mtime_ns
        self.assertEqual(run("--root", str(self.tmp))[0], 0)
        self.assertEqual(self.readme.stat().st_mtime_ns, before, "a file without markers must not be written")
        text = self.doc.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Arch\n\nkeep me\n\n<!-- AUTO:migrations -->\n"))
        self.assertTrue(text.endswith("<!-- /AUTO:migrations -->\n\nend\n"))
        self.assertEqual(run("--root", str(self.tmp), "--check")[0], 0)
        code, out, _ = run("--root", str(self.tmp), "--list")
        self.assertEqual(code, 0)
        self.assertIn("migrations", out)
        self.assertIn("ok", out)

    def test_a_new_migration_makes_the_block_stale(self) -> None:
        run("--root", str(self.tmp))
        _, heads = sd.chain_order(sd.read_migrations(self.tmp))
        (self.tmp / sd.VERSIONS / "9999_test.py").write_text(
            f'"""A test migration."""\nrevision = "9999_test"\ndown_revision = "{heads[0]}"\n', encoding="utf-8")
        code, out, _ = run("--root", str(self.tmp), "--check", "--diff")
        self.assertEqual(code, 1)
        self.assertIn("STALE docs/ARCH.md: migrations", out)
        self.assertIn("+| ", out)
        self.assertIn("9999_test", out)

    def test_two_heads_are_named(self) -> None:
        (self.tmp / sd.VERSIONS / "9998_side.py").write_text(
            '"""Side branch."""\nrevision = "9998_side"\ndown_revision = "0001"\n', encoding="utf-8")
        run("--root", str(self.tmp))
        self.assertIn("**2 heads**", self.doc.read_text(encoding="utf-8"))

    def test_an_unreadable_source_is_exit_2(self) -> None:
        self.doc.write_text("<!-- AUTO:parity -->\n<!-- /AUTO:parity -->\n", encoding="utf-8")
        code, _, err = run("--root", str(self.tmp), "--check")
        self.assertEqual(code, 2)
        self.assertIn("crbs-parity-report.md", err)


class RealDocsTests(unittest.TestCase):
    def test_real_docs_render_idempotently(self) -> None:
        results = sd.process(REPO)
        names = {r.path.relative_to(REPO).as_posix(): [b.name for b in r.blocks] for r in results}
        self.assertTrue({"migrations", "formats"} <= set(names["docs/ARCHITECTURE.md"]))
        self.assertIn("parity", names["docs/CRBS_PARITY.md"])
        self.assertEqual(names["docs/PROGRESS.md"], ["last-updated"])
        self.assertTrue({"status", "gates", "agents", "decisions", "last-updated"} <= set(names["docs/STATUS.md"]))
        cache: dict[str, object] = {}
        for r in results:
            again, _, stale = sd.render_text(r.new, sd.Context(root=REPO, target=r.path, cache=cache))
            self.assertEqual(again, r.new, r.path)
            self.assertEqual(stale, [], r.path)

    def test_progress_block_is_at_the_top(self) -> None:
        lines = (REPO / "docs/PROGRESS.md").read_text(encoding="utf-8").splitlines()
        self.assertTrue(lines[0].startswith("# "))
        self.assertEqual(lines[2], "<!-- AUTO:last-updated -->")


# --------------------------------------------------------------------------------------------------
# each generator on the real repository files
# --------------------------------------------------------------------------------------------------


class GeneratorTests(unittest.TestCase):
    def test_features_registry(self) -> None:
        text = (REPO / sd.FEATURES).read_text(encoding="utf-8")
        items = sd.parse_features_yaml(text)
        self.assertGreater(len(items), 20)
        for i in items:
            if i.get("evidence"):
                self.assertTrue((REPO / i["evidence"]).exists(), i["evidence"])
        try:  # the subset must read the same as real YAML where PyYAML happens to be installed
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            pass
        else:
            self.assertEqual([{k: str(v) for k, v in d.items()} for d in yaml.safe_load(text)], items)
        full = sd.gen_status(ctx())
        done = [i for i in items if i["status"] == "done"]
        self.assertIn(f"Done {len(done)} ·", full)
        short = sd.gen_status(ctx("README.md", only="done"))
        self.assertEqual(short.count("\n| ") - 1, len(done))  # header row + one row per Done item
        self.assertNotIn("Backend only:", short)
        self.assertIn("](smartsched/", short)  # links relative to the README at the root
        self.assertIn("](../smartsched/", full)  # and to docs/STATUS.md

    def test_features_parser_refuses_ambiguous_yaml(self) -> None:
        for text, why in (('- feature: a: b\n  area: planning\n  status: done\n', "quote"),
                          ('- feature: "a"\n  area: planning\n  status: shipped\n', "status"),
                          ('- feature: "a"\n  colour: red\n', "unknown key"),
                          ('- feature: "a"\n  area: planning\n', "no status")):
            with self.subTest(why), self.assertRaisesRegex(sd.SyncError, why):
                sd.parse_features_yaml(text)

    def test_parity_matches_the_report_table(self) -> None:
        text = (REPO / sd.PARITY_REPORT).read_text(encoding="utf-8")
        results = re.findall(r"^\| [A-Z][\w-]* \|.*\| \*\*([A-Z]+)\*\* \|", text, re.M)
        sha = re.search(r"\(commit `([0-9a-f]+)`\)", text).group(1)  # type: ignore[union-attr]
        out = sd.gen_parity(ctx())
        for k in ("PASS", "GAP", "FAIL", "MISSING"):
            self.assertIn(f"{k} {results.count(k)}", out)
        self.assertIn(f"of {len(results)} rows", out)
        self.assertIn(f"`{sha}`", out)
        gaps = sd.gen_parity(ctx("docs/CRBS_PARITY.md", gaps="yes"))
        self.assertEqual(gaps.count("\n| ") - 1, len([r for r in results if r != "PASS"]))

    def test_migrations_single_head(self) -> None:
        files = sorted(p for p in (REPO / sd.VERSIONS).glob("*.py"))
        src = {p: p.read_text(encoding="utf-8") for p in files}
        revs = {m.group(1) for t in src.values()
                if (m := re.search(r'^revision\s*(?::[^=]*)?=\s*["\']([^"\']+)', t, re.M))}
        downs = set(re.findall(r'^down_revision\s*(?::[^=]*)?=\s*["\']([^"\']+)', "\n".join(src.values()), re.M))
        heads = revs - downs
        out = sd.gen_migrations(ctx("docs/ARCHITECTURE.md"))
        if len(heads) == 1:
            self.assertIn(f"single head **`{heads.pop()}`**", out)
        for r in revs:
            self.assertIn(f"`{r}`", out)

    def test_gates_list_matches_gates_py(self) -> None:
        sys.path.insert(0, str(REPO / "smartsched/deploy/pod-ci"))
        try:
            from podci.gates import DEPLOY, GATES  # type: ignore[import-not-found]
        except (ImportError, SyntaxError):
            self.skipTest("podci needs Python >= 3.12")
        finally:
            sys.path.remove(str(REPO / "smartsched/deploy/pod-ci"))
        gates, deploy = sd.read_gates(REPO)
        self.assertEqual([(g.name, g.description, g.blocking, g.needs) for g in gates],
                         [(g.name, g.description, g.blocking, g.needs) for g in GATES])
        self.assertEqual(deploy.name, DEPLOY.name)  # type: ignore[union-attr]
        out = sd.gen_gates(ctx())
        for g in GATES:
            self.assertIn(f"| `{g.name}` |", out)

    def test_gate_results_from_the_pod_ci_store(self) -> None:
        sys.path.insert(0, str(REPO / "smartsched/deploy/pod-ci"))
        try:
            from podci.state import SCHEMA  # type: ignore[import-not-found]
        except (ImportError, SyntaxError):
            self.skipTest("podci needs Python >= 3.12")
        finally:
            sys.path.remove(str(REPO / "smartsched/deploy/pod-ci"))
        with tempfile.TemporaryDirectory() as tmp:
            root, db = Path(tmp), Path(tmp) / "ci.sqlite3"
            con = sqlite3.connect(db)
            con.executescript(SCHEMA)
            con.execute("INSERT INTO runs (id, branch, sha, state, created_at, finished_at) VALUES "
                        "(1, 'main', 'a' || hex(zeroblob(19)), 'success', 0, 1760565600), "
                        "(2, 'main', 'b' || hex(zeroblob(19)), 'failure', 0, 1760569200), "
                        "(3, 'main', 'c' || hex(zeroblob(19)), 'running', 0, NULL)")
            con.executemany("INSERT INTO steps (run_id, seq, name, state) VALUES (2, ?, ?, ?)",
                            [(0, "prepare", "success"), (1, "backend", "failure")])
            con.commit()
            con.close()
            entry = sd.record_podci(root, db, "main")
            self.assertEqual(entry["commit"][:1], "b")
            self.assertEqual(entry["date"], "2025-10-15 23:00 UTC")
            self.assertEqual(entry["gates"], {"prepare": "success", "backend": "failure"})
            sd.record_podci(root, db, "main")  # replaces, does not append
            data = json.loads((root / sd.GATE_RESULTS).read_text(encoding="utf-8"))
            self.assertEqual(len(data["runs"]), 1)

    def test_agents_counts_and_no_prompts(self) -> None:
        agents = json.loads((REPO / sd.REGISTRY).read_text(encoding="utf-8"))["agents"]
        out = sd.gen_agents(ctx())
        self.assertIn(f"{len(agents)} agents", out)
        running = [a for a in agents if a.get("status") == "running"]
        if running:
            self.assertIn(f"running {len(running)}", out)
        self.assertEqual(out.count("\n| "), len(running) + 1 if running else 0)
        for a in agents:  # statuses only: no goals, scopes or prompts
            for key in ("goal", "scope", "next"):
                text = str(a.get(key) or "")
                if len(text) > 40:
                    self.assertNotIn(text[:40], out)
        self.assertEqual(sd.ledger_name("docs-autosync-2026-10-15 SCOPE: new scripts/docs/**"),
                         "docs-autosync-2026-10-15")

    def test_decisions(self) -> None:
        text = (REPO / sd.ROADMAP).read_text(encoding="utf-8")
        sets = sd.roadmap_decisions(text)
        titles = [s.title for s in sets]
        self.assertTrue(any(t.startswith("User decisions") for t in titles), titles)
        self.assertTrue(all(s.date for s in sets), titles)
        self.assertFalse(any("orchestrator" in t.lower() for t in titles), titles)
        out = sd.gen_decisions(ctx())
        for s in sets:
            self.assertIn(s.title[:60], out)
        self.assertNotIn("- [ ]", out)
        sample = ("### Owner decisions 2026-01-02 ~10:00: things\n- **Bold rule** (detail). More.\n"
                  "- Plain rule. Second sentence.\n- [ ] a task, not a decision\n  - nested detail\n\n"
                  "Paragraph after.\n- not part of it\n"
                  "### Other\nUser decisions recovered: a; b.\n")
        got = sd.roadmap_decisions(sample)
        self.assertEqual([(s.title, s.date, s.time, s.items) for s in got], [
            ("Owner decisions: things", "2026-01-02", "~10:00", ["Bold rule", "Plain rule"]),
            ("User decisions recovered", "", "", ["a", "b"]),
        ])

    def test_roadmap_counts(self) -> None:
        text = (REPO / sd.ROADMAP).read_text(encoding="utf-8")
        done = len(re.findall(r"(?m)^\s*[-*]\s+\[[xX]\]\s", text))
        open_ = len(re.findall(r"(?m)^\s*[-*]\s+\[ \]\s", text))
        self.assertIn(f"**{done} ticked · {open_} open**", sd.gen_roadmap(ctx()))

    def test_languages(self) -> None:
        out = sd.gen_languages(ctx())
        self.assertIn("Turkish (`tr`)", out)
        self.assertIn("English (`en`)", out)
        self.assertIn("source catalogue", out)

    def test_formats_match_the_registry_source(self) -> None:
        names = []
        for p in sorted((REPO / sd.COUNCIL).glob("formats_*.py")):
            names += re.findall(r'register\(\s*FormatSpec\(\s*"([a-z0-9-]+)"', p.read_text(encoding="utf-8"))
        out = sd.gen_formats(ctx("docs/ARCHITECTURE.md"))
        self.assertIn(f"{len(names)} formats", out)
        for n in names:
            self.assertIn(f"| `{n}` |", out)
        specs, _ = sd.read_formats(REPO)
        xlsx = next(s for s in specs if s["name"] == "xlsx")
        self.assertEqual(xlsx["route"], "structured")
        self.assertEqual(xlsx["limits"]["max_bytes"], 25 * 1024 * 1024)

    def test_last_updated_names_head(self) -> None:
        head = sd.git_head(REPO)
        if head is None:
            self.skipTest("not a git checkout (pod CI exports the tree)")
        self.assertIn(f"`{head[0]}`", sd.gen_last_updated(ctx()) or "")


class RecordingsTests(unittest.TestCase):
    """The README 'See it work' block comes from docs/images/recordings/clips.json and the files next to it."""

    def test_real_clips_render_featured_grid_and_every_take(self) -> None:
        text = sd.gen_recordings(ctx("README.md"))
        data = json.loads((REPO / "docs/images/recordings/clips.json").read_text(encoding="utf-8"))
        for clip in data["featured"]:
            self.assertIn(f'src="docs/images/recordings/{clip["id"]}.gif"', text)
            self.assertIn(f"<b>{clip['title']}.</b>", text)
        for take in data["takes"]:
            self.assertIn(f'href="docs/images/recordings/{take["id"]}.mp4"', text)
            self.assertIn(f'src="docs/images/recordings/{take["id"]}-poster.png"', text)
        self.assertIn(f"({len(data['takes'])} full takes, MP4)", text)
        self.assertEqual(text, sd.gen_recordings(ctx("README.md")))  # deterministic

    def test_missing_media_file_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rec = root / "docs/images/recordings"
            rec.mkdir(parents=True)
            (rec / "clips.json").write_text(json.dumps({
                "featured": [{"id": "a", "take": "t", "title": "A", "caption": "c"}],
                "takes": [{"id": "t", "title": "T"}],
            }), encoding="utf-8")
            (rec / "a.gif").write_bytes(b"x")
            (rec / "t.mp4").write_bytes(b"x")
            c = sd.Context(root=root, target=root / "README.md")
            with self.assertRaises(sd.SyncError):
                sd.gen_recordings(c)  # t-poster.png is missing
            (rec / "t-poster.png").write_bytes(b"x")
            out = sd.gen_recordings(c)
            self.assertIn('<a href="docs/images/recordings/t.mp4"><img alt="Screen recording: A. c"', out)
            self.assertIn('src="docs/images/recordings/a.gif"', out)
            self.assertNotIn("<picture>", out)  # no WebP yet: the GIF alone

    def _clip_root(self, root: Path, *, gif: bool, webp: bool) -> object:
        rec = root / "docs/images/recordings"
        rec.mkdir(parents=True)
        (rec / "clips.json").write_text(json.dumps({
            "featured": [{"id": "a", "take": "t", "title": "A", "caption": "c"}], "takes": [],
        }), encoding="utf-8")
        (rec / "t.mp4").write_bytes(b"x")
        if gif:
            (rec / "a.gif").write_bytes(b"x")
        if webp:
            clips = root / "docs/launch/media/clips"
            clips.mkdir(parents=True)
            (clips / "a.webp").write_bytes(b"x")
        return sd.Context(root=root, target=root / "README.md")

    def test_webp_is_shown_with_the_gif_as_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = sd.gen_recordings(self._clip_root(Path(tmp), gif=True, webp=True))
            self.assertIn(
                '<a href="docs/images/recordings/t.mp4"><picture>'
                '<source srcset="docs/launch/media/clips/a.webp" type="image/webp">'
                '<img alt="Screen recording: A. c" src="docs/images/recordings/a.gif" width="100%">'
                "</picture></a>", out)

    def test_webp_only_clip_needs_no_gif(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = sd.gen_recordings(self._clip_root(Path(tmp), gif=False, webp=True))
            self.assertIn('<img alt="Screen recording: A. c" src="docs/launch/media/clips/a.webp" width="100%">', out)
            self.assertNotIn(".gif", out)

    def test_clip_without_gif_or_webp_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(sd.SyncError):
            sd.gen_recordings(self._clip_root(Path(tmp), gif=False, webp=False))

    def test_real_readme_loads_webp_where_the_launch_lane_made_one(self) -> None:
        text = sd.gen_recordings(ctx("README.md"))
        data = json.loads((REPO / "docs/images/recordings/clips.json").read_text(encoding="utf-8"))
        for clip in data["featured"]:
            webp = REPO / "docs/launch/media/clips" / f"{clip['id']}.webp"
            if webp.is_file():
                self.assertIn(f'srcset="docs/launch/media/clips/{clip["id"]}.webp"', text)


if __name__ == "__main__":
    unittest.main()
