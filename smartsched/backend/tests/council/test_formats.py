"""Format registry (P19-I1..I3): magic-byte detection, CSV/TSV decoding and delimiters, JSON, xls, ods, XML, ICS.

Acceptance runs on exports of the real Bahar planning list built in the test (tests/council/exports.py):
every export must give >= 99 % of the xlsx meetings, compared on their natural keys."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
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


# --------------------------------------------------------------------------- xls + ods (P19-I2)


def _strip(r: dict) -> dict:
    return {k: v for k, v in r.items() if k not in ("source", "warnings")}


@pytest.fixture(scope="module")
def libreoffice_copies(tmp_path_factory) -> dict[str, Path]:
    if exports.soffice() is None:
        pytest.skip("LibreOffice (soffice) is not installed: no writer for .xls / .ods on this machine")
    d = tmp_path_factory.mktemp("lo")
    return {fmt: exports.convert(BAHAR_LIST, fmt, d) for fmt in ("xls", "ods")}


@pytest.mark.slow
@pytest.mark.parametrize("fmt", ["xls", "ods"])
def test_bahar_saved_as_xls_and_ods_gives_the_xlsx_records(libreoffice_copies, fmt):
    """P19-I2 acceptance: the Bahar list saved by LibreOffice as .xls / .ods gives the xlsx records."""
    path = libreoffice_copies[fmt]
    rendered = render_file(path.read_bytes(), path.name)
    assert rendered.format == fmt and [g.name for g in rendered.grids] == ["Sayfa1", "Sayfa2"]
    assert fastpath.detect_shape(rendered) == "planning-list"
    recs, _ = fastpath.records_for("planning-list", path, path.name, 2026)
    base, _ = fastpath.planning_records(BAHAR_LIST, BAHAR_LIST.name)
    meetings = [r for r in recs if r["type"] == "meeting"]
    expected = [r for r in base if r["type"] == "meeting"]
    assert len(meetings) == len(expected) == 1524
    same = sum(_strip(a) == _strip(b) for a, b in zip(expected, meetings, strict=True))
    # .ods: every record; .xls: LibreOffice writes row 219's course name and start as 0 (its own conversion)
    assert same >= (1524 if fmt == "ods" else 1523), same
    rooms = [_strip(r) for r in recs if r["type"] == "room"]
    assert rooms == [_strip(r) for r in base if r["type"] == "room"] and len(rooms) == 54  # Sayfa2 buckets


def _ods_row(*cells: str, repeat: int = 1) -> str:
    rep = f' table:number-rows-repeated="{repeat}"' if repeat > 1 else ""
    return f"<table:table-row{rep}>{''.join(cells)}</table:table-row>"


def _ods_cell(text: str = "", repeat: int = 1, attrs: str = "") -> str:
    extra = f" {attrs}" if attrs else ""
    rep = f' table:number-columns-repeated="{repeat}"' if repeat > 1 else ""
    body = f"<text:p>{text}</text:p>" if text else ""
    return f"<table:table-cell{rep}{extra}>{body}</table:table-cell>"


def test_ods_reader_values_repeats_and_merges():
    content = (
        '<table:table table:name="Sayfa1">'
        + _ods_row(_ods_cell("Ders Kodu"), _ods_cell("Gün"), _ods_cell("Başlangıç"), _ods_cell("Kapasite"))
        + _ods_row(
            _ods_cell("MAT 112"),
            _ods_cell("Perşembe"),
            _ods_cell("13:30", attrs='office:value-type="time" office:time-value="PT13H29M59.999999S"'),
            _ods_cell("180,0", attrs='office:value-type="float" office:value="180"'),
            _ods_cell(repeat=16000),  # LibreOffice's trailing filler: dropped, never expanded
        )
        + _ods_row(_ods_cell("İŞL 101", repeat=2), _ods_cell(), _ods_cell("x"), repeat=2)
        + _ods_row(_ods_cell(), repeat=1048000)  # trailing empty rows
        + "</table:table>"
    )
    r = render_file(exports.ods_from_content(content), "liste.ods")
    g = r.grids[0]
    assert g.cells == [
        ["Ders Kodu", "Gün", "Başlangıç", "Kapasite"],
        ["MAT 112", "Perşembe", "13:30", "180"],
        ["İŞL 101", "İŞL 101", "", "x"],
        ["İŞL 101", "İŞL 101", "", "x"],
    ]
    merged = '<table:table table:name="S">' + _ods_row(
        _ods_cell("A 101", attrs='table:number-columns-spanned="2"'), "<table:covered-table-cell/>", _ods_cell("z")
    )
    g = render_file(exports.ods_from_content(merged + "</table:table>"), "m.ods").grids[0]
    assert g.cells == [["A 101", "A 101", "z"]] and g.merged == [(0, 0, 0, 1)]


@pytest.mark.parametrize(
    "content",
    [
        _ods_row(_ods_cell("bomb", repeat=16384)),  # one value repeated over 16 384 columns
        _ods_row(_ods_cell("bomb"), repeat=1_000_000),  # one row repeated a million times
        _ods_row(_ods_cell("bomb", attrs='table:number-columns-spanned="16384"')),
    ],
    ids=["columns-repeated", "rows-repeated", "spanned"],
)
def test_ods_repeat_bombs_are_413(content):
    data = exports.ods_from_content(f'<table:table table:name="S">{content}</table:table>')
    assert len(data) < 4096
    with pytest.raises(UnsafeFileError) as e:
        formats.precheck("bomb.ods", data)
    assert e.value.status == 413
    with pytest.raises(UnsafeFileError):
        render_file(data, "bomb.ods")


def test_ods_with_a_dtd_is_refused():
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(exports.ods_from_content(""))) as src, zipfile.ZipFile(buf, "w") as dst:
        for info in src.infolist():
            body = src.read(info)
            if info.filename == "content.xml":
                body = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]>' + body.split(b"?>", 1)[1]
            dst.writestr(info, body)
    with pytest.raises(UnsafeFileError) as e:
        formats.precheck("dtd.ods", buf.getvalue())
    assert e.value.status == 400


# --------------------------------------------------------------------------- xml + ics (P19-I3)

BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">]>
<rooms><room code="A 101">&lol3;</room><room code="A 102">&lol3;</room></rooms>"""


def test_spreadsheetml_2003_export_gives_the_xlsx_meetings(tmp_path, xlsx_meetings):
    shape, recs, rendered = _fast(tmp_path, "bahar_v5.xml", exports.spreadsheetml(BAHAR_LIST))
    assert shape == "planning-list" and rendered.format == "xml"
    assert [g.name for g in rendered.grids] == ["Sayfa1", "Sayfa2"]
    assert _overlap(xlsx_meetings, recs) >= 0.99
    assert len([r for r in recs if r["type"] == "room"]) == 54  # the Sayfa2 capacity buckets survive


def test_generic_xml_repeated_siblings_become_rows():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<kampus><bina ad="A"><derslik kod="A 101"><kapasite>58</kapasite><etiket>AMFİ</etiket></derslik>
<derslik kod="A 102"><kapasite>40</kapasite></derslik></bina>
<bina ad="B"><derslik kod="B 201"><kapasite>36</kapasite></derslik></bina></kampus>""".encode()
    g = render_file(xml, "kampus.xml").grids
    assert [x.name for x in g] == ["bina/derslik"]  # the leaf records; the building is carried as a column
    rooms = g[0].cells
    assert rooms[0] == ["@kod", "kapasite", "etiket", "bina@ad"]
    assert rooms[1] == ["A 101", "58", "AMFİ", "A"] and rooms[3] == ["B 201", "36", "", "B"]
    table = b"<t><tr><td>kod</td><td>kapasite</td></tr><tr><td>A 101</td><td>58</td></tr></t>"
    assert render_file(table, "t.xml").grids[0].cells == [["td"], ["kod, kapasite"], ["A 101, 58"]]


def test_xml_with_entities_is_400_and_too_many_elements_413():
    for data in (BILLION_LAUGHS, b'<?xml version="1.0"?><!DOCTYPE a SYSTEM "file:///etc/passwd"><a/>'):
        with pytest.raises(UnsafeFileError) as e:
            formats.precheck("rooms.xml", data)
        assert e.value.status == 400 and "DTD" in e.value.message
    many = b"<a>" + b"<b/>" * 200_001 + b"</a>"
    with pytest.raises(UnsafeFileError) as e:
        formats.precheck("many.xml", many)
    assert e.value.status == 413


def _ics(*events: str) -> bytes:
    body = "".join(f"BEGIN:VEVENT\r\n{e.strip()}\r\nEND:VEVENT\r\n" for e in events)
    return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//EN\r\n{body}END:VCALENDAR\r\n".encode()


def test_ics_rrule_is_clipped_and_people_are_dropped():
    from app.council.formats_ics import ics_records, instances

    weekly = """UID:mat112@uni
DTSTART;TZID=Europe/Istanbul:20260302T133000
DTEND;TZID=Europe/Istanbul:20260302T160000
RRULE:FREQ=WEEKLY;BYDAY=MO;UNTIL=20260601T000000Z
EXDATE;TZID=Europe/Istanbul:20260420T133000
SUMMARY:MAT 112 §1 Kalkülüs II
LOCATION:A 204 / A 205
ORGANIZER;CN=Elçim Kırımlı:mailto:elcim@uni.edu.tr
ATTENDEE;CN=Öğrenci:mailto:ogr@uni.edu.tr
DESCRIPTION:Sorular: elcim@uni.edu.tr"""
    utc = "UID:u2\r\nDTSTART:20260303T053000Z\r\nDTEND:20260303T071000Z\r\nSUMMARY:FZT 2002\r\nLOCATION:B 101"
    data = _ics(weekly, utc)
    found, warnings = instances(data, formats.REGISTRY["ics"].limits)
    mondays = [i for i in found if i.uid == "mat112@uni"]
    assert len(mondays) == 12 and all(i.when.isoweekday() == 1 for i in mondays)  # 2 Mar-25 May, no 20 Apr
    assert str(mondays[0].start) == "13:30:00" and str(mondays[0].end) == "16:00:00"
    recs, _ = ics_records(data, "feed.ics")
    first = recs[0]
    assert first["room_code"] == "A204" and recs[1]["room_code"] == "A205" and first["course_codes"] == ["MAT112"]
    assert first["section"] == "1" and first["day"] == 1 and first["date"] == "2026-03-02"
    blob = json.dumps(recs, ensure_ascii=False)
    assert "elcim@" not in blob and "Kırımlı" not in blob and "ogr@" not in blob  # no ORGANIZER / ATTENDEE
    fzt = next(r for r in recs if r["course_codes"] == ["FZT2002"])
    assert (fzt["start"], fzt["end"]) == ("08:30", "10:10")  # UTC -> Europe/Istanbul
    # a window (the term) clips the expansion
    found, _ = instances(data, formats.REGISTRY["ics"].limits, window=(date(2026, 3, 1), date(2026, 3, 31)))
    assert len([i for i in found if i.uid == "mat112@uni"]) == 5


def test_ics_expansion_is_bounded():
    from app.council.formats_ics import instances

    lim = formats.REGISTRY["ics"].limits
    endless = "UID:e\r\nDTSTART:20260101T080000\r\nRRULE:FREQ=DAILY\r\nSUMMARY:x\r\nLOCATION:A 101"
    found, warnings = instances(_ics(endless), lim, window=(date(2026, 1, 1), date(2100, 1, 1)))
    assert len(found) == lim.max_instances == 5000 and "stopped at 5000" in warnings[-1]
    secondly = "UID:s\r\nDTSTART:20260101T080000\r\nRRULE:FREQ=SECONDLY\r\nSUMMARY:x\r\nLOCATION:A 101"
    found, warnings = instances(_ics(secondly), lim)
    assert found == [] and "SECONDLY recurrence is not a timetable" in warnings[0]
    old = "UID:o\r\nDTSTART:14000101T080000\r\nRRULE:FREQ=DAILY\r\nSUMMARY:x\r\nLOCATION:A 101"
    found, warnings = instances(_ics(old), lim, window=(date(2026, 1, 1), date(2026, 2, 1)))
    assert "steps" in warnings[-1]  # 626 years of daily steps before the window: stopped, not hung
