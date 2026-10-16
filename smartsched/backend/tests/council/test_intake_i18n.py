"""The intake in Turkish (T-R1-23): the F-08 job (the Bahar list, its English CSV export, a scanned PDF and the
rules memo DOCX) with AI off, read back with ``?lang=tr``: every council message a reader meets (file and step
messages, the phase, the AI note, review titles and findings) is Turkish, and no "(s)" plural is left.

Content stays as written (file, sheet and column names, the quoted values), so the scan drops quoted text and the
file names before it looks for English words."""

from __future__ import annotations

import io
import re

from app.council import i18n

from tests.api_fixtures import login
from tests.council.conftest import BAHAR_LIST, EN_CSV, MEMO_DOCX, SCAN_PNG
from tests.council.test_formats_api import upload

#: words that only an English council message has (F-13's EN_WORDS plus the council's own vocabulary)
EN = re.compile(
    r"\b(Close|Loading|Save|Cancel|Search|Submit|Next|Previous|Error|Delete|Edit|Back|Open|Retry|the|is|of|and|are|"
    r"needs?|file|files|records?|rows?|read|found|requests?|rooms?|time|sheet|hidden|same|term|weeks?|column|"
    r"not|used|finding|rule|texts?|courses?|duplicate|merge|suggestions|group|period|grid|skipped|known|shape|"
    r"existing|importer|deterministic|path|only|wait|person|accept|reject|students|seats|assigned|defines|before|"
    r"they|end|start|from|with|this|could|AI|Same|Term|Finding|File|Rule)\b"
)
PLURAL = re.compile(r"[a-z]+\(s\)")


def scanned_pdf() -> bytes:
    """The real exam sheet scan (PNG) saved as a one-page PDF: no text layer, as a scanner makes it."""
    from PIL import Image

    buf = io.BytesIO()
    Image.open(SCAN_PNG).convert("RGB").save(buf, format="PDF")
    return buf.getvalue()


def english(text: str, names: list[str]) -> list[str]:
    for n in names:
        text = text.replace(n, "")
    text = re.sub(r"'[^']*'|\"[^\"]*\"", "", text)
    return EN.findall(text) + PLURAL.findall(text)


async def test_f08_job_reads_in_turkish(client):
    h = await login(client)
    files = [
        (BAHAR_LIST.name, BAHAR_LIST.read_bytes()),
        (EN_CSV.name, EN_CSV.read_bytes()),
        ("taranmis_sinav_programi.pdf", scanned_pdf()),
        (MEMO_DOCX.name, MEMO_DOCX.read_bytes()),
    ]
    job = await upload(client, h, *files, ai="false")
    names = [f[0] for f in files]
    job = (await client.get(f"/api/v1/council/jobs/{job['id']}", headers=h, params={"lang": "tr"})).json()
    review = (await client.get(f"/api/v1/council/jobs/{job['id']}/review", headers=h, params={"lang": "tr"})).json()
    lines: list[str] = [job["summary"].get("ai") or ""]
    for f in job["files"]:
        lines += [f.get("message") or ""] + [s.get("message") or "" for s in f["steps"]]
    lines += [s.get("message") or "" for s in job["cross_steps"]]
    lines += [it["title"] for it in review["items"]]
    found = {line: english(line, names) for line in "\n".join(lines).split("\n") if line}
    bad = {k: v for k, v in found.items() if v}
    assert bad == {}
    pdf = job["files"][2]
    assert pdf["message"].startswith("Okunmadı: bu dosyada okunabilir metin yok")
    csv_step = next(st for st in job["files"][1]["steps"] if st["agent"] == "intake")
    assert "CSV · UTF-8 · ," in csv_step["message"]  # the encoding and the delimiter (T-R1-26)
    # the English stays the stored text (and the default for an English reader)
    en = (await client.get(f"/api/v1/council/jobs/{job['id']}", headers=h, params={"lang": "en"})).json()
    assert en["files"][2]["message"] == "needs the AI model to read (image/scan)"
    assert {it["title_en"] for it in review["items"]} == {
        it["title"]
        for it in (
            await client.get(f"/api/v1/council/jobs/{job['id']}/review", headers=h, params={"lang": "en"})
        ).json()["items"]
    }


def test_catalogue_examples():
    tr = lambda s: i18n.localize(s, "tr")  # noqa: E731
    assert tr("1 request(s) end before they start") == "1 talebin bitişi başlangıcından önce"
    assert tr("room A702 is assigned 10 time(s) but no room list or timetable header defines it").startswith(
        "A702 dersliği 10 kez"
    )
    assert tr("Same instructor? 'X' and 'Y'") == "Aynı öğretim elemanı mı? 'X' ve 'Y'"
    assert tr("sheet 'Sayfa2' is hidden in the workbook; it was read anyway") == (
        "'Sayfa2' sayfası çalışma kitabında gizli; yine de okundu"
    )
    assert tr("unknown line stays") == "unknown line stays"
    assert i18n.localize("1 request(s) end before they start", "en") == "1 request(s) end before they start"
