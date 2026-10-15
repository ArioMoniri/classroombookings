"""Locale-independent value parsing, on values taken from the real workbooks and their variants."""

from __future__ import annotations

from datetime import date, time

from app.council import text as tx


def test_days_in_several_languages():
    assert tx.parse_days("Perşembe") == [4]
    assert tx.parse_days("Salı / Çarşamba / Perşembe / Cuma") == [2, 3, 4, 5]
    assert tx.parse_days("Thursday") == [4]
    assert tx.parse_days("Mittwoch") == [3]
    assert tx.parse_days("mercredi") == [3]
    assert tx.parse_days("Cumartesi") == [6] and tx.parse_days("Pazar") == [7]
    assert tx.parse_days("Mon") == [1] and tx.parse_days("Pzt") == [1]
    assert tx.parse_days("Asenkron") == []
    assert tx.parse_days("1 Haziran Pazartesi", allow_abbrev=False) == [1]


def test_clock_and_ranges_from_real_cells():
    assert tx.parse_clock("13:30") == time(13, 30)
    assert tx.parse_clock("09.00") == time(9, 0)
    assert tx.parse_clock("1:30 PM") == time(13, 30)
    assert tx.parse_clock(time(11, 0)) == time(11, 0)
    # grid axis labels exactly as typed in the Bahar board, including the "22-50" typo
    assert tx.parse_time_range("08:30-09:10") == (time(8, 30), time(9, 10))
    assert tx.parse_time_range("20.30-21.10") == (time(20, 30), time(21, 10))
    assert tx.parse_time_range("22.10-22-50") == (time(22, 10), time(22, 50))
    assert tx.parse_time_range("8:30 – 10:20") == (time(8, 30), time(10, 20))


def test_dates():
    assert tx.parse_date("2026-05-13") == date(2026, 5, 13)
    assert tx.parse_date("13.05.2026") == date(2026, 5, 13)
    assert tx.parse_date("13 May 2026") == date(2026, 5, 13)
    assert tx.parse_date("May 13, 2026") == date(2026, 5, 13)
    assert tx.parse_date("1 Haziran Pazartesi", 2026) == date(2026, 6, 1)
    assert tx.parse_date("1 Haziran Pazartesi") is None  # no year, no hint: never guessed


def test_rooms_and_courses():
    assert tx.room_tokens("A 101 / A 106 / A 107") == ["A101", "A106", "A107"]
    assert tx.room_tokens("A 207 - A 206 - A 205") == ["A207", "A206", "A205"]
    assert tx.room_tokens("HS 3, HS 4") == ["HS3", "HS4"]
    assert tx.room_tokens("Room 1.12") == ["ROOM1.12"]
    assert tx.room_tokens("derslik") == []
    assert tx.course_codes("MAT 112") == ["MAT112"]
    assert tx.course_codes("INF-101") == ["INF101"]
    assert tx.person_key("Prof. Dr. ATA AKIN") == "ata akin"


def test_modes_and_language():
    assert tx.parse_mode("Yüz yüze") == "F2F"
    assert tx.parse_mode("Face to face") == "F2F"
    assert tx.parse_mode("Online") == "ONLINE" and tx.parse_mode("UZEM") == "UZEM"
    assert tx.parse_mode("Hibrit") == "HYBRID"
    tr_headers = ["Ders Kodu", "Ders Adı", "Şube", "Dersin Günü", "Dersin Başlangıç Saati", "Derslik Talebi"]
    en_headers = ["Course Code", "Course Title", "Section", "Weekday", "Start Time", "Requested Room"]
    assert tx.detect_language(tr_headers)[0] == "tr"
    assert tx.detect_language(en_headers)[0] == "en"
