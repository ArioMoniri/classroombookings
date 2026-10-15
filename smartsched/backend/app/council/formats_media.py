"""Pixels that may be sent to the model (Phase 19 P19-A3): images and scanned PDF pages.

* Images are verified and decoded by Pillow with a pixel cap (a decompression bomb is a 413), then re-encoded
  (PNG, or JPEG for photos): EXIF, GPS, XMP, ICC and comments do not survive, and the long side is at most
  :data:`MAX_SIDE` px (Claude's recommended input size, so nothing is sent that the model would downscale).
* A scanned PDF is not sent as a PDF (its metadata, attachments and hidden text layers would go with it): at most
  :data:`MAX_PAGES` pages are rendered with pypdfium2 at :data:`DPI` dpi and sent as page images.

The upload precheck (:func:`check_image`) runs Pillow's ``verify`` on every image before a job exists.
"""

from __future__ import annotations

import io
from typing import Any

from app.core import safe_files

MAX_SIDE = 1568
MAX_PIXELS = 40_000_000  # decoded image area cap (a 2 KB PNG may declare 100 000 x 100 000)
MAX_PAGES = 20
DPI = 150


def _pil() -> Any:
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    return Image


def check_image(data: bytes) -> tuple[int, int]:
    """Verify an upload; returns (width, height). 400 unreadable, 413 too many pixels."""
    Image = _pil()
    try:
        with Image.open(io.BytesIO(data)) as im:
            size: tuple[int, int] = (int(im.size[0]), int(im.size[1]))
            im.verify()
    except Image.DecompressionBombError as exc:
        raise safe_files.UnsafeFileError(413, f"the image declares too many pixels (limit {MAX_PIXELS})") from exc
    except Exception as exc:  # noqa: BLE001 - truncated / not an image
        raise safe_files.UnsafeFileError(400, f"the image cannot be read: {type(exc).__name__}") from exc
    if size[0] * size[1] > MAX_PIXELS:
        raise safe_files.UnsafeFileError(413, f"the image declares too many pixels (limit {MAX_PIXELS})")
    return size


def clean_image(data: bytes) -> tuple[bytes, str, dict[str, Any]]:
    """(bytes, media type, info) of the re-encoded, metadata-free, downscaled image."""
    from PIL import ImageOps

    Image = _pil()
    w, h = check_image(data)
    with Image.open(io.BytesIO(data)) as im:
        had_exif = bool(im.info.get("exif")) or bool(getattr(im, "getexif", lambda: {})())
        im = ImageOps.exif_transpose(im)  # keep the visible orientation, then drop the tag with the rest
        photo = im.format == "JPEG"
        im = im.convert("RGB" if photo or im.mode in ("CMYK", "P", "LA") else ("RGBA" if "A" in im.mode else "RGB"))
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        out = io.BytesIO()
        if photo:
            im.save(out, "JPEG", quality=90, optimize=True)
            media = "image/jpeg"
        else:
            im.save(out, "PNG", optimize=True)
            media = "image/png"
        info = {"width": w, "height": h, "sent_width": im.size[0], "sent_height": im.size[1], "exif_stripped": had_exif}
    return out.getvalue(), media, info


def pdf_pages(data: bytes) -> tuple[list[bytes], int]:
    """(PNG images of the first :data:`MAX_PAGES` pages, total page count) of a scanned PDF."""
    import pypdfium2 as pdfium

    try:
        doc = pdfium.PdfDocument(data)
    except Exception as exc:  # noqa: BLE001
        raise safe_files.UnsafeFileError(400, f"cannot read the PDF: {type(exc).__name__}") from exc
    try:
        total = len(doc)
        images: list[bytes] = []
        for i in range(min(total, MAX_PAGES)):
            page = doc[i]
            pil = page.render(scale=DPI / 72).to_pil()
            pil.thumbnail((MAX_SIDE, MAX_SIDE))
            buf = io.BytesIO()
            pil.convert("RGB").save(buf, "PNG", optimize=True)
            images.append(buf.getvalue())
            page.close()
        return images, total
    finally:
        doc.close()


__all__ = ["DPI", "MAX_PAGES", "MAX_PIXELS", "MAX_SIDE", "check_image", "clean_image", "pdf_pages"]
