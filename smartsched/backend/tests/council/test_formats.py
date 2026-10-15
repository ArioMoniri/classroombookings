"""Format registry (P19-I1..I3): magic-byte detection, CSV/TSV decoding and delimiters, JSON, xls, ods, XML, ICS.

Acceptance runs on exports of the real Bahar planning list built in the test (tests/council/exports.py):
every export must give >= 99 % of the xlsx meetings, compared on their natural keys."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest
from app.core.safe_files import UnsafeFileError
from app.council import fastpath, formats
from app.council.formats_text import INTAKE_V1, decode_text, json_shape, sniff_delimiter
from app.council.render import RenderError, render_file

from tests.council import exports
from tests.council.conftest import BAHAR_LIST, ROOM_MASTER


def _key(r: dict) -> tuple:
    return (r["course_code"], r["section"], tuple(r["days"]), r["start"], r["end"], tuple(r["rooms"]))


@pytest.fixture(scope="module")
def xlsx_meetings() -> Counter:
    recs, _ = fastpath.planning_records(BAHAR_LIST, BAHAR_LIST.name)
    meetings = [r for r in recs if r["type"] == "meeting"]
    assert len(meetings) == 1524  # the real list: 1 529 rows, 5 without a course code
    return Counter(_key(r) for r in meetings)


def _fast(tmp_path: Path, name: str, data: bytes) -> tuple[str, list[dict], object]:
    """Store ``data`` like an upload and read it the way the council's fast path does."""
    path = tmp_path / f"0_{name}"
    path.write_bytes(data)
    rendered = render_file(data, name)
    shape = fastpath.detect_shape(rendered)
    assert shape is not None, (rendered.format, [g.summary() for g in rendered.grids])
    recs, _ = fastpath.records_for(shape, path, name, 2026)
    return shape, recs, rendered


def _overlap(expected: Counter, recs: list[dict]) -> float:
    got = Counter(_key(r) for r in recs if r["type"] == "meeting")
    return sum((expected & got).values()) / sum(expected.values())


# --------------------------------------------------------------------------- detection


def test_magic_bytes_win_over_the_extension():
    xlsx = BAHAR_LIST.read_bytes()
    assert formats.detect_format("liste.csv", xlsx) == "xlsx"  # a workbook renamed .csv is still a workbook
    assert formats.detect_format("odalar.xlsx", ROOM_MASTER.read_bytes()) == "csv"  # and a CSV renamed .xlsx
    assert formats.detect_format("x.json", b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n") == "ics"
    assert formats.detect_format("x.txt", b'{"schema": "smartsched.intake.v1"}') == "json"
    assert formats.detect_format("x.dat", b'<?xml version="1.0"?><a><b>1</b><b>2</b></a>') == "xml"
    # the extension breaks a tie inside the text family only: the same delimited bytes as .txt stay text
    data = b"kod;kapasite\nA101;58\nA102;40\n"
    assert formats.detect_format("odalar.csv", data) == "csv"
    assert formats.detect_format("odalar.txt", data) == "txt"


def test_ole2_and_odf_containers_are_told_apart_by_their_streams():
    with pytest.raises(RenderError, match="save the file as .docx"):
        formats.detect_format("memo.xls", exports.ole2_with_stream("WordDocument"))
    assert formats.detect_format("liste.doc", exports.ole2_with_stream("Workbook")) == "xls"
    ods = exports.ods_from_content('<table:table table:name="S"><table:table-row/></table:table>')
    assert formats.detect_format("liste.xlsx", ods) == "ods"
    with pytest.raises(RenderError, match="empty"):
        formats.detect_format("x.csv", b"")
    with pytest.raises(RenderError, match="unsupported"):
        formats.detect_format("x.bin", b"\x00\x01\x02binary\x00")


# --------------------------------------------------------------------------- csv / tsv decoding


def test_decoding_order_bom_then_strict_utf8_then_cp1254():
    word = "Perşembe İŞLETME ığüöç"
    assert decode_text(word.encode("cp1254")) == (word, "cp1254")  # İ=0xDD ş=0xFE ğ=0xF0
    assert decode_text(word.encode("utf-8")) == (word, "utf-8")
    assert decode_text(b"\xef\xbb\xbf" + word.encode("utf-8")) == (word, "utf-8-sig")
    assert decode_text(word.encode("utf-16")) == (word, "utf-16")


def test_delimiter_sep_line_then_sniffer_then_column_variance():
    assert sniff_delimiter("sep=|\na;b|c\n") == ("|", 1, "sep= line")
    assert sniff_delimiter("kod;ad;kapasite\nA101;Amfi, büyük;58\nA102;Lab;40\n")[0] == ";"
    assert sniff_delimiter("kod\tad\nA101\tAmfi\nA102\tLab\n")[0] == "\t"
    # comma decimals inside a ;-file: the steadiest column count decides
    text = "kod;oran;not\nA;1,5;x, y, z\nB;2,25;q\nC;3,0;r, s\n"
    assert sniff_delimiter(text)[0] == ";"


def test_bahar_exports_as_csv_and_tsv_give_the_xlsx_meetings(tmp_path, xlsx_meetings):
    """P19-I1 acceptance: cp1254 ';' CSV (comma decimals, dotted times) and UTF-8-BOM TSV >= 99 %."""
    cp = exports.csv_bytes(BAHAR_LIST, delimiter=";", encoding="cp1254", decimal=",", dotted_times=True)
    shape, recs, rendered = _fast(tmp_path, "bahar_v5.csv", cp)
    assert shape == "planning-list" and rendered.format == "csv"
    assert "read as cp1254, semicolon-separated" in rendered.warnings[0]
    assert _overlap(xlsx_meetings, recs) >= 0.99
    mat = next(r for r in recs if r["type"] == "meeting" and r["course_code"] == "MAT112")
    assert mat["days"] == [4] and mat["start"] == "13:30" and mat["rooms"] == ["A204"]  # "Perşembe", "13.30"
    assert mat["source"]["row"] == 2

    tsv = b"\xef\xbb\xbf" + exports.csv_bytes(BAHAR_LIST, delimiter="\t", encoding="utf-8")
    shape, recs, rendered = _fast(tmp_path, "bahar_v5.tsv", tsv)
    assert shape == "planning-list" and "utf-8-sig, tab-separated" in rendered.warnings[0]
    assert _overlap(xlsx_meetings, recs) >= 0.99


def test_bahar_export_as_json_gives_the_xlsx_meetings(tmp_path, xlsx_meetings):
    shape, recs, rendered = _fast(tmp_path, "bahar_v5.json", exports.json_records(BAHAR_LIST))
    assert shape == "planning-list" and rendered.format == "json" and rendered.grids[0].name == "records"
    assert _overlap(xlsx_meetings, recs) >= 0.99


# --------------------------------------------------------------------------- json limits + intake.v1


def test_json_caps_depth_objects_and_size():
    assert json_shape('{"a": [{"b": "[[[{"}]}') == (3, 2)  # brackets inside strings do not count
    deep = ("[" * 33 + "]" * 33).encode()
    with pytest.raises(UnsafeFileError) as e:
        formats.precheck("deep.json", deep)
    assert e.value.status == 413 and "33 levels" in e.value.message
    many = json.dumps([{"a": i} for i in range(50_001)]).encode()
    with pytest.raises(UnsafeFileError) as e:
        formats.precheck("many.json", many)
    assert e.value.status == 413 and "50001 objects" in e.value.message
    with pytest.raises(UnsafeFileError) as e:
        formats.precheck("big.json", b"[" + b'"x",' * (3 * 1024 * 1024) + b'"x"]')
    assert e.value.status == 413
    with pytest.raises(UnsafeFileError) as e:
        formats.precheck("bad.json", b'[{"a": 1,}]')
    assert e.value.status == 400


def intake_v1_doc() -> dict:
    return {
        "schema": INTAKE_V1,
        "rooms": [{"code": "A 101", "capacity": 58, "exam_capacity": 30, "building": "A", "tags": ["amfi"]}],
        "requests": [
            {
                "course_code": "MAT 112",
                "course_name": "Kalkülüs II",
                "section": 1,
                "program": "Bilgisayar Mühendisliği (İngilizce)",
                "faculty": "MDBF",
                "class_year": 1,
                "enrolment": "180",
                "day": "Perşembe",
                "start": "13.30",
                "end": "16:00",
                "rooms": "A 204",
                "instructors": "Dr.Öğr.Üyesi Elçim Elgün Kırımlı",
                "weeks": "1-14",
            }
        ],
        "timetable": [{"room": "A 204", "date": "2026-03-05", "start": "13:30", "end": "16:00", "text": "MAT 112"}],
    }


def test_native_intake_v1_is_read_as_records(tmp_path):
    data = json.dumps(intake_v1_doc(), ensure_ascii=False).encode()
    shape, recs, rendered = _fast(tmp_path, "intake.json", data)
    assert shape == "intake-v1" and [g.name for g in rendered.grids] == ["rooms", "requests", "timetable"]
    room, meeting, booking = recs
    assert room["code"] == "A101" and room["capacity"] == 58 and room["tags"] == ["AMFI"]
    assert meeting["course_code"] == "MAT112" and meeting["days"] == [4] and meeting["start"] == "13:30"
    assert meeting["rooms"] == ["A204"] and meeting["weeks"] == list(range(1, 15)) and meeting["enrolment"] == 180
    assert meeting["source"] == {"file": "intake.json", "table": "requests", "row": 1, "pointer": "/requests/0"}
    assert booking["day"] == 4 and booking["course_codes"] == ["MAT112"] and booking["room_code"] == "A204"
