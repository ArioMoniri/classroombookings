"""``app/ai/personal.py``: the KVKK ``ai_personal`` withdrawal redactor at the AI client boundary (backend asks batch 3
item 5). Pure tests; the end-to-end case on the real Bahar import is ``tests/test_wave2_kvkk_batch3.py``."""

from __future__ import annotations

import copy

from app.ai.client import AIClient
from app.ai.personal import Redactor

from tests.ai.conftest import tool


def _r() -> Redactor:
    return Redactor(
        [
            ("Prof. Dr. İsmail Işık", ["Prof. Dr. İsmail Işık", "ismail ışık", "ismail.isik@uni.edu.tr"]),
            ("Ayşe Yılmaz", ["Ayşe Yılmaz", "Ali", "ayse_yilmaz"]),
        ]
    )


def test_turkish_case_ascii_folding_and_separators():
    r = _r()
    for text in (
        "İSMAİL IŞIK pazartesi yok",
        "ismail ışık pazartesi yok",
        "Ismail Isik pazartesi yok",
        "ismail işık pazartesi yok",  # NBSP; ş/ı typed as s/i or the other way round
        "i̇smail ışık pazartesi yok",  # Python's lower() of İ (i + combining dot)
    ):
        assert r.text(text) == "[KİŞİ_1] pazartesi yok", text
    assert r.text("Prof. Dr. İsmail Işık") == "[KİŞİ_1]"  # the longest variant wins: no stray title
    assert r.text("yazın: ismail.isik@uni.edu.tr") == "yazın: [KİŞİ_1]"
    assert r.text("AYŞE YILMAZ ve ayse.yilmaz ve ayse_yilmaz") == "[KİŞİ_2] ve [KİŞİ_2] ve [KİŞİ_2]"
    # one word is not a person, and a longer word that contains the name is a different word
    assert r.text("Ali Bey ile Alican") == "Ali Bey ile Alican"
    assert r.text("Ayşe Yılmazoğlu") == "Ayşe Yılmazoğlu"
    assert r.text("Ceyhun Işık") == "Ceyhun Işık"


def test_payload_copies_and_skips_ids_tool_names_binary_and_thinking():
    r = _r()
    messages = [
        {"role": "user", "content": "Ayşe Yılmaz pazartesi yok"},
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "Ayşe Yılmaz", "signature": "sig"},
                {"type": "tool_use", "id": "toolu_1", "name": "Ayşe Yılmaz", "input": {"name": "Ayşe Yılmaz"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_1", "content": "İsmail Işık A 204'te"},
                {
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": "Ayşe Yılmaz"},
                },
            ],
        },
    ]
    before = copy.deepcopy(messages)
    out = r.payload(messages)
    assert messages == before  # the caller's history is untouched
    assert out[0]["content"] == "[KİŞİ_2] pazartesi yok"
    assert out[1]["content"][0] == before[1]["content"][0]  # signed thinking is never altered
    assert out[1]["content"][1]["name"] == "Ayşe Yılmaz" and out[1]["content"][1]["input"] == {"name": "[KİŞİ_2]"}
    assert out[2]["content"][0]["content"] == "[KİŞİ_1] A 204'te"
    assert out[2]["content"][1]["source"]["data"] == "Ayşe Yılmaz"  # binary payloads cannot be redacted
    assert Redactor().payload(messages) is messages and not Redactor()


def test_answer_tokens_come_back_as_names():
    r = _r()
    msg = tool(
        "propose_constraints", {"proposals": [{"selector": {"instructor_name": "[KİŞİ_1]"}, "nl_text": "[KISI_2] yok"}]}
    )
    r.restore_message(msg)
    inp = msg.content[-1].input
    assert inp["proposals"][0]["selector"]["instructor_name"] == "Prof. Dr. İsmail Işık"
    assert inp["proposals"][0]["nl_text"] == "Ayşe Yılmaz yok"
    assert r.restore_text("[KİŞİ_9] bilinmiyor") == "[KİŞİ_9] bilinmiyor"  # an unknown token stays as it is


async def test_client_redacts_requests_and_restores_answers(fake_sdk):
    client = AIClient("sk-ant-" + "test-0000", "claude-opus-5-5")
    client.redactor = _r()
    fake_sdk.script = [tool("noop", {"who": "[KİŞİ_2]"})]
    msg = await client.complete(
        system=[{"type": "text", "text": "Ayşe Yılmaz'ın dersleri", "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": "ayşe yılmaz salı"}],
    )
    call = fake_sdk.calls[-1]
    assert call["system"][0]["text"] == "[KİŞİ_2]'ın dersleri" and call["messages"][0]["content"] == "[KİŞİ_2] salı"
    assert "yılmaz" not in str(call).lower() and "yilmaz" not in str(call).lower()
    assert msg.content[-1].input == {"who": "Ayşe Yılmaz"}
