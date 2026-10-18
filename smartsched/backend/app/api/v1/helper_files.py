"""Helper file router API (HB-23b; docs/design/v3/helper-file-router.md §6).

* ``POST   /helper/files/classify``          one card for a dropped file (or several: one card to the setup wizard)
* ``POST   /helper/files/route``             the chooser pick / "Başka bir tür seç" with the staged file
* ``POST   /helper/files/handoff``           the card's button: re-checks and writes ``helper.file.handoff``
* ``DELETE /helper/files/{sid}``             ✕ / "Vazgeç" / sheet close: the stage goes at once
* ``GET    /helper/files/examples``          the header-only templates; ``/examples/{kind}.{ext}`` downloads one

Classify answers 200 for every outcome a card can show (detected, ambiguous, unknown, needs_planner, refused,
error) and 413 only when the stream passes the cap before a card exists. It writes no database row: no job, no
helper message, no audit row, no usage row. The ``upload_token`` lives in the response body only, never in a URL.
"""

from __future__ import annotations

import time
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import Response as RawResponse
from pydantic import BaseModel, ConfigDict, Field

from app.ai.helper import cards
from app.ai.helper import files as hf
from app.api.deps import DB, CurrentAccess
from app.api.v1.helper import refused
from app.core import safe_files
from app.core.config import get_settings
from app.services import audit

router = APIRouter(prefix="/helper/files", tags=["helper"])

Token = Annotated[str, Field(min_length=20, max_length=2000, pattern=r"^[A-Za-z0-9_\-.]+$")]


def cap_bytes() -> int:
    """``min(upload_max_mb, council_max_file_mb)``: 15 MB by default (§1.3)."""
    st = get_settings()
    return int(min(float(st.upload_max_mb), float(st.council_max_file_mb)) * safe_files.MiB)


def stage_error(exc: hf.StageError) -> HTTPException:
    return refused(exc.status, exc.code, exc.tr, exc.en)


async def _helper_on(db: DB, access: CurrentAccess) -> None:
    from app.ai.helper import settings as hs

    pol = await hs.policy(db, access)
    if not pol.enabled:
        raise refused(
            403, "helper_disabled", "Yardımcı hesabınızda kapalı.", "The helper is turned off for your account."
        )


def _stage_out(st: hf.Staged) -> dict[str, Any]:
    from app.ai.helper.schema import utc_iso

    return {"upload_token": st.token, "expires_at": utc_iso(st.expires_at), "size": st.size, "format": st.format}


@router.post("/classify")
async def classify(
    request: Request,
    db: DB,
    access: CurrentAccess,
    file: list[UploadFile] = File(..., description="one file; several (planners only) go to the setup wizard"),
    context: str | None = Form(None, max_length=64, description="feature_id of the page it was dropped on"),
    lang: str | None = Form(None, max_length=8, description="tr | en, for logs only (cards carry both)"),
    term_id: int | None = Form(None, description="the page's active term (default: the current term)"),
    kind: str | None = Form(None, max_length=48, description="a forced kind (chooser pick with HELPER_FILE_STAGE=off)"),
) -> dict[str, Any]:
    await _helper_on(db, access)
    # one live file per person (HB-23d N9): every new drop drops the previous stage first, whatever its outcome
    # (rate limit, refusal, 413, 422, resend, unknown); a routable file is staged again below
    hf.clear(access.user_id)
    t0 = time.perf_counter()
    if not hf.rate_ok(access.user_id):
        card = cards.status(
            "refusal",
            "rate_limited",
            "Çok sayıda dosya okundu. Bir dakika sonra yeniden deneyin.",
            "Too many files were read. Try again in a minute.",
            action="classify_file",
        )
        return {"card": cards.dump(card)}
    cap = cap_bytes()
    reads: list[tuple[str, bytes]] = []
    planner = any(p in access.perms for p in hf.ONBOARDING.perms)
    # several files: the setup wizard reads them together (planners only); anyone else picks one file (HB-23d N8)
    if len(file) > 1 and not planner:
        raise refused(
            422,
            "one_file_only",
            "Yardımcıya bir seferde bir dosya bırakın. Birden çok dosyayı yalnızca planlama ekibi Kurulum "
            "sihirbazına birlikte gönderebilir.",
            "Drop one file at a time on the helper. Only the planning team can send several files to the setup "
            "wizard together.",
        )
    for up in file:
        try:
            data = await safe_files.read_upload(up, cap)
        except safe_files.UnsafeFileError as exc:
            mb = f"{cap / safe_files.MiB:.0f}"
            card = cards.status(
                "refusal",
                "file_too_large",
                f"Dosya çok büyük; en çok {mb} MB okuyabilirim.",
                f"The file is too large; I can read up to {mb} MB.",
                action="classify_file",
            )
            raise HTTPException(
                413,
                {
                    "code": "file_too_large",
                    "message": exc.message,
                    "message_en": exc.message,
                    "message_tr": card.message.tr,
                    "card": cards.dump(card),
                },
            ) from exc
        reads.append((up.filename or "upload", data))
    sess = hf.session_tag(request, access.user)
    # no stage without a sign-in session to bind it to (KVKK review 14): the browser sends the file again
    stage_on = bool(get_settings().helper_file_stage) and bool(sess)
    if len(reads) > 1:
        return await _classify_many(db, access, reads, t0)
    name, data = reads[0]
    sig, refusal = await hf.read_file(name, data)
    if refusal is not None or sig is None:
        assert refusal is not None
        hf.telemetry(None, None, "-", (time.perf_counter() - t0) * 1000, "refused")
        return {"card": cards.dump(hf.refusal_card(access, refusal))}
    try:
        built = await hf.build(db, access, sig, active_term_id=term_id, context=context, forced_kind=kind)
    except hf.KindNotAllowed as exc:
        raise refused(
            403, "kind_not_allowed", "Bu dosya bu türe aktarılamaz.", "This file can't be routed to that type."
        ) from exc
    out: dict[str, Any] = {}
    if built.kinds:
        if stage_on:
            st = hf.stage(data, sig, hf.token_kinds(access, sig), access.user_id, sess)
            out["stage"] = _stage_out(st)
            if built.card.type == "choice":  # type: ignore[attr-defined]
                built.card.args = {"upload_token": st.token}  # type: ignore[attr-defined]
        else:
            out["resend"] = True
    hf.telemetry(built.kind, built.score, sig.card_format, (time.perf_counter() - t0) * 1000, built.state)
    return {"card": cards.dump(built.card), **out}


async def _classify_many(db: DB, access: CurrentAccess, reads: list[tuple[str, bytes]], t0: float) -> dict[str, Any]:
    """Open question 4 (owner: take the recommendation): one card, "{n} dosya bıraktınız", whose primary opens the
    setup wizard with every file. Nothing is staged (orchestrator decision after the KVKK review, item 16): the
    browser still holds the File objects and the wizard uploads them itself, so the answer says ``resend``."""
    from app.ai.helper import schema as s

    good: list[tuple[bytes, hf.Signals]] = []
    lines_tr: list[str] = []
    lines_en: list[str] = []
    skipped: list[str] = []
    for i, (name, data) in enumerate(reads, start=1):
        sig, refusal = await hf.read_file(name, data)
        if sig is None:
            skipped.append(str(i))
            continue
        good.append((data, sig))
        cands = hf.candidates(sig)
        if len(lines_tr) < 4:
            if cands and hf.decide(cands) != "unknown":
                info = hf.KINDS[cands[0][0]]
                lines_tr.append(f"{i}. dosya: {info.label[0]}")
                lines_en.append(f"File {i}: {info.label[1].lower()}")
            else:
                lines_tr.append(f"{i}. dosya: tanınmadı")
                lines_en.append(f"File {i}: not recognised")
    if not good:
        name, data = reads[0]
        _, refusal = await hf.read_file(name, data)
        assert refusal is not None
        return {"card": cards.dump(hf.refusal_card(access, refusal))}
    warnings = []
    if skipped:
        warnings.append(
            s.FileWarning(
                code="file_skipped",
                status="bad",
                message=cards.txt(
                    f"Okunamayan dosyalar gönderilmez: {', '.join(skipped)}. dosya.",
                    f"Files that couldn't be read are left out: file {', '.join(skipped)}.",
                ),
            )
        )
    n = len(reads)
    card = s.FileCard(
        id=cards.new_id(),
        title=cards.txt(
            f"{n} dosya bıraktınız. Birden çok dosyayı Kurulum sihirbazı birlikte okur.",
            f"You dropped {n} files. The setup wizard reads several files together.",
        ),
        state="detected",
        format="mixed",
        evidence=s.Texts(tr=lines_tr, en=lines_en),
        warnings=warnings,
        primary=s.FileRoute(
            feature_id="onboarding",
            label=cards.txt("Kurulum sihirbazında aç", "Open in the setup wizard"),
            carries_file=True,
        ),
        explain=s.Texts(tr=[hf.KINDS["intake_json"].hint[0]], en=[hf.KINDS["intake_json"].hint[1]]),
    )
    out: dict[str, Any] = {"card": cards.dump(card), "resend": True}
    hf.telemetry("many", None, "mixed", (time.perf_counter() - t0) * 1000, "detected")
    return out


class RouteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upload_token: Token
    kind: Annotated[str, Field(pattern=r"^[a-z_]{2,48}$")]
    term_id: int | None = None
    context: str | None = Field(default=None, max_length=64)


@router.post("/route")
async def route(body: RouteIn, request: Request, db: DB, access: CurrentAccess) -> dict[str, Any]:
    """The chooser pick (and "Başka bir tür seç"): the card of that kind from the staged signals; the token stays."""
    await _helper_on(db, access)
    sess = hf.session_tag(request, access.user)
    try:
        meta, _ = hf.peek(body.upload_token, access.user_id, sess)
    except hf.StageError as exc:
        raise stage_error(exc) from exc
    if body.kind not in (meta.get("kinds") or []):
        raise refused(
            403, "kind_not_allowed", "Bu dosya bu türe aktarılamaz.", "This file can't be routed to that type."
        )
    sig = hf.Signals.from_dict(meta["sig"])
    try:
        built = await hf.build(
            db, access, sig, active_term_id=body.term_id, context=body.context, forced_kind=body.kind
        )
    except hf.KindNotAllowed as exc:
        raise refused(
            403, "kind_not_allowed", "Bu dosya bu türe aktarılamaz.", "This file can't be routed to that type."
        ) from exc
    return {"card": cards.dump(built.card)}


class HandoffIn(BaseModel):
    """Exactly one ``upload_token`` (HB-23d N5): a new stage clears the person's previous one, so there is never more
    than one live token; several dropped files are never staged (the wizard uploads them itself)."""

    model_config = ConfigDict(extra="forbid")
    upload_token: Token
    kind: Annotated[str, Field(pattern=r"^[a-z_]{2,48}$")] | None = None
    feature_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$", max_length=64)]
    params: dict[str, str | int | None] = Field(default_factory=dict)


@router.post("/handoff")
async def handoff(body: HandoffIn, request: Request, db: DB, access: CurrentAccess) -> dict[str, Any]:
    """The card's button (an ``isTrusted`` activation only): re-checks the token, the permission for ``feature_id``
    and the params, then writes one ``helper.file.handoff`` audit row (kind, page, term, extension, size, the first
    12 characters of the SHA-256; never the file name). It does not consume the token: the target page does."""
    from app.models import Term

    await _helper_on(db, access)
    sess = hf.session_tag(request, access.user)
    try:
        meta = hf.peek(body.upload_token, access.user_id, sess)[0]
    except hf.StageError as exc:
        raise stage_error(exc) from exc
    nope = refused(403, "route_not_allowed", "Bu sayfa bu dosya için açılamaz.", "This page can't take this file.")
    kind = body.kind or hf.CHOOSER_ONBOARDING
    if kind == hf.CHOOSER_ONBOARDING:
        # the setup wizard with the file: planners only
        if body.feature_id != "onboarding" or not any(p in access.perms for p in hf.ONBOARDING.perms):
            raise nope
        if hf.CHOOSER_ONBOARDING not in (meta.get("kinds") or []):
            raise nope
        href: dict[str, Any] = {}
    else:
        if kind not in (meta.get("kinds") or []) or kind not in hf.KINDS:
            raise refused(
                403, "kind_not_allowed", "Bu dosya bu türe aktarılamaz.", "This file can't be routed to that type."
            )
        sig = hf.Signals.from_dict(meta["sig"])
        routes = [r for r in hf.file_routes(kind, sig, None, None) if hf._visible(access, r)]  # noqa: SLF001
        match = next((r for r in routes if r.feature_id == body.feature_id), None)
        if match is None:
            raise nope
        href = {k: v for k, v in match.params.items() if k != "term_id"}
        if "kind" in body.params and body.params["kind"] != match.params.get("kind"):
            raise nope
        term_id = body.params.get("term_id")
        if term_id is not None:
            if not isinstance(term_id, int) or await db.get(Term, term_id) is None:
                raise refused(422, "bad_term", "Bu dönem bulunamadı.", "That term was not found.")
            href["term_id"] = term_id
        year = body.params.get("year")
        if year is not None:
            if not isinstance(year, int) or not 2000 <= year <= 2100:
                raise refused(422, "bad_year", "Yıl geçerli değil.", "The year is not valid.")
            href["year"] = year
    await audit.record(
        db,
        "helper.file.handoff",
        "helper_file",
        str(meta.get("sha") or "")[:12],
        after={
            "kind": kind,
            "feature_id": body.feature_id,
            "term_id": href.get("term_id"),
            "ext": meta.get("fmt"),
            "size": meta.get("size"),
            "sha12": str(meta.get("sha") or "")[:12],
            "files": 1,
            "via": "helper",
        },
        actor=access.user,
    )
    await db.commit()
    return {"ok": True, "href_params": href}


@router.delete("/{sid}", status_code=204)
async def drop_stage(sid: str, access: CurrentAccess) -> Response:
    """✕ "Dosyayı kaldır", "Vazgeç", sheet close: the person's stage goes at once (204 also when already gone)."""
    hf.delete(sid, access.user_id)
    return Response(status_code=204)


@router.get("/examples")
async def examples(_: CurrentAccess) -> list[dict[str, Any]]:
    from app.ai.helper import file_examples

    return file_examples.listing()


_MEDIA = {"xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "csv": "text/csv; charset=utf-8"}


@router.get("/examples/{name}")
async def example_file(name: str, _: CurrentAccess) -> RawResponse:
    """``{kind}.{xlsx|csv}``: a header-only template generated from the importer's column definitions."""
    from app.ai.helper import file_examples

    kind, _dot, ext = name.partition(".")
    ex = file_examples.EXAMPLES.get(kind)
    if ex is None or ext != ex.format:
        raise HTTPException(
            404,
            {
                "code": "not_found",
                "message": "no such template",
                "message_en": "no such template",
                "message_tr": "Böyle bir örnek dosya yok.",
            },
        )
    return RawResponse(
        file_examples.render(kind),
        media_type=_MEDIA[ex.format],
        headers={"Content-Disposition": f'attachment; filename="{ex.file_name}"', "Cache-Control": "no-store"},
    )


# ------------------------------------------------------------------------------------- the target pages (§6.5)


def one_token(upload_token: str | None, upload_tokens: list[str]) -> str | None:
    """The one hand-over token of a request (HB-23d N5). ``upload_tokens`` is the deprecated list form; more than
    one token answers 422 ``one_upload_token``: a new stage clears the person's previous one, so a second token
    could never be live."""
    tokens = [t for t in ([upload_token] if upload_token else []) + list(upload_tokens) if t]
    if len(tokens) > 1:
        from app.schemas.messages import problem

        raise problem(
            422,
            "one_upload_token",
            "Yardımcıdan bir seferde yalnızca bir dosya gelebilir. Diğer dosyaları sayfaya kendiniz ekleyin.",
            "Only one file can come from the helper at a time. Add the other files on the page yourself.",
        )
    return tokens[0] if tokens else None


def look(request: Request, user: Any, token: str) -> tuple[str, dict[str, Any]]:
    """Check a hand-over token without consuming it (owner, session, expiry): (extension, metadata). The target
    endpoints call this first and :func:`take` only after their own checks passed (KVKK review 12)."""
    try:
        meta, _ = hf.peek(token, int(user.id), hf.session_tag(request, user))
    except hf.StageError as exc:
        from app.schemas.messages import problem

        raise problem(exc.status, exc.code, exc.tr, exc.en) from exc
    return str(meta.get("ext") or meta.get("fmt") or "bin"), meta


async def take(request: Request, user: Any, token: str) -> tuple[str, bytes, dict[str, Any]]:
    """Consume a hand-over token on a target endpoint: (extension, bytes, metadata). The project's error shape on
    403 (another person or session) / 410 (used, expired)."""
    try:
        meta, data = hf.consume(token, int(user.id), hf.session_tag(request, user))
    except hf.StageError as exc:
        from app.schemas.messages import problem

        raise problem(exc.status, exc.code, exc.tr, exc.en) from exc
    ext = str(meta.get("ext") or meta.get("fmt") or "bin")
    return ext, data, meta


def handed_name(meta: dict[str, Any], ext: str, filename: str | None) -> str:
    """The stored file name: the browser's own name when the page sends it, else ``helper-<sha12>.<ext>``."""
    from pathlib import PurePath

    name = PurePath(filename or "").name.strip()
    if name and PurePath(name).suffix.lower() == f".{ext}".lower():
        return name[:200]
    return f"helper-{str(meta.get('sha') or '')[:12]}.{ext or 'bin'}"


__all__ = ["cap_bytes", "handed_name", "look", "one_token", "router", "take"]
