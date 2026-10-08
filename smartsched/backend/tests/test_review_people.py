"""Review M11 (instructor lists split into people) and M12 (strict AI person resolution) on the real
Bahar 2026 import."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.importers.normalize import split_person_names
from app.models import Instructor, SectionInstructor
from sqlalchemy import func, select

from tests import studio_support

bahar = studio_support.bahar

# cells of "Dersin 1./2. Öğretim Elemanı" in bahar_derslik_planlama_listesi_v5.xlsx (verbatim)
REAL_CELLS = {
    "Arş. Gör. Ecenur Aydemir, Arş. Gör. Ahmet Can Küçükkurt": ["Arş. Gör. Ecenur Aydemir", "Arş. Gör. Ahmet Can Küçükkurt"],
    "Doç. Dr. Hande Yapışlar\n&\nDoç. Dr. Meltem Kolgazi": ["Doç. Dr. Hande Yapışlar", "Doç. Dr. Meltem Kolgazi"],
    "Prof.Dr.Oğuz Polat,Prof.Dr.Işıl Pakiş": ["Prof.Dr.Oğuz Polat", "Prof.Dr.Işıl Pakiş"],
    "Prof. Dr. Eda Tahir Turanlı\n ve Öğr.Gör.Dr. Eda Suer": ["Prof. Dr. Eda Tahir Turanlı", "Öğr.Gör.Dr. Eda Suer"],
    "Öğr.Gör. Zehra Ayşin İlter Lewis;Öğr.Gör. Gülden Akyol": ["Öğr.Gör. Zehra Ayşin İlter Lewis", "Öğr.Gör. Gülden Akyol"],
    "Doç. Dr. M. Emin AKSOY, Öğr. Gör. Hayrettin Can SÜDOR": ["Doç. Dr. M. Emin AKSOY", "Öğr. Gör. Hayrettin Can SÜDOR"],
    "Prof. Dr. Halime Kenar,": ["Prof. Dr. Halime Kenar"],
    "Öğr,Gör. Nihan Laçin": ["Öğr Gör. Nihan Laçin"],
    "Dr. Öğr. Üyesi Ladan Hajhamidiasl Öğr. Gör. Dr. Cansu Gençalp": [
        "Dr. Öğr. Üyesi Ladan Hajhamidiasl",
        "Öğr. Gör. Dr. Cansu Gençalp",
    ],
    # free text in the column stays one entry; companies are not split on "ve"
    "Lütfen Pogram Koordinatörü Gökhan Aydın ve Bülent Yapıcı için yoklama, not giriş ve ders sonlandırma "
    "yetkilerini tanımlayınız.": [
        "Lütfen Pogram Koordinatörü Gökhan Aydın ve Bülent Yapıcı için yoklama, not giriş ve ders sonlandırma "
        "yetkilerini tanımlayınız."
    ],
    "Fatma Akgün - B4AFC Bilişim Teknolojileri ve Stratejik İş Çözümleri A.Ş": [
        "Fatma Akgün - B4AFC Bilişim Teknolojileri ve Stratejik İş Çözümleri A.Ş"
    ],
}


def test_m11_split_real_instructor_cells():
    for cell, want in REAL_CELLS.items():
        assert split_person_names(cell) == want, cell


async def test_m11_imported_bahar_has_people_not_lists(bahar):
    async with get_session_factory()() as s:
        names = list((await s.execute(select(Instructor.full_name))).scalars())
        listy = [n for n in names if len(split_person_names(n)) > 1]
        assert listy == []  # 53 list-names before the fix
        ecenur = (await s.execute(select(Instructor).where(Instructor.canonical_name == "ecenur aydemir"))).scalar_one()
        kucukkurt = (
            await s.execute(select(Instructor).where(Instructor.canonical_name == "ahmet can küçükkurt"))
        ).scalar_one()
        n_ecenur = (
            await s.execute(select(func.count()).where(SectionInstructor.instructor_id == ecenur.id))
        ).scalar_one()
        n_kk = (await s.execute(select(func.count()).where(SectionInstructor.instructor_id == kucukkurt.id))).scalar_one()
    assert n_ecenur >= 19 and n_kk >= 19  # one person across all her sections: clashes become visible
    # the solver sees one instructor key on all of them
    from app.models import ScheduleRun
    from app.services.solver_bridge import build_solver_input

    async with get_session_factory()() as s:
        inp, _ = await build_solver_input(s, ScheduleRun(id=-1, term_id=bahar.term_id, kind="COURSE", horizon="TERM", params={}, stats={}))
    key = f"INS:{ecenur.id}"
    assert sum(1 for e in inp.events if key in e.instructor_keys) >= 10


async def test_m12_strict_person_resolution_on_real_instructors(bahar):
    from app.ai.resolve import _status, load_term_context, resolve_instructor

    async with get_session_factory()() as s:
        ctx = await load_term_context(s, bahar.term_id)
    by_canon = {i.canonical_name: i for i in ctx.instructors}
    turanli = next(i for c, i in by_canon.items() if c == "eda tahir turanlı")
    # real people, with titles, other casing, missing diacritics, a middle name left out
    for text, want in (
        ("Prof. Dr. Eda Tahir Turanlı", turanli),
        ("EDA TAHİR TURANLI", turanli),
        ("Eda Tahir Turanli", turanli),
        ("Prof. Dr. Eda Turanlı", turanli),
    ):
        ent = resolve_instructor(ctx, text)
        assert ent.resolved_id == want.id, (text, ent)
    # invented names and near misses never resolve to a real person
    invented = ["Dr. Kemal Sunal", "Prof. Dr. Zeki Müren", "Ayşe Fatma Demirtaşlıoğlu", "Öğr. Gör. Ecenur Aydın"]
    two_word = [i for i in ctx.instructors if len(i.canonical_name.split()) == 2][:60]
    invented += [f"{i.full_name}oğlu" for i in two_word]  # surname changed: the old fuzzy match took them
    resolved_wrongly = []
    for text in invented:
        ent = resolve_instructor(ctx, text)
        if ent.resolved_id is not None:
            resolved_wrongly.append((text, ent.resolved_label))
        assert _status([], [ent], 0.9) == "needs_review"
    assert resolved_wrongly == []
    # one surname, ambiguous given names: not a guess
    keskin = [i for i in ctx.instructors if i.canonical_name.endswith(" keskin")]
    if len(keskin) >= 2:
        assert resolve_instructor(ctx, "Dr. Keskin").resolved_id is None
