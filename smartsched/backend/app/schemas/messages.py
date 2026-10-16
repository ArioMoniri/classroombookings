"""Bilingual refusals for request validation (round-1 R1-M-17, T-R1-31).

A pydantic validator that raises a plain ``ValueError`` reaches the client as ``"Value error, <english>"``. The
helpers here keep the stored English sentence and add the Turkish one, so the UI can show the reader's language
and keep the technical detail in an expandable part:

* :func:`coded` builds the ``PydanticCustomError`` a ``field_validator`` raises. FastAPI's 422 then carries
  ``{type: <code>, loc, msg: <english>, ctx: {code, message_tr, message_en}}`` with no pydantic prefix.
* :class:`Refusal` is the ``ValueError`` a service raises when it knows both sentences; :func:`validated` turns
  it (or any ``ValueError``) into the coded form inside a validator.
* :func:`problem` is the same shape for an ``HTTPException`` raised in a route (``detail`` dict with ``code``,
  ``message`` / ``message_en`` and ``message_tr``), the shape ``lib/api/error-text.ts`` already reads.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import HTTPException
from pydantic_core import PydanticCustomError

T = TypeVar("T")


class Refusal(ValueError):
    """A ``ValueError`` with a code and both sentences (``str()`` stays the English one)."""

    def __init__(self, code: str, tr: str, en: str) -> None:
        super().__init__(en)
        self.code = code
        self.tr = tr
        self.en = en


def coded(code: str, tr: str | None, en: str) -> PydanticCustomError:
    """The error a ``field_validator`` raises: ``msg`` is the English sentence, ``ctx`` holds both."""
    ctx: dict[str, Any] = {"code": code, "message_en": en}
    if tr:
        ctx["message_tr"] = tr
    # the template is formatted with ``ctx``; the sentence itself is never re-formatted
    return PydanticCustomError(code, "{message_en}", ctx)


def validated(fn: Callable[[Any], T], value: Any, *, code: str = "invalid", tr_by_text: dict[str, str] | None = None) -> T:
    """Run a service cleaner inside a validator; a :class:`Refusal` keeps its code and both texts, another
    ``ValueError`` gets ``code`` and the Turkish text looked up by its English message (``tr_by_text``)."""
    try:
        return fn(value)
    except Refusal as exc:
        raise coded(exc.code, exc.tr, exc.en) from exc
    except ValueError as exc:
        text = str(exc)
        tr = (tr_by_text or {}).get(text)
        if tr is None and tr_by_text:
            tr = next((v for k, v in tr_by_text.items() if k and text.startswith(k)), None)
        raise coded(code, tr, text) from exc


def problem(status: int, code: str, tr: str, en: str, **extra: Any) -> HTTPException:
    """An ``HTTPException`` whose detail is ``{code, message, message_en, message_tr, ...extra}``."""
    return HTTPException(status, {"code": code, "message": en, "message_en": en, "message_tr": tr, **extra})


def pick(language: str | None, tr: str, en: str) -> str:
    """The sentence in a user's profile language (Turkish only when the profile says so)."""
    return tr if (language or "").lower().startswith("tr") else en
