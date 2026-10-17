"""Security contact of the institution (RFC 9116 security.txt; security follow-up wave3-sec2).

``GET`` / ``PUT /api/v1/admin/security-contact`` (administrators; the write is audited ``security.contact``) and the
public ``/.well-known/security.txt`` + ``/security.txt`` built from it (:mod:`app.services.security_txt`).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.api.deps import DB, Admin
from app.services import audit
from app.services import security_txt as st

router = APIRouter(prefix="/admin/security-contact", tags=["security"])
public_router = APIRouter(tags=["security"])


class ContactIn(BaseModel):
    contact_email: str | None = Field(default=None, max_length=320)
    contact_url: str | None = Field(default=None, max_length=600)
    policy_url: str | None = Field(default=None, max_length=600)
    preferred_languages: str | None = Field(default=None, max_length=100)


def refusal(exc: st.InvalidContact) -> HTTPException:
    return HTTPException(
        422,
        {
            "code": "invalid_security_contact",
            "field": exc.field,
            "message": exc.message_en,
            "message_en": exc.message_en,
            "message_tr": exc.message_tr,
        },
    )


async def _view(db: DB) -> dict[str, Any]:
    vals = await st.current(db)
    return {
        **vals,
        "warning": None if vals["configured"] else st.UNSET_WARNING,
        "last_change": await st.last_change(db),
    }


@router.get("")
async def get_contact(db: DB, _: Admin) -> dict[str, Any]:
    return await _view(db)


@router.put("")
async def put_contact(body: ContactIn, db: DB, user: Admin) -> dict[str, Any]:
    try:
        values = st.validate(body.model_dump())
    except st.InvalidContact as exc:
        raise refusal(exc) from exc
    before = await st.current(db)
    await st.save(db, values)
    await audit.record(
        db,
        st.AUDIT_ACTION,
        "setting",
        "security",
        before={k: before.get(k) for k in st.KEYS},
        after=dict(values),
        actor=user,
    )
    await db.commit()
    return await _view(db)


@public_router.get("/.well-known/security.txt", include_in_schema=False)
@public_router.get("/security.txt", include_in_schema=False)
async def security_txt(request: Request, db: DB) -> PlainTextResponse:
    text = st.build(await st.current(db), host=request.headers.get("host", ""), scheme=request.url.scheme)
    return PlainTextResponse(text, headers={"Cache-Control": "max-age=3600", "X-Content-Type-Options": "nosniff"})
