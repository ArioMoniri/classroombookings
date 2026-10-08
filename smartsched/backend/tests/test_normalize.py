"""Unit tests for app.importers.normalize — every quirk from docs/DATA_ANALYSIS.md."""

from __future__ import annotations

from datetime import date, datetime, time

import pytest
from app.importers import normalize as n

# --- text basics -------------------------------------------------------------


def test_clean_text_handles_nbsp_dash_and_whitespace():
    assert n.clean_text("\xa0") is None
    assert n.clean_text("-") is None
    assert n.clean_text("--") is None
    assert n.clean_text(None) is None
    assert n.clean_text("  A 204 ") == "A 204"
    assert n.clean_text("Moleküler Biyoloji ve \n Genetik") == "Moleküler Biyoloji ve Genetik"
    assert n.clean_text(12) == "12"


def test_turkish_case():
    assert n.tr_lower("SALI") == "salı"
    assert n.tr_lower("İNG") == "ing"
    assert n.tr_upper("ing") == "İNG"
    assert n.tr_upper("ısı") == "ISI"
    assert n.tr_casefold("PERŞEMBE ") == "perşembe"


# --- course codes ------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("MAT 112", "MAT112"),
        ("MAT112", "MAT112"),
        (" YENİ DERS\nACU 311", "ACU311"),
        ("mbg 698", "MBG698"),
        ("SYS019", "SYS019"),
        ("ACU1001", "ACU1001"),
        ("FZT 3002", "FZT3002"),
        ("İNG 101", "ING101"),  # usability U6: the dotted capital İ folds to I
        ("ACU", None),
        ("\xa0", None),
        (None, None),
    ],
)
def test_canon_course_code(raw, expected):
    assert n.canon_course_code(raw) == expected


def test_display_course_code():
    assert n.display_course_code("MAT112") == "MAT 112"
    assert n.display_course_code("ACU1001") == "ACU 1001"
    assert n.display_course_code("SYS019A") == "SYS 019A"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("HEM 334 / NRS 304", ["HEM334", "NRS304"]),
        ("MBG 598\nmbg 698\nmbg 408", ["MBG598", "MBG698", "MBG408"]),
        ("ING 101 /105", ["ING101", "ING105"]),
        ("ING 102/106", ["ING102", "ING106"]),
        ("HEM 333 NRS 303", ["HEM333", "NRS303"]),
        ("BME 313 (MEG 303) ", ["BME313", "MEG303"]),
        ("EHM 112 B1+", ["EHM112"]),
        ("MAT 102 / MAT 112", ["MAT102", "MAT112"]),
        ("HAZIRLIK", []),
        ("NAFİYE HOCA", []),
        ("Hemşirelik Bitirme Sınavı", []),
        ("11.12.2026 tarihinde", []),
    ],
)
def test_extract_course_codes(raw, expected):
    assert n.extract_course_codes(raw) == expected


# --- days --------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,days,flexible,needs_room",
    [
        ("Pazartesi", [1], False, True),
        ("salı", [2], False, True),
        ("PERŞEMBE", [4], False, True),
        ("Cuma ", [5], False, True),
        ("Cumartesi", [6], False, True),
        ("Pazar", [7], False, True),
        ("Perşembe/Cuma", [4, 5], False, True),
        ("Çarşamba- Perşembe", [3, 4], False, True),
        ("Salı / Çarşamba / Perşembe / Cuma", [2, 3, 4, 5], False, True),
        ("Salı veya Çarşamba", [2, 3], True, True),
        ("Çarşamba veya Perşembe ", [3, 4], True, True),
        ("Perşembe (uygulama)", [4], False, True),
        ("Çarşamba (Teorik)", [3], False, True),
        ("Hafta içi hergün", [1, 2, 3, 4, 5], True, True),
        ("Belirli günü yok", [], True, True),
        ("Danışman ile görüşülerek belirlenecek", [], True, True),
        ("Asenkron", [], False, False),
        ("UZEM", [], False, False),
        ("Uzem", [], False, False),
        ("ASG Hastanelerinde yapılacak.", [], False, False),
        ("Yaz döneminde yapılacak.", [], False, False),
        ("Tez dersi olduğu için gün saat verilmemiştir", [], True, False),
        (None, [], False, None),
        ("\xa0", [], False, None),
    ],
)
def test_parse_day(raw, days, flexible, needs_room):
    r = n.parse_day(raw)
    assert r.days == days
    assert r.flexible is flexible
    assert r.needs_room is needs_room


def test_parse_day_rejects_time_value_with_warning():
    r = n.parse_day(time(13, 30))
    assert r.days == [] and r.warnings


def test_parse_day_note_kept():
    assert n.parse_day("Perşembe (uygulama)").note == "uygulama"


# --- times & periods ---------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        (time(8, 30), time(8, 30)),
        (datetime(1900, 1, 1, 13, 30), time(13, 30)),
        (datetime(2025, 10, 10, 10, 10), time(10, 10)),
        (datetime(1900, 1, 11, 0, 0), time(11, 0)),  # bare "11" formatted as a date
        (0.5208333, time(12, 30)),
        (0.5, time(12, 0)),
        (12, time(12, 0)),
        (0, None),
        ("09.00", time(9, 0)),
        ("09:00", time(9, 0)),
        (" 13:30", time(13, 30)),
        ("18.00", time(18, 0)),
        ("8:30", time(8, 30)),
        ("-", None),
        ("\xa0", None),
        ("UZEM", None),
        ("Tüm gün", None),
        (None, None),
    ],
)
def test_parse_time(raw, expected):
    assert n.parse_time(raw) == expected


def test_period_grid_has_18_slots():
    assert len(n.PERIODS) == 18
    assert n.PERIODS[0].start == time(8, 30) and n.PERIODS[0].end == time(9, 10)
    assert n.PERIODS[11].start == time(17, 30) and n.PERIODS[11].end == time(18, 0)
    assert n.PERIODS[17].start == time(22, 10) and n.PERIODS[17].end == time(22, 50)


@pytest.mark.parametrize(
    "start,end,sp,ep",
    [
        (time(13, 30), time(16, 0), 7, 9),
        (time(11, 0), time(13, 20), 4, 6),
        (time(11, 0), time(12, 30), 4, 5),
        (time(8, 30), time(10, 0), 1, 2),
        (time(9, 20), time(11, 40), 2, 4),
        (time(18, 0), time(22, 0), 13, 17),
        (time(17, 30), time(18, 0), 12, 12),
        (time(13, 30), time(17, 30), 7, 11),
        (time(16, 0), time(17, 30), 10, 11),
        (time(20, 30), time(22, 50), 16, 18),
    ],
)
def test_time_range_to_periods_exact(start, end, sp, ep):
    r = n.time_range_to_periods(start, end)
    assert (r.start_period, r.end_period) == (sp, ep)
    assert not r.warnings


@pytest.mark.parametrize(
    "start,end,sp,ep",
    [
        (time(9, 0), time(10, 50), 1, 3),  # 09:00 is not on the grid -> snapped into P1
        (time(9, 30), time(12, 30), 2, 5),
        (time(10, 0), time(12, 0), 3, 5),  # 10:00 = end of P2 (uses none of it); ends mid-P5 -> conservative
        (time(15, 0), time(16, 40), 9, 10),  # Bahar CSE 102: 15:00 is the P8/P9 break, not P8
        (time(13, 0), time(15, 0), 6, 8),
        (time(8, 0), time(10, 0), 1, 2),  # before grid start
        (time(17, 40), time(20, 20), 12, 15),
    ],
)
def test_time_range_to_periods_snaps_with_warning(start, end, sp, ep):
    r = n.time_range_to_periods(start, end)
    assert (r.start_period, r.end_period) == (sp, ep)
    assert r.warnings


def test_time_to_period_invalid():
    assert n.time_to_period(time(23, 30)).period is None
    r = n.time_range_to_periods(time(13, 30), time(13, 0))
    assert r.start_period is None and r.warnings


def test_parse_time_slot():
    assert n.parse_time_slot("08:30-09:10") == (time(8, 30), time(9, 10))
    assert n.parse_time_slot("18.00-18.40") == (time(18, 0), time(18, 40))
    assert n.parse_time_slot("22.10-22-50") == (time(22, 10), time(22, 50))
    assert n.parse_time_slot("foo") is None


# --- rooms -------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("A 101 / A 106", ["A101", "A106"]),
        ("A 101 - A 102", ["A101", "A102"]),
        ("A107/ B 207", ["A107", "B207"]),
        ("C z01", ["CZ01"]),
        ("Cz01", ["CZ01"]),
        ("CZ02", ["CZ02"]),
        ("B 207\nPC", ["B207"]),
        ("a 106", ["A106"]),
        ("d 107", ["D107"]),
        (" A 204", ["A204"]),
        ("A301-A302-A303 MULTİDİSİPLİN", ["A301", "A302", "A303"]),
        ("A 101 / A 106 / A 107 / A 108", ["A101", "A106", "A107", "A108"]),
        ("D 302 - A 104", ["D302", "A104"]),
        ("A103 (Bilg. Lab. Zorunlu)", ["A103"]),
        ("A 105 nolu bilgi lab", ["A105"]),
        ("72 kişilik C blok 601-602 vb", ["C601", "C602"]),
        ("ANS138 ile aynı derslik", []),
        ("Online", []),
        ("Derslik talebi yok", []),
        ("B 3 Toplantı Odası", []),
        ("11.12.2026 tarihinde tam gün", []),
        (None, []),
    ],
)
def test_parse_room_codes(raw, expected):
    assert n.parse_room_codes(raw) == expected


def test_display_room_code():
    assert n.display_room_code("A101") == "A 101"
    assert n.display_room_code("CZ01") == "C z01"


@pytest.mark.parametrize(
    "raw,code,cap,tags",
    [
        ("A 101\n (58)", "A101", 58, []),
        ("A 201\n(96)\nTIP", "A201", 96, ["TIP"]),
        ("B 207\nPC", "B207", None, ["PC"]),
        ("D 107", "D107", None, []),
        ("C z01\n(30)", "CZ01", 30, []),
        ("A305\n(64)", "A305", 64, []),
        ("B 207  (60)", "B207", 60, []),
        ("B 406 (80)", "B406", 80, []),
        ("C402\n(35)", "C402", 35, []),
    ],
)
def test_parse_room_header(raw, code, cap, tags):
    h = n.parse_room_header(raw)
    assert h is not None
    assert h.code == code and h.capacity == cap and h.tags == tags


def test_parse_room_header_rejects_non_room():
    assert n.parse_room_header("Pazartesi") is None
    assert n.parse_room_header("08:30-09:10") is None
    assert n.parse_room_header(None) is None
    assert n.parse_room_header("HEM 242") is None


def test_parse_definitive_rooms():
    assert n.parse_definitive_rooms("A 101 / A 106 / A 107").room_codes == ["A101", "A106", "A107"]
    assert n.parse_definitive_rooms("Online").status == "NO_ROOM"
    assert n.parse_definitive_rooms("Derslik talebi yok").status == "NO_ROOM"
    assert n.parse_definitive_rooms("Hastane Uygulaması").status == "NO_ROOM"
    assert n.parse_definitive_rooms("UZEM").status == "NO_ROOM"
    assert n.parse_definitive_rooms("sınıf iptal").status == "CANCELLED"
    assert n.parse_definitive_rooms("kapatıldı").status == "CANCELLED"
    assert n.parse_definitive_rooms("Laboratuvar").status == "NO_ROOM"
    assert n.parse_definitive_rooms(None).status == "EMPTY"
    assert n.parse_definitive_rooms("Yabancı Diller Tarafından Paylaşılacak").status == "UNKNOWN"


# --- weeks -------------------------------------------------------------------


ALL14 = list(range(1, 15))


@pytest.mark.parametrize(
    "raw,weeks",
    [
        (None, ALL14),
        ("Hepsi", ALL14),
        ("Tüm haftalar", ALL14),
        ("Tüm dönem", ALL14),
        ("Tüm", ALL14),
        ("her hafta", ALL14),
        ("Dönemin tamamı", ALL14),
        (14, ALL14),
        ("14", ALL14),
        ("14 hafta", ALL14),
        ("14 HAFTA", ALL14),
        ("1-14", ALL14),
        ("1-14.haftalar", ALL14),
        ("1.-14. haftalar arası", ALL14),
        ("1 İLA 14 ", ALL14),
        ("1,2,3,4,5,6,7,8,9,10,11,12,13,14", ALL14),
        ("100%", ALL14),
        ("1,2,3", [1, 2, 3]),
        ("1-5. HAFTALAR DERSLİKTE, 6-14. HAFTALAR UYGULAMA HASTANELERİNDE YAPILACAKTIR", [1, 2, 3, 4, 5]),
        ("2., 3., 4., 5. ve 6. haftalar derslik kullanılacak", [2, 3, 4, 5, 6]),
        ("11., 12., 13. ve 14. haftalarda", [11, 12, 13, 14]),
        ("12., 13. ve 14. hafta derslik kullanılacaktır.", [12, 13, 14]),
        ("İlk 2 hafta", [1, 2]),
        ("İlk 9 hafta", list(range(1, 10))),
        ("İlk 11 hafta kullanılacak.", list(range(1, 12))),
        ("Ders ilk 6 hafta derslikte işlenecek, sonra Radyoloji Laboratuvarında işlenecektir.", list(range(1, 7))),
        ("12. Hafta tam gün derslik ihtiyacı ", [12]),
    ],
)
def test_parse_weeks(raw, weeks):
    assert n.parse_weeks(raw).weeks == weeks


def test_parse_weeks_fractions_and_flags_warn_but_default_to_all():
    for raw in (0.5, "0.5", 0, 0.4, "x", "-", "\xa0", 1, "Hayır", "Evet"):
        r = n.parse_weeks(raw)
        assert r.weeks == ALL14, raw
        assert r.all_weeks is True


def test_parse_weeks_overflow_capped_with_warning():
    r = n.parse_weeks("16 hafta ")
    assert r.weeks == ALL14 and r.warnings
    r = n.parse_weeks("1-14", max_week=16)
    assert r.weeks == ALL14


def test_parse_weeks_no_room_phrases():
    for raw in (
        "Online",
        "UZEM",
        "Ders çevrimiçi işlenecektir.",
        "Hastanede yapılacaktır.",
        "Ders laboratuvarda işlenecektir.",
    ):
        r = n.parse_weeks(raw)
        assert r.weeks == [] and r.needs_room is False, raw


def test_parse_weeks_vize():
    r = n.parse_weeks("Vize dönemine dek")
    assert r.weeks == list(range(1, 8)) and r.warnings


# --- mode / pct / class year / ints ------------------------------------------


@pytest.mark.parametrize(
    "raw,mode,needs_room",
    [
        ("Yüz yüze", "F2F", True),
        ("YÜZ YÜZE", "F2F", True),
        ("Yüzyüze", "F2F", True),
        ("Derslik", "F2F", True),
        ("DERSLİK", "F2F", True),
        ("Online", "ONLINE", False),
        ("ONline", "ONLINE", False),
        ("Çevrimiçi", "ONLINE", False),
        ("Hibrit", "HYBRID", True),
        ("hibrit", "HYBRID", True),
        ("UZEM", "UZEM", False),
        ("Asenkron", "ASYNC", False),
        ("Hastane", "HOSPITAL", False),
        ("Simülasyon Eğitimi", "SIMULATION", True),
        ("Lab", "OTHER", False),
        ("14 hafta", "OTHER", True),
        (
            "İlk 9 hafta ders online işlenecektir, kalan haftalarda saat değişikliği yapılarak derslikte işlenecektir.",
            "HYBRID",
            True,
        ),
        ("Alttan alan öğrenciler için açılmıştır. Derslik kullanılmayacaktır.", "OTHER", False),
        (None, "F2F", True),
        ("\xa0", "F2F", True),
    ],
)
def test_parse_mode(raw, mode, needs_room):
    r = n.parse_mode(raw)
    assert (r.mode, r.needs_room) == (mode, needs_room)


@pytest.mark.parametrize(
    "raw,expected",
    [
        (0, 0),
        ("0", 0),
        (1, 100),
        (0.5, 50),
        (0.3, 30),
        (0.75, 75),
        (50, 50),
        (100, 100),
        ("100%%", 100),
        ("100%", 100),
        ("50 %", 50),
        ("UZEM", 100),
        ("x", None),
        ("yok", 0),
        ("-", None),
        ("\xa0", None),
        (None, None),
    ],
)
def test_parse_pct(raw, expected):
    assert n.parse_pct(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        (1, [1]),
        ("1. Sınıf", [1]),
        ("1.Sınıf ", [1]),
        ("4. Sınıf ", [4]),
        (1.2, [1, 2]),
        ("1&2", [1, 2]),
        ("1,2,3", [1, 2, 3]),
        (0, [0]),
        (5, [5]),
        ("-", []),
        (None, []),
    ],
)
def test_parse_class_year(raw, expected):
    assert n.parse_class_year(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        (180, 180),
        ("2", 2),
        (4.0, 4),
        ("4,5", 4),  # rounds half-up for ints is not required; we floor toward int()
        ("\xa0", None),
        ("-", None),
        (None, None),
        (time(12, 30), None),
        ("Çarşamba", None),
        ("T", None),
        ("120 kişi", 120),
    ],
)
def test_parse_int_loose(raw, expected):
    assert n.parse_int_loose(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [("4,5", 4.5), ("4..5", 4.5), (",", None), (4, 4.0), ("3", 3.0), (None, None), ("\xa0", None)],
)
def test_parse_float_loose(raw, expected):
    assert n.parse_float_loose(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        (1, 1),
        ("1. Yarıyıl", 1),
        ("6.Yarıyıl", 6),
        ("2025/Güz", 1),
        ("Güz", 1),
        ("Bahar", 2),
        ("BAHAR", 2),
        ("Güz- Bahar", None),
        ("Bilim Tarihi ", None),
        (None, None),
    ],
)
def test_parse_semester(raw, expected):
    assert n.parse_semester(raw) == expected


# --- people ------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,title,canonical",
    [
        ("Prof. Dr. ATA AKIN", "Prof. Dr.", "ata akın"),
        ("Dr.Öğr.Üyesi Elçim Elgün Kırımlı", "Dr. Öğr. Üyesi", "elçim elgün kırımlı"),
        ("Dr. Öğr. Üyesi NAFİYE ÇİĞDEM AKTEKİN", "Dr. Öğr. Üyesi", "nafiye çiğdem aktekin"),
        ("Dr. Öğr. Üyesi Nafiye Çiğdem Aktekin", "Dr. Öğr. Üyesi", "nafiye çiğdem aktekin"),
        ("Doç. Dr. Nuray ALACA", "Doç. Dr.", "nuray alaca"),
        ("Öğr. Gör. Dr. Melin Levent Yuna", "Öğr. Gör. Dr.", "melin levent yuna"),
        ("Öğr.Gör.Dr. Mahsa Ziraksima", "Öğr. Gör. Dr.", "mahsa ziraksima"),
        ("Arş. Gör. Meryem BEKTAŞ KARAKUŞ\xa0", "Arş. Gör.", "meryem bektaş karakuş"),
        ("ARŞ. GÖR. DENİZHAN YILDIZBAŞ\n", "Arş. Gör.", "denizhan yıldızbaş"),
        ("Uzm. Eğt. Erkan Evrendilek", "Uzm. Eğt.", "erkan evrendilek"),
        ("Uzm. Eğitmen Rana Güngör", "Uzm. Eğitmen", "rana güngör"),
        ("PROF. DR. ESRA UĞUR", "Prof. Dr.", "esra uğur"),
        ("Biyofizik Anabilim Dalı", None, "biyofizik anabilim dalı"),
        ("Dr. Öğr. Üyesi Ş. Ecem ÖRKÜ", "Dr. Öğr. Üyesi", "ş. ecem örkü"),
    ],
)
def test_canon_person_name(raw, title, canonical):
    p = n.canon_person_name(raw)
    assert p is not None
    assert p.title == title
    assert p.canonical == canonical


def test_canon_person_name_same_person_different_case_match():
    a = n.canon_person_name("Dr. Öğr. Üyesi NAFİYE ÇİĞDEM AKTEKİN")
    b = n.canon_person_name("Dr. Öğr. Üyesi Nafiye Çiğdem Aktekin")
    assert a and b and a.canonical == b.canonical


def test_split_person_names():
    assert n.split_person_names("Prof. Dr. A B\nDoç. Dr. C D") == ["Prof. Dr. A B", "Doç. Dr. C D"]
    assert n.split_person_names("Dr. A B / Dr. C D") == ["Dr. A B", "Dr. C D"]
    assert n.split_person_names("\xa0") == []
    assert n.canon_person_name("UZEM") is not None  # units are kept, caller decides


# --- faculties / programs ----------------------------------------------------


def test_canon_faculty_aliases():
    assert n.canon_faculty("MDBF").canonical == n.canon_faculty("Mühendislik ve Doğa Bilimleri Fakültesi").canonical
    assert n.canon_faculty("MDBF ; MF").canonical == n.canon_faculty("MDBF").canonical
    assert n.canon_faculty("SHMYO").canonical == n.canon_faculty("Sağlık Hizmetleri Meslek Yüksekokulu").canonical
    assert n.canon_faculty("ECZACILIK FAKÜLTESİ").canonical == n.canon_faculty("Eczacılık Fakültesi").canonical
    assert n.canon_faculty("Rektörlük  Servis").canonical == n.canon_faculty("Rektörlük Servis").canonical
    assert n.canon_faculty("İnsan ve Toplum Bilimleri Fakültesi ").name == "İnsan ve Toplum Bilimleri Fakültesi"
    assert n.canon_faculty("Yabancı Diller").canonical == n.canon_faculty("Yabancı Diller Bölümü").canonical
    assert n.canon_faculty(None) is None


def test_canon_program():
    a = n.canon_program("Moleküler Biyoloji ve \n Genetik")
    assert a and a.name == "Moleküler Biyoloji ve Genetik"
    assert n.canon_program("Sosyoloji ").canonical == n.canon_program("Sosyoloji").canonical
    assert n.canon_program("OPTİSYENLİK").canonical == n.canon_program("Optisyenlik").canonical
    assert n.canon_program("Hemşirelik (İÖ)").is_evening is True
    assert n.canon_program("Hemşirelik").is_evening is False
    assert n.split_program_names("PTL - ENT - DYZ") == ["PTL", "ENT", "DYZ"]
    assert n.split_program_names("AHP+ANS") == ["AHP", "ANS"]
    assert n.split_program_names("Fizyoterapi ve Rehabilitasyon") == ["Fizyoterapi ve Rehabilitasyon"]


# --- venue request -----------------------------------------------------------


def test_parse_venue_request_exact_room():
    v = n.parse_venue_request("A 105")
    assert v.room_codes == ["A105"] and v.confidence == "high" and v.needs_room is True


def test_parse_venue_request_room_with_reason():
    v = n.parse_venue_request("A103 (Bilg. Lab. Zorunlu)")
    assert v.room_codes == ["A103"] and "PC" in v.tags and v.confidence == "high"


def test_parse_venue_request_building_level():
    v = n.parse_venue_request("A Blok'ta Derslik")
    assert v.building == "A" and v.room_codes == [] and v.confidence == "medium"
    assert n.parse_venue_request("derslik (B Blok isteniyor)").building == "B"
    assert n.parse_venue_request("B Blok Derslik").building == "B"


def test_parse_venue_request_capacity_level():
    v = n.parse_venue_request("72 kişilik C blok 601-602 vb")
    assert v.min_capacity == 72 and v.building == "C" and v.room_codes == ["C601", "C602"]
    v = n.parse_venue_request("1 adet sınav kapasitesi minimum 60 kişilik derslik")
    assert v.min_capacity == 60 and v.room_count == 1
    v = n.parse_venue_request("Seminerler ... 100-120  kişilik bir derslik talebimiz var.")
    assert v.min_capacity == 100


def test_parse_venue_request_multi_room_lab():
    v = n.parse_venue_request("A301-A302-A303 MULTİDİSİPLİN")
    assert v.room_codes == ["A301", "A302", "A303"] and "LAB" in v.tags


def test_parse_venue_request_generic():
    v = n.parse_venue_request("Derslik")
    assert v.room_codes == [] and v.needs_room is True and v.confidence == "low"
    assert n.parse_venue_request("1 derslik").room_count == 1
    assert n.parse_venue_request("2 büyük sınıf veya 3 küçük sınıf").room_count == 2
    assert n.parse_venue_request("DERSLİK+HASTANE").needs_room is True
    assert n.parse_venue_request("Amfi").tags == ["AMPHI"]
    assert n.parse_venue_request("SHMYO Servis Dersi-Büyük anfi (A204?)").room_codes == ["A204"]


def test_parse_venue_request_dates_and_junk():
    v = n.parse_venue_request("11.12.2026 tarihinde tam gün")
    assert v.room_codes == [] and v.confidence == "low" and v.notes
    v = n.parse_venue_request("--")
    assert v.confidence == "none" and v.needs_room is None
    assert n.parse_venue_request(None).confidence == "none"


def test_parse_venue_request_no_room():
    for raw in (
        "Yok",
        "Derslik talebi yok",
        "Online",
        "UZEM",
        "Hastane",
        "Asenkron",
        "Yok, Acıbadem Maslak",
        "Laboratuvar",
    ):
        assert n.parse_venue_request(raw).needs_room is False, raw


def test_parse_venue_request_computer_lab_and_invigilators():
    v = n.parse_venue_request("Bilgisayar laboratuvarı")
    assert "PC" in v.tags and v.needs_room is True
    v = n.parse_venue_request("1 Gözetmen Talebi")
    assert v.invigilators == 1
    v = n.parse_venue_request("NUT 470 dersi ile aynı derslikte")
    assert v.same_room_as == ["NUT470"]
    v = n.parse_venue_request("ANS138 ve ANS102  ile aynı derslik")
    assert v.same_room_as == ["ANS138", "ANS102"]
    assert n.parse_venue_request("Toplantı Salonu").tags == ["MEETING"]


# --- exam dates / grid day headers -------------------------------------------


def test_parse_date_range():
    assert n.parse_date_range(datetime(2026, 6, 3)) == (date(2026, 6, 3), None)
    assert n.parse_date_range("11.06.2026 - 12.06.2026") == (date(2026, 6, 11), date(2026, 6, 12))
    assert n.parse_date_range("-") == (None, None)
    assert n.parse_date_range("YOK") == (None, None)
    assert n.parse_date_range(date(2026, 5, 13)) == (date(2026, 5, 13), None)


def test_parse_day_header():
    assert n.parse_day_header("Pazartesi", 2026) == (1, None)
    assert n.parse_day_header("1 Haziran Pazartesi", 2026) == (1, date(2026, 6, 1))
    assert n.parse_day_header("7 Haziran Pazar", 2026) == (7, date(2026, 6, 7))
    assert n.parse_day_header("Salı", 2026) == (2, None)


def test_parse_grid_cell():
    c = n.parse_grid_cell("HEM 334 / NRS 304")
    assert c.kind == "COURSE" and c.codes == ["HEM334", "NRS304"]
    c = n.parse_grid_cell("Hazırlık")
    assert c.kind == "BLOCK" and c.label == "HAZIRLIK"
    assert n.parse_grid_cell("UZEM").label == "UZEM"
    assert n.parse_grid_cell("ETKİNLİK").label == "ETKİNLİK"
    assert n.parse_grid_cell("NAFİYE HOCA").label == "NAFİYE HOCA"
    assert n.parse_grid_cell("EHM 112 B1+").section_label == "B1+"
    assert n.parse_grid_cell("  ") is None


def test_fill_to_tag():
    assert n.fill_to_tag("FFFFFF00") == "YELLOW"
    assert n.fill_to_tag("FFFFC000") == "ORANGE"
    assert n.fill_to_tag("FF7030A0") == "PURPLE"
    assert n.fill_to_tag("FF00B0F0") == "BLUE"
    assert n.fill_to_tag("FF0070C0") == "BLUE"
    assert n.fill_to_tag("FF92D050") == "GREEN"
    assert n.fill_to_tag("FFFFFFFF") is None
    assert n.fill_to_tag("00000000") is None
    assert n.fill_to_tag("theme:0") is None
    assert n.fill_to_tag("theme:5") == "THEME5"


def test_parse_section_label():
    assert n.parse_section_label(1) == "1"
    assert n.parse_section_label("1, 2") == "1,2"
    assert n.parse_section_label(1.2) == "1,2"
    assert n.parse_section_label(" (B1+ INT A)") == "B1+ INT A"
    assert n.parse_section_label("\xa0") is None
    assert n.parse_section_label("-") is None


def test_parse_bool_loose():
    assert n.parse_bool_loose("Evet") is True
    assert n.parse_bool_loose("EVET ") is True
    assert n.parse_bool_loose("Hayır") is False
    assert n.parse_bool_loose("X") is True
    assert n.parse_bool_loose(0) is False
    assert n.parse_bool_loose("70% derslikte") is None
    assert n.parse_bool_loose(None) is None


@pytest.mark.parametrize(
    "raw,name,expected",
    [
        ("MAT 112", None, "MAT112"),
        ("BES 3O6", None, "BES306"),
        ("GT' 251", None, "GT251"),
        ("ING1 11", None, "ING111"),
        ("ACU", "Ülkeler ve Türkiye Coğrafyası", "ACU-"),
        ("MBG XXX", "Seçmeli", "MBG-"),
        ("ACU", None, None),
        (None, "x", None),
    ],
)
def test_canon_course_code_loose(raw, name, expected):
    code, warning = n.canon_course_code_loose(raw, name)
    if expected is None:
        assert code is None
    elif expected.endswith("-"):
        assert code and code.startswith(expected) and len(code) == len(expected) + 4 and warning
    else:
        assert code == expected
        assert (warning is None) == (raw == "MAT 112")


@pytest.mark.parametrize(
    "text,weeks",
    [
        ("son 7 hafta", list(range(8, 15))),  # review MINOR 8: was [7]
        ("Son 4 hafta derslikte", [11, 12, 13, 14]),
        ("2-14 (7. hafta hariç)", [2, 3, 4, 5, 6, *range(8, 15)]),  # was [7]
        ("1-14 hariç 8", [*range(1, 8), *range(9, 15)]),
        ("8. ve 9. hafta hariç tüm haftalar", [*range(1, 8), *range(10, 15)]),
        ("ilk 7 hafta", list(range(1, 8))),
    ],
)
def test_parse_weeks_last_n_and_except(text, weeks):
    assert n.parse_weeks(text, 14).weeks == weeks
