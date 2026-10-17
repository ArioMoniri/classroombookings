"""Clip checks before any provider call (VO-03): the declared type against an allowlist, the magic bytes against
the declared type, and the length from the container header.

* Accepted: WebM (``audio/webm``; Chromium / Firefox MediaRecorder, Opus), Ogg (``audio/ogg``), MP4 / M4A
  (``audio/mp4``; Safari), MP3 (``audio/mpeg``) and WAV (``audio/wav``). Codec parameters
  (``audio/webm;codecs=opus``) are ignored; aliases are folded.
* Length: WAV from ``fmt`` + ``data``; Ogg from the last page's granule position (Opus at 48 kHz minus the
  pre-skip, Vorbis at its sample rate); WebM from ``Info/Duration`` or, when a live recording has none, from the
  last block's timecode; MP4 from ``moov/mvhd``. MP3 and anything unreadable give ``None``: the provider's own
  reported length is then the check (and the meter) after the call.

Everything works on the bytes in memory; nothing is written anywhere.
"""

from __future__ import annotations

import struct

#: canonical type -> accepted aliases
TYPES: dict[str, tuple[str, ...]] = {
    "audio/webm": ("audio/webm", "video/webm"),
    "audio/ogg": ("audio/ogg", "application/ogg", "audio/opus"),
    "audio/mp4": ("audio/mp4", "audio/m4a", "audio/x-m4a", "audio/aac", "video/mp4"),
    "audio/mpeg": ("audio/mpeg", "audio/mp3", "audio/mpeg3"),
    "audio/wav": ("audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"),
}
_ALIASES = {alias: canon for canon, aliases in TYPES.items() for alias in aliases}


def canonical_type(content_type: str | None) -> str | None:
    """``audio/webm;codecs=opus`` -> ``audio/webm``; ``None`` when the type is not accepted."""
    base = (content_type or "").split(";", 1)[0].strip().lower()
    return _ALIASES.get(base)


def sniff(data: bytes) -> str | None:
    """The canonical type the bytes are, from their magic numbers."""
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "audio/webm"
    if data[:4] == b"OggS":
        return "audio/ogg"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
    if data[4:8] == b"ftyp":
        return "audio/mp4"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "audio/mpeg"
    return None


def duration_s(data: bytes, kind: str) -> float | None:
    try:
        if kind == "audio/wav":
            return _wav(data)
        if kind == "audio/ogg":
            return _ogg(data)
        if kind == "audio/webm":
            return _webm(data)
        if kind == "audio/mp4":
            return _mp4(data)
    except (struct.error, IndexError, ValueError, ZeroDivisionError):
        return None
    return None


# ---------------------------------------------------------------------------------------------- WAV


def _wav(data: bytes) -> float | None:
    pos, byte_rate = 12, 0
    while pos + 8 <= len(data):
        cid, size = data[pos : pos + 4], struct.unpack_from("<I", data, pos + 4)[0]
        if cid == b"fmt ":
            byte_rate = struct.unpack_from("<I", data, pos + 16)[0]
        elif cid == b"data":
            size = min(size, len(data) - pos - 8)
            return size / byte_rate if byte_rate else None
        pos += 8 + size + (size & 1)
    return None


# ---------------------------------------------------------------------------------------------- Ogg


def _ogg(data: bytes) -> float | None:
    if not data.startswith(b"OggS"):
        return None
    header = data[27 + data[26] :]  # the first page's payload follows its segment table
    if header.startswith(b"OpusHead"):
        rate, pre_skip = 48000.0, struct.unpack_from("<H", header, 10)[0]
    elif header.startswith(b"\x01vorbis"):
        rate, pre_skip = float(struct.unpack_from("<I", header, 12)[0]), 0
    else:
        return None
    last = data.rfind(b"OggS")
    granule = struct.unpack_from("<q", data, last + 6)[0]
    if granule < 0 or not rate:
        return None
    return max(granule - pre_skip, 0) / rate


# ---------------------------------------------------------------------------------------------- WebM (EBML)

_SEGMENT, _INFO, _CLUSTER, _GROUP = 0x18538067, 0x1549A966, 0x1F43B675, 0xA0
_TIMECODE_SCALE, _DURATION, _CLUSTER_TC, _SIMPLE, _BLOCK = 0x2AD7B1, 0x4489, 0xE7, 0xA3, 0xA1
_MASTERS = {_SEGMENT, _INFO, _CLUSTER, _GROUP}


def _vint(data: bytes, pos: int, *, keep_marker: bool) -> tuple[int, int, bool]:
    """(value, length, unknown-size) of an EBML variable-length integer at ``pos``."""
    first = data[pos]
    length = 1
    mask = 0x80
    while length <= 8 and not first & mask:
        mask >>= 1
        length += 1
    if length > 8:
        raise ValueError("bad EBML vint")
    value = first if keep_marker else first & (mask - 1)
    for b in data[pos + 1 : pos + length]:
        value = (value << 8) | b
    unknown = not keep_marker and value == (1 << (7 * length)) - 1
    return value, length, unknown


def _webm(data: bytes) -> float | None:
    scale, duration, cluster_tc, last_tc = 1_000_000, None, 0, None
    pos, n = 0, len(data)
    while pos < n:
        try:
            eid, ilen, _ = _vint(data, pos, keep_marker=True)
            size, slen, unknown = _vint(data, pos + ilen, keep_marker=False)
        except (ValueError, IndexError):
            break  # trailing bytes that are not an element: keep what was read
        body = pos + ilen + slen
        if eid in _MASTERS:
            pos = body  # step into a master element (sizes may be unknown in a live recording)
            continue
        if body + size > n:
            break
        payload = data[body : body + size]
        if eid == _TIMECODE_SCALE:
            scale = int.from_bytes(payload, "big") or scale
        elif eid == _DURATION:
            duration = struct.unpack(">f" if size == 4 else ">d", payload)[0]
        elif eid == _CLUSTER_TC:
            cluster_tc = int.from_bytes(payload, "big")
        elif eid in (_SIMPLE, _BLOCK) and size >= 4:
            _, tlen, _ = _vint(payload, 0, keep_marker=False)
            rel = struct.unpack_from(">h", payload, tlen)[0]
            last_tc = max(last_tc or 0, cluster_tc + rel)
        if unknown:
            break
        pos = body + size
    ticks = duration if duration else last_tc
    return ticks * scale / 1e9 if ticks else None


# ---------------------------------------------------------------------------------------------- MP4


def _mp4(data: bytes) -> float | None:
    def boxes(start: int, end: int):  # type: ignore[no-untyped-def]
        pos = start
        while pos + 8 <= end:
            size = struct.unpack_from(">I", data, pos)[0]
            kind = data[pos + 4 : pos + 8]
            head = 8
            if size == 1:
                size, head = struct.unpack_from(">Q", data, pos + 8)[0], 16
            elif size == 0:
                size = end - pos
            if size < head:
                return
            yield kind, pos + head, min(pos + size, end)
            pos += size

    for kind, start, end in boxes(0, len(data)):
        if kind != b"moov":
            continue
        for sub, s2, _e2 in boxes(start, end):
            if sub != b"mvhd":
                continue
            version = data[s2]
            if version == 1:
                scale, dur = struct.unpack_from(">IQ", data, s2 + 20)
            else:
                scale, dur = struct.unpack_from(">II", data, s2 + 12)
            return dur / scale if scale and dur else None
    return None


__all__ = ["TYPES", "canonical_type", "duration_s", "sniff"]
