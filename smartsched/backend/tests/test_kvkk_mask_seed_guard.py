"""KVKK-MASK (kvkk-mask-2026-10-18): every masked copy of a seed workbook passes the upload guard.

The masked final exam list once kept 2 cells the guard (app/core/kvkk_guard.py ``unmasked_hits``) refused: the
instructor column wrote a glued title ("Dr.Öğ.Üy.") the masker did not know, so the saved name list held the
fragments "Öğ." / "Üy." as name words and the guard read the kept title of the masked cell as two name words.
The synthetic test pins the shape; the slow one masks all 7 seed fixtures with a name list built the way
``stack.sh fixtures`` builds kvkk-names.json and expects 0 hits. The name list lives only in a temporary
directory removed at the end; only counts are asserted, never a value."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from app.core import kvkk_guard
from app.core.config import get_settings
from app.models import Base, Instructor
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND.parents[1] / "scripts" / "record" / "kvkk_mask.py"
FIXTURES = BACKEND / "tests" / "fixtures"
SEEDS = sorted(p for p in FIXTURES.iterdir() if p.is_file() and p.suffix.lower() in (".xlsx", ".csv"))
#: synthetic person written with the glued, abbreviated title of the exam list (never a real name)
GLUED = "Öğ. Üy. Aday Kural"


@pytest.fixture(scope="module")
def km():
    spec = importlib.util.spec_from_file_location("kvkk_mask_seed", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def guard_on(monkeypatch):
    def use(names_file: Path) -> None:
        monkeypatch.setattr(get_settings(), "kvkk_upload_guard", True)
        monkeypatch.setattr(get_settings(), "kvkk_names_file", str(names_file))
        kvkk_guard.reset_cache()

    yield use
    kvkk_guard.reset_cache()


def _xlsx(path: Path, cells: list[str]) -> None:
    wb = Workbook()
    wb.active.append(["Ders Kodu", "Öğretim Elemanı"])
    for c in cells:
        wb.active.append(["TST 101", c])
    wb.save(path)


def test_abbreviated_title_fragments_are_titles(km) -> None:
    for w in ("Öğ.", "Üy.", "Eğit.", "EĞİT.", "Psk.", "Gr.", "Gö."):
        assert km.is_title(w), w
    assert km.name_words("Dr. Öğ. Üy. Aday Kural") == ["Aday", "Kural"]
    assert km.saved_names(["Dr. Öğ. Üy. Aday Kural", "Aday Kural", "Öğ. Üy.", "Ayşe B. Kural"]) == [
        "Aday Kural",
        "Ayşe B. Kural",
    ]


def test_glued_title_cell_passes_the_guard_after_masking(km, tmp_path, guard_on, capsys) -> None:
    db = tmp_path / "rec.db"
    eng = create_engine(f"sqlite:///{db}")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Instructor(full_name=GLUED, canonical_name=GLUED.lower(), title="Dr."))
        s.commit()
    eng.dispose()
    names = tmp_path / "kvkk-names.json"
    assert km.main([str(db), "--save-names", str(names)]) == 0
    src, dst = tmp_path / "src", tmp_path / "fixtures"
    src.mkdir()
    _xlsx(src / "final.xlsx", ["Dr.Öğ.Üy.Aday Kural", "Dr. Öğr. Üyesi Aday KURAL"])
    assert km.main(["--workbooks", str(src), str(dst), "--names", str(names)]) == 0
    guard_on(names)
    assert kvkk_guard.unmasked_hits((src / "final.xlsx").read_bytes(), "final.xlsx") == 2  # the raw copy is caught
    assert kvkk_guard.unmasked_hits((dst / "final.xlsx").read_bytes(), "final.xlsx") == 0
    capsys.readouterr()


def test_an_older_name_list_with_titles_is_rewritten_by_the_workbook_pass(km, tmp_path, guard_on, capsys) -> None:
    """A $REC_WORKDIR saved before this fix keeps its kvkk-names.json (stack.sh only builds it when missing):
    the --workbooks pass strips the title tokens from it, so the guard reading the same file agrees."""
    names = tmp_path / "kvkk-names.json"
    names.write_text(json.dumps([f"Dr. {GLUED}"], ensure_ascii=False), encoding="utf-8")
    src, dst = tmp_path / "src", tmp_path / "fixtures"
    src.mkdir()
    _xlsx(src / "final.xlsx", ["Dr.Öğ.Üy.Aday Kural"])
    assert km.main(["--workbooks", str(src), str(dst), "--names", str(names)]) == 0
    assert json.loads(names.read_text(encoding="utf-8")) == ["Aday Kural"]
    guard_on(names)
    assert kvkk_guard.unmasked_hits((dst / "final.xlsx").read_bytes(), "final.xlsx") == 0
    capsys.readouterr()


@pytest.mark.slow
def test_every_masked_seed_workbook_passes_the_upload_guard(km, guard_on, capsys) -> None:
    """The real seed fixtures: the name list exactly as stack.sh ensure_fixtures builds it (throwaway import of the
    Bahar and Güz planning lists and the final exam list, then ``kvkk_mask.py DB --save-names``)."""
    assert len(SEEDS) == 7
    with tempfile.TemporaryDirectory(prefix="kvkk-seed-") as tmp:
        work = Path(tmp)
        url = f"sqlite+aiosqlite:///{work / 'names-build.db'}"
        env = {**os.environ, "PYTHONPATH": str(BACKEND)}
        for kind, wb, term in (
            ("planning-list", "bahar_derslik_planlama_listesi_v5.xlsx", "2026-BAHAR"),
            ("planning-list", "guz_derslik_planlama_2026_2027_v2.xlsx", "2026-GUZ"),
            ("exam-list", "final_planlama_listesi_2026_v2.xlsx", "2026-FINAL"),
        ):
            cmd = [sys.executable, "-m", "app.cli", "--database-url", url, "import", kind, str(FIXTURES / wb)]
            r = subprocess.run(
                [*cmd, "--term", term], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=600
            )
            assert r.returncode == 0, f"{kind} import failed (exit {r.returncode})"
        names = work / "kvkk-names.json"
        assert km.main([str(work / "names-build.db"), "--save-names", str(names)]) == 0
        assert km.main(["--workbooks", str(FIXTURES), str(work / "fixtures"), "--names", str(names)]) == 0
        capsys.readouterr()  # the script's own output stays out of the test log
        guard_on(names)
        assert kvkk_guard._pairs(str(names))  # a real list, not an empty one that passes everything
        hits = {}
        for seed in SEEDS:
            assert kvkk_guard.unmasked_hits(seed.read_bytes(), seed.name) > 0 or seed.suffix == ".csv"
            hits[seed.name] = kvkk_guard.unmasked_hits((work / "fixtures" / seed.name).read_bytes(), seed.name)
        assert hits == dict.fromkeys(hits, 0), {k: n for k, n in hits.items() if n}  # file names and counts only
