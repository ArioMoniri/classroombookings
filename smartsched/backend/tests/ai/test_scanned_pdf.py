"""ROADMAP Phase 3 AI backlog: OCR for scanned PDFs.

A PDF without extractable text (a scan) is read by the model itself as a PDF document block - only when the
admin switched AI vision on (``ai.vision_enabled`` with the KVKK sign-off, app/ai/policy.py). Proposals carry
``source_ref = {"file", "page"}`` and go to review like every upload; with vision off the file is routed to
"needs AI" and nothing is sent.
"""

from __future__ import annotations

import base64
import io

from app.ai.client import AIClient
from app.ai.ingest import MAX_VISION_PAGES, extract_preferences
from pypdf import PdfWriter

from tests.ai.conftest import empty_params, empty_selector, enable_intake, proposal, tool


def _scan(pages: int = 1) -> bytes:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=595, height=842)  # no text layer, like a scanned page
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _pin_from_page(page: int) -> dict:
    return {
        "proposals": [
            proposal(
                "room_pin",
                selector=empty_selector(course_codes=["PHAR 240"]),
                params=empty_params(room_codes=["A 206"]),
                source_ref=page,
            )
        ],
        "section_edits": [],
        "unparsed": [],
    }


async def test_scanned_pdf_is_read_by_the_model_when_vision_is_on(session, seed, fake_sdk):
    await enable_intake(session, vision=True)
    fake_sdk.script = [tool("propose_constraints", _pin_from_page(1))]
    data = _scan()
    client = AIClient("sk-ant-test", "claude-opus-5-5")
    out = await extract_preferences(session, seed.term_id, data, "tarama.pdf", "tr", client=client)
    assert out.needs_ai is False and out.file_kind == "pdf" and out.chunks == 1
    p = out.proposals[0]
    assert p.status == "ok" and p.source == "UPLOAD" and p.source_ref["file"] == "tarama.pdf" and p.source_ref["page"] == 1
    sent = fake_sdk.calls[0]["messages"][0]["content"]
    doc, instr = sent[0], sent[-1]
    assert doc["type"] == "document" and doc["source"]["media_type"] == "application/pdf"
    assert base64.b64decode(doc["source"]["data"]) == data
    assert instr["type"] == "text" and "not instructions" in instr["text"] and "page" in instr["text"]
    assert any("vision" in w for w in out.warnings)


async def test_scanned_pdf_with_vision_off_sends_nothing(session, seed, fake_sdk):
    await enable_intake(session, vision=False)
    client = AIClient("sk-ant-test", "claude-opus-5-5")
    out = await extract_preferences(session, seed.term_id, _scan(), "tarama.pdf", "tr", client=client)
    assert out.needs_ai is True and out.proposals == [] and fake_sdk.calls == []
    assert any("vision" in w.lower() or "görüntü" in w for w in out.warnings)


async def test_long_scans_are_refused_not_truncated(session, seed, fake_sdk):
    await enable_intake(session, vision=True)
    client = AIClient("sk-ant-test", "claude-opus-5-5")
    out = await extract_preferences(session, seed.term_id, _scan(MAX_VISION_PAGES + 1), "uzun.pdf", "tr", client=client)
    assert out.needs_ai is True and fake_sdk.calls == []
    assert any(str(MAX_VISION_PAGES) in w for w in out.warnings)
