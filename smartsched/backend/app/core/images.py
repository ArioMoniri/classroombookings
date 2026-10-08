"""Uploaded images (org logo, room photos).

* :func:`check_image` (review MINOR 14): the bytes must be the image type the name claims (magic bytes).
* :func:`sanitize_image` (CRBS parity audit B2): decode with Pillow, keep only JPEG / PNG / GIF (CRBS
  ``settings/Organisation`` and ``setup/rooms/Rooms`` accept ``jpg|jpeg|png|gif``), re-encode, at most
  ``MAX_SIDE`` px on the longer side (CRBS refuses logos wider than 1600 px; here they are scaled down).
  Re-encoding drops whatever rode along in the file (SVG/HTML payloads, polyglots, EXIF/GPS metadata).
* :class:`SafeStaticFiles`: every response under ``/uploads`` carries ``X-Content-Type-Options: nosniff``
  and ``Content-Security-Policy: default-src 'none'``, so even a file stored before these checks existed
  cannot run script in the application's origin.
"""

from __future__ import annotations

import io
import warnings
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

_EXT = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png", ".gif": "gif", ".webp": "webp"}


def sniff(data: bytes) -> str | None:
    """Image type from the magic bytes: ``jpeg`` / ``png`` / ``gif`` / ``webp`` or ``None``."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def check_image(data: bytes, ext: str, content_type: str | None) -> str | None:
    """Problem with an upload, or ``None`` when ``data`` really is a ``ext`` image."""
    want = _EXT.get(ext.lower())
    if want is None:
        return "unsupported image type (jpg, png, gif, webp)"
    if content_type and not content_type.lower().startswith(("image/", "application/octet-stream")):
        return f"not an image upload (content type {content_type})"
    got = sniff(data)
    if got is None:
        return "the file is not a jpg, png, gif or webp image"
    if got != want:
        return f"the file is a {got} image but is named {ext}"
    return None


# --------------------------------------------------------------------------------------------------
# Decode + re-encode (CRBS parity audit B2)
# --------------------------------------------------------------------------------------------------

#: Pillow format -> stored file extension
ALLOWED_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "GIF": ".gif"}
MAX_SIDE = 1600
#: decoded pixels refused before any full decode (decompression bombs): 40 MP ≈ 8000 x 5000
MAX_PIXELS = 40_000_000
MAX_BYTES = 10 * 1024 * 1024

UPLOAD_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'",
    "Cross-Origin-Resource-Policy": "same-site",
}


class ImageError(ValueError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def sanitize_image(data: bytes, *, max_side: int = MAX_SIDE, max_bytes: int = MAX_BYTES) -> tuple[bytes, str]:
    """Return ``(re-encoded bytes, extension)`` for a JPEG/PNG/GIF upload; :class:`ImageError` otherwise."""
    if len(data) > max_bytes:
        raise ImageError(413, f"image larger than {max_bytes // (1024 * 1024)} MB")
    if not data:
        raise ImageError(400, "empty file")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            probe = Image.open(io.BytesIO(data))
            fmt = probe.format or ""
            if fmt not in ALLOWED_FORMATS:
                raise ImageError(400, "unsupported image type (jpg, png, gif)")
            width, height = probe.size
            if width < 1 or height < 1 or width * height > MAX_PIXELS:
                raise ImageError(413, f"image dimensions {width}x{height} are too large")
            probe.verify()  # verify() leaves the image unusable: decode a second handle
            img = Image.open(io.BytesIO(data))
            img.load()
    except ImageError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageError(400, "the file is not a readable jpg, png or gif image") from exc
    except (OSError, SyntaxError, ValueError) as exc:  # truncated / corrupt data
        raise ImageError(400, "the file is not a readable jpg, png or gif image") from exc
    return _encode(img, fmt, max_side), ALLOWED_FORMATS[fmt]


def _encode(img: Image.Image, fmt: str, max_side: int) -> bytes:
    if fmt == "JPEG":
        img = ImageOps.exif_transpose(img) or img  # keep the orientation, drop the EXIF block itself
    if fmt == "GIF":
        img.seek(0)  # first frame only
        img = img.convert("RGBA") if "transparency" in img.info else img.convert("RGB")
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    save: dict[str, Any] = {}
    if fmt == "JPEG":
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        save = {"quality": 88, "optimize": True}
    elif fmt == "PNG":
        if img.mode not in ("RGB", "RGBA", "L", "LA", "P"):
            img = img.convert("RGBA")
        save = {"optimize": True}
    elif img.mode != "RGBA":
        img = img.convert("P", palette=Image.Palette.ADAPTIVE)
    img.save(out, format=fmt, **save)
    return out.getvalue()


class SafeStaticFiles(StaticFiles):
    """``StaticFiles`` that adds :data:`UPLOAD_HEADERS` to every file response."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        for k, v in UPLOAD_HEADERS.items():
            response.headers[k] = v
        return response
