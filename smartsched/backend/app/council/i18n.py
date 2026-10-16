"""Turkish for the council's own messages (T-R1-23): step and file messages, review titles, findings, the phase.

The council writes its messages in English (they are also log and audit text). This module is the TR/EN pair
catalogue: an ordered list of ``(English pattern, Turkish template)``; :func:`localize` gives a reader the Turkish
line for every English one it knows (``lang="tr"``) and leaves the rest as it is. A pattern's named groups go into
the template; a group whose name ends in ``_m`` is itself a council message and is localized again.

The API localizes at the boundary (``GET /council/jobs/{id}``, its events and ``/review``, by ``?lang=`` or the
job's language), so the stored text stays English and old jobs read in Turkish too. Numbers keep their digits,
file, sheet and column names stay as written, and percentages read ``%96``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

#: the record types and entity names in counts and messages
ENTITY_TR = {
    "meeting": "ders",
    "meetings": "ders",
    "exam": "sınav",
    "exams": "sınav",
    "room": "derslik",
    "rooms": "derslik",
    "booking": "rezervasyon",
    "bookings": "rezervasyon",
    "course": "ders",
    "courses": "ders",
    "staff": "personel",
    "instructor": "öğretim elemanı",
    "instructors": "öğretim elemanı",
    "calendar": "takvim",
    "constraint": "kural",
    "record": "kayıt",
    "records": "kayıt",
    "entity": "kayıt",
}
KIND_TR = {
    "request_list": "talep listesi",
    "room_list": "derslik listesi",
    "timetable_grid": "haftalık program tablosu",
    "exam_list": "sınav listesi",
    "staff_list": "personel listesi",
    "calendar": "akademik takvim",
    "other": "diğer",
}
SHAPE_TR = {
    "planning-list": "planlama listesi",
    "weekly-grid": "haftalık program tablosu",
    "room-master": "derslik listesi",
    "exam-list": "sınav listesi",
    "crbs-legacy": "eski rezervasyon dışa aktarımı",
}
SEVERITY_TR = {"error": "hata", "warning": "uyarı", "info": "bilgi"}


def _ent(word: str) -> str:
    return ENTITY_TR.get(word.strip().lower(), word)


Rule = tuple[re.Pattern[str], str | Callable[[re.Match[str]], str]]
_RULES: list[Rule] = []


def _r(pattern: str, tr: str | Callable[[re.Match[str]], str]) -> None:
    _RULES.append((re.compile(pattern, re.S), tr))


# --- intake / render ---------------------------------------------------------------------------------------
_r(
    r"AI is off: this file was not read \(no table the server can read\)",
    "YZ kapalı, okunmadı (sunucunun okuyabileceği tablo yok)",
)
_r(
    r"needs the AI model to read \(image/scan\)",
    "Okunmadı: bu dosyada okunabilir metin yok (taranmış belge ya da görsel olabilir); okumak için yapay zekâ "
    "modeli gerekir",
)
_r(
    r"the PDF has no text layer \(scanned\?\); it can only be read by the AI model",
    "Bu PDF'de okunabilir metin yok (taranmış belge olabilir); yalnız yapay zekâ modeli okuyabilir",
)
_r(
    r"read as (?P<enc>[\w-]+), (?P<d>\w+)-separated \((?P<how>.*)\)",
    lambda m: (
        f"{m['enc'] == 'text' and 'Metin' or 'CSV'} · {ENCODING_NAME.get(m['enc'], m['enc'])} · "
        f"{DELIMITER_CHAR.get(m['d'], m['d'])}"
    ),
)
_r(r"(?P<n>\d+) ruled table\(s\) read with pdfplumber", "PDF'deki {n} çizgili tablo okundu")
_r(r"ruled-table reader skipped: (?P<e>\w+)", "çizgili tablo okunamadı ({e})")
_r(r"only the first (?P<n>\d+) rows were read", "yalnız ilk {n} satır okundu")
_r(r"sheet '(?P<s>.*)': only the first (?P<n>\d+) rows were read", "'{s}' sayfası: yalnız ilk {n} satır okundu")
_r(r"sheet '(?P<s>.*)': columns after (?P<n>\d+) were not read", "'{s}' sayfası: {n}. sütundan sonrası okunmadı")
_r(
    r"(?P<n>\d+) attachment\(s\) are read as files of this job: (?P<f>.*)",
    "{n} ek bu işin dosyaları olarak okunuyor: {f}",
)
_r(r"only the first (?P<n>\d+) of (?P<t>\d+) attachments were read", "{t} ekin yalnız ilk {n} tanesi okundu")
_r(
    r"only the Subject and Date headers were kept \(sender and recipients are not read\)",
    "Yalnız Konu ve Tarih başlıkları alındı (gönderen ve alıcılar okunmadı)",
)
_r(r"could not be read", "okunamadı")
_r(
    r"this file has no machine-readable text \(image or scan\); reading it needs the AI model \((?P<why_m>.*)\)",
    "Bu dosyada okunabilir metin yok (görsel ya da taranmış belge olabilir); okumak için yapay zekâ modeli gerekir ({why_m})",
)
_r(r"AI vision is off \(Settings > AI\)", "görsel okuma kapalı (Ayarlar › Yapay zekâ)")
_r(
    r"AI disabled for the council \(COUNCIL_AI=false or ai=false\); deterministic path only",
    "Bu iş için yapay zekâ kapalı; yalnız kural tabanlı okuma",
)
_r(
    r"AI is off for the council \(an administrator has not allowed sending file content to Claude under Settings > AI\);"
    r" deterministic path only",
    "Yapay zekâ kapalı (yönetici, dosya içeriğinin gönderilmesine Ayarlar › Yapay zekâ altında izin vermedi); yalnız "
    "kural tabanlı okuma",
)
_r(
    r"no Anthropic API key configured: deterministic path only \(heuristic mapping \+ importers\)",
    "Yapay zekâ anahtarı tanımlı değil; yalnız kural tabanlı okuma",
)
_r(
    r"sheet '(?P<s>.*)' is hidden in the workbook; it was read anyway",
    "'{s}' sayfası çalışma kitabında gizli; yine de okundu",
)
_r(
    r"known shape '(?P<shape>[\w-]+)': the existing importer reads this file \(deterministic fast path\)",
    lambda m: (
        f"Bilinen biçim ({SHAPE_TR.get(m['shape'], m['shape'])}): dosyayı mevcut aktarıcı okur (kural tabanlı hızlı yol)"
    ),
)
_r(
    r"read by the (?P<shape>[\w-]+) importer's parser: (?P<n>\d+) records",
    lambda m: f"{SHAPE_TR.get(m['shape'], m['shape'])} aktarıcısı okudu: {m['n']} kayıt",
)
_r(r"(?P<n>\d+) records", "{n} kayıt")
_r(
    r"free text without tables; record extraction from prose needs the AI model \((?P<why_m>.*)\)",
    "Tablosuz serbest metin; metinden kayıt çıkarmak için yapay zekâ modeli gerekir ({why_m})",
)
_r(r"(?P<agent>\w+) timed out after (?P<s>\d+)s", "{agent} adımı {s} sn içinde bitmedi")
_r(r"vision transcription failed: (?P<e>.*)", "görsel okuma başarısız: {e}")
_r(r"free-text extraction failed: (?P<e>.*)", "serbest metinden çıkarma başarısız: {e}")
_r(
    r"token budget exhausted \((?P<a>\d+) >= (?P<b>\d+)\); heuristic result kept",
    "token bütçesi doldu ({a} ≥ {b}); kural tabanlı sonuç kaldı",
)
# --- cross-file steps --------------------------------------------------------------------------------------
_r(
    r"(?P<r>\d+) rooms, (?P<c>\d+) courses, (?P<d>\d+) duplicate records, (?P<m>\d+) merge suggestions",
    "{r} derslik, {c} ders, {d} yinelenen kayıt, {m} birleştirme önerisi",
)
_r(
    r"(?P<n>\d+) term group\(s\); period grid: (?P<src>.*)",
    lambda m: f"{m['n']} dönem grubu; ders saati çizelgesi: {GRID_TR.get(m['src'], m['src'])}",
)
_r(r"(?P<n>\d+) finding\(s\)", "{n} bulgu")
_r(r"model judge skipped: (?P<why_m>.*)", "model denetimi atlandı: {why_m}")
_r(r"judge failed: (?P<e>.*)", "model denetimi başarısız: {e}")
_r(
    r"(?P<n>\d+) rule-like text\(s\) found; turning them into constraints needs the AI model.*",
    "{n} kural benzeri metin bulundu; bunları kurala çevirmek için yapay zekâ modeli gerekir",
)
_r(
    r"rule miner model call failed \((?P<e>.*)\); texts kept for review",
    "kural madencisi çağrısı başarısız ({e}); metinler incelemeye kaldı",
)
_r(r"only the first (?P<n>\d+) parts of the rule text were analysed", "kural metninin yalnız ilk {n} parçası incelendi")
# --- the job's phase ---------------------------------------------------------------------------------------
_r(r"file (?P<i>\d+)/(?P<n>\d+): (?P<f>.*)", "dosya {i}/{n}: {f}")
_r(r"cross-file: reconcile, plan, rules, critic", "tüm dosyalar: eşleştirme, dönem planı, kurallar, denetim")
_r(r"re-reading (?P<n>\d+) file\(s\) with the reviewed mapping", "{n} dosya, onaylanan eşlemeyle yeniden okunuyor")
# --- critic findings ---------------------------------------------------------------------------------------
_r(r"(?P<n>\d+) request\(s\) end before they start", "{n} talebin bitişi başlangıcından önce")
_r(
    r"room (?P<code>.+?) is assigned (?P<n>\d+) time\(s\) but no room list or timetable header defines it",
    "{code} dersliği {n} kez atanmış, ama hiçbir derslik listesinde ya da program başlığında yok",
)
_r(
    r"(?P<n>\d+) request\(s\) have more students than seats in their assigned room\(s\); e\.g\. (?P<ex>.*)",
    lambda m: (
        f"{m['n']} talebin öğrenci sayısı atanan dersliklerin kapasitesini aşıyor; örnek: "
        + re.sub(r"(\d+) students, (\d+) seats in", r"\1 öğrenci, \2 koltuk:", m["ex"])
    ),
)
_r(
    r"solver pre-check \((?P<code>[\w:]+)\): (?P<n>\d+) finding\(s\); e\.g\. .*",
    lambda m: f"Çözücü ön denetimi ({PRECHECK_TR.get(m['code'], m['code'])}): {m['n']} bulgu",
)
_r(r"solver static check could not run \((?P<e>\w+)\)", "çözücü ön denetimi çalışamadı ({e})")
# --- review titles -----------------------------------------------------------------------------------------
_r(
    r"(?P<f>.+?): (?P<p>\d+) of (?P<t>\d+) rows read by the AI model wait for a person \(accept, edit or reject each row\)",
    "{f}: yapay zekânın okuduğu {t} satırdan {p} tanesi bir kişinin kararını bekliyor (her satırı onaylayın, "
    "düzeltin ya da reddedin)",
)
_r(r"Same (?P<k>\w+)\? '(?P<a>.*)' and '(?P<b>.*)'", lambda m: f"Aynı {_ent(m['k'])} mı? '{m['a']}' ve '{m['b']}'")
_r(r"Same (?P<k>\w+)\?", lambda m: f"Aynı {_ent(m['k'])} mı?")
_r(
    r"(?P<w>.+?): is this a (?P<k>.+)\?",
    lambda m: f"{m['w']}: bu bir {KIND_LABEL_TR.get(m['k'], m['k'])} mı?",
)
_r(
    r"(?P<w>.+): column '(?P<h>.*)' -> (?P<f>[\w()]+(?: used\))?)\? \(remembered: (?P<r>.+)\)",
    lambda m: f"{m['w']}: '{m['h']}' sütunu → {_field(m['f'])}? (hatırlanan: {_field(m['r'])})",
)
_r(r"(?P<w>.+): column '(?P<h>.*)' -> (?P<f>.+)\?", lambda m: f"{m['w']}: '{m['h']}' sütunu → {_field(m['f'])}?")
_r(r"column (?P<c>\d+) -> (?P<f>.+)\?", lambda m: f"{m['c']}. sütun → {_field(m['f'])}?")
_r(
    r"(?P<f>.+?): (?P<n>\d+) rule-like text\(s\) need the AI model to become constraints",
    "{f}: {n} kural benzeri metin, kurala dönüşmek için yapay zekâ modeli bekliyor",
)
_r(
    r"Term (?P<code>\S+) \((?P<k>\w+), (?P<w>\d+) weeks\) from (?P<f>.*)",
    lambda m: f"Dönem {m['code']} ({TERM_KIND_TR.get(m['k'], m['k'])}, {m['w']} hafta): {m['f']}",
)
_r(r"Finding", "Bulgu")
_r(r"Rule proposal", "Kural önerisi")
_r(r"Rule-like texts", "Kural benzeri metinler")
_r(r"File", "Dosya")
_r(r"(?P<f>.+?): (?P<msg_m>.+)", "{f}: {msg_m}")  # "<file>: <message>" (file items): only when the message is known

#: how the encodings and delimiters of a delimited text file are named on the file row (T-R1-26)
ENCODING_NAME = {
    "cp1254": "Windows-1254",
    "utf-8": "UTF-8",
    "utf-8-sig": "UTF-8 (BOM)",
    "utf-16": "UTF-16",
    "latin-1": "ISO-8859-1",
    "text": "metin",
}
DELIMITER_CHAR = {"semicolon": ";", "comma": ",", "tab": "sekme", "pipe": "|"}
GRID_TR = {
    "timetable-grid": "program tablosundan",
    "timetable-grid (= default 18-period grid)": "program tablosundan (varsayılan 18 ders saati)",
    "default-18": "varsayılan 18 ders saati",
    "inferred": "derslerin saatlerinden çıkarıldı",
}
PRECHECK_TR = {
    "fixed_conflict": "sabit dersler çakışıyor",
    "trusted_lock_capacity": "kilitli dersin dersliği küçük",
    "locked_overlap": "kilitli dersler çakışıyor",
    "pigeonhole": "yeterli derslik ya da saat yok",
    "no_room": "uygun derslik yok",
}
TERM_KIND_TR = {"REGULAR": "normal dönem", "SUMMER": "yaz okulu", "FINAL": "final", "BUT": "bütünleme"}
#: app/council/structure.py KIND_LABELS in Turkish
KIND_LABEL_TR = {
    "room list": "derslik listesi",
    "course / request list": "ders / talep listesi",
    "exam list": "sınav listesi",
    "existing timetable grid": "mevcut program tablosu",
    "calendar / holidays": "takvim / tatiller",
    "staff list": "personel listesi",
    "preferences / rules": "tercih / kural listesi",
    "other": "başka bir tablo",
}


def _field(f: str) -> str:
    return "kullanılmıyor" if f in ("(not used)", "not used") else f


def _one(line: str, depth: int = 0) -> str | None:
    for rx, tr in _RULES:
        m = rx.fullmatch(line)
        if m is None:
            continue
        if callable(tr):
            return tr(m)
        groups: dict[str, Any] = {}
        known = True
        for k, v in m.groupdict().items():
            if k.endswith("_m") and v is not None:
                inner = _one(v, depth + 1) if depth < 3 else None
                if inner is None:
                    known = False
                    break
                groups[k] = inner
            else:
                groups[k] = v if v is not None else ""
        if not known:
            continue
        return tr.format(**groups)
    return None


def localize(text: str | None, lang: str | None) -> str | None:
    """``text`` (lines of council messages) for a reader of ``lang``: Turkish where the catalogue knows the line."""
    if not text or (lang or "").lower()[:2] != "tr":
        return text
    return "\n".join(_one(line) or line for line in text.split("\n"))


def localize_item(item: dict[str, Any], lang: str | None) -> dict[str, Any]:
    """A review item with its title (and an issue's severity) for ``lang``; the English stays in ``title_en``."""
    if (lang or "").lower()[:2] != "tr":
        return item
    out = {**item, "title_en": item.get("title"), "title": localize(item.get("title"), lang)}
    if isinstance(item.get("severity"), str):
        out["severity_label"] = SEVERITY_TR.get(item["severity"], item["severity"])
    return out


__all__ = ["ENTITY_TR", "SEVERITY_TR", "localize", "localize_item"]
