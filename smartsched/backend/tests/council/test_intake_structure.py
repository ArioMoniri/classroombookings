"""Intake + structure analyst on the real workbooks and the files built from them."""

from __future__ import annotations

from functools import lru_cache

import pytest
from app.council import fastpath
from app.council.render import RenderError, render_file
from app.council.structure import analyze

from tests.council.conftest import (
    BAHAR_GRID,
    BAHAR_LIST,
    EN_CSV,
    EXAM_LIST,
    EXAM_PDF,
    FINAL_GRID,
    GUZ_GRID,
    GUZ_LIST,
    MEMO_DOCX,
    ROOM_MASTER,
    SCAN_PNG,
    TRANSPOSED,
)


@lru_cache(maxsize=16)
def _render(p):
    return render_file(p.read_bytes(), p.name)


@pytest.mark.parametrize(
    ("path", "shape"),
    [
        (BAHAR_LIST, "planning-list"),
        (GUZ_LIST, "planning-list"),
        (EXAM_LIST, "exam-list"),
        (BAHAR_GRID, "weekly-grid"),
        (GUZ_GRID, "weekly-grid"),
        (FINAL_GRID, "weekly-grid"),
        (ROOM_MASTER, "room-master"),
        (EN_CSV, None),
        (EXAM_PDF, None),
        (MEMO_DOCX, None),
        (TRANSPOSED, None),
    ],
)
def test_known_shapes_route_to_the_fast_path(path, shape):
    assert fastpath.detect_shape(_render(path)) == shape


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        (BAHAR_LIST, "request_list"),
        (GUZ_LIST, "request_list"),
        (EXAM_LIST, "exam_list"),
        (FINAL_GRID, "timetable_grid"),
        (GUZ_GRID, "timetable_grid"),
        (ROOM_MASTER, "room_list"),
        (EN_CSV, "request_list"),
        (EXAM_PDF, "exam_list"),
        (MEMO_DOCX, "room_list"),
        (TRANSPOSED, "timetable_grid"),
    ],
)
def test_general_path_classifies_the_first_table(path, kind):
    analyses = analyze(_render(path))
    assert analyses[0].kind == kind
    assert analyses[0].confidence >= 0.75


def test_planning_list_columns_are_mapped_with_confidence():
    a = analyze(_render(BAHAR_LIST))[0]
    m = {c.header.split("\n")[0].strip(): (c.field, c.confidence) for c in a.columns}
    assert m["Ders Kodu"][0] == "course_code"
    assert m["Dersin Günü"][0] == "day"
    assert m["Dersin"][0] in ("start_time", "end_time")  # "Dersin \nBaşlangıç Saati" (first line only)
    assert m["Derslik Talebi"][0] == "room_request"
    assert m["Derslik Planlama - Kesinleşen Derslik"][0] == "room"
    assert m["Derse Özel Açıklama"][0] == "notes"
    # weekly hours T/U/L/K are not SmartSched fields
    assert m["T"][0] is None and m["AKTS"][0] is None
    # the hidden summary sheet with repeated DERSLİK | KAPASİTE groups is a room list
    sayfa2 = analyze(_render(BAHAR_LIST))[1]
    assert sayfa2.kind == "room_list" and len(sayfa2.mapping()["room"]) == 7


def test_english_csv_headers_map_to_the_same_fields():
    a = analyze(_render(EN_CSV))[0]
    fields = {c.header: c.field for c in a.columns}
    assert fields["Course Code"] == "course_code"
    assert fields["Weekday"] == "day"
    assert fields["Start Time"] == "start_time" and fields["End Time"] == "end_time"
    assert fields["Assigned Room"] == "room" and fields["Requested Room"] == "room_request"
    assert fields["Lecturer"] == "instructor" and fields["Second Lecturer"] == "instructor2"
    assert a.language == "en"


def test_pdf_text_layer_becomes_one_table_across_pages():
    r = _render(EXAM_PDF)
    assert r.format == "pdf" and not r.needs_vision
    assert len(r.grids) == 1 and r.grids[0].n_rows == 121  # header + 120 real rows over 3 pages
    assert r.grids[0].ref(r.grids[0].n_rows - 1)["page"] == 3


def test_transposed_grid_is_detected_horizontally():
    a = analyze(_render(TRANSPOSED))[0]
    assert {ax.orientation for ax in a.axes} == {"horizontal"}
    assert len(a.axes) == 2 and a.axes[0].slots[0] == ["08:30", "09:10"]


def test_grid_axes_on_the_real_board():
    a = analyze(_render(BAHAR_GRID))[0]
    assert [(ax.start, ax.end) for ax in a.axes] == [(2, 19), (22, 39)]
    assert len(a.axes[0].slots) == 18


def test_image_needs_vision_and_unsupported_formats_are_explained():
    r = _render(SCAN_PNG)
    assert r.needs_vision and r.media_type == "image/png" and not r.grids
    with pytest.raises(RenderError, match="save the file as .xlsx"):
        render_file(b"\xd0\xcf\x11\xe0legacy", "old.xls")
    with pytest.raises(RenderError, match="empty"):
        render_file(b"", "x.csv")
