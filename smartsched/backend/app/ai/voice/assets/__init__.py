"""The admin's speech test clip (VO-04): 5.16 s of Turkish speech, Ogg Opus 24 kbps mono (14 KB).

Source and licence: ``SOURCES.md`` next to this file (MediaSpeech, CC BY 4.0). The clip is sent only by the
admin's test call (``POST /ai/admin/providers/{p}/test``) to the provider being tested.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

CLIP = Path(__file__).with_name("tr-test.ogg")
CLIP_MIME = "audio/ogg"
#: what the clip says (MediaSpeech's own transcript of the first 5.16 s of the source file)
CLIP_TEXT = "şu cümle çok önemli çok bir cümlecik bir şey ama çok şeyi anlatıyor"


@cache
def test_clip() -> bytes:
    return CLIP.read_bytes()


__all__ = ["CLIP", "CLIP_MIME", "CLIP_TEXT", "test_clip"]
