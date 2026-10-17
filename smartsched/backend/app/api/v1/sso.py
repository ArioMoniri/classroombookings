"""Sign-in with Microsoft Entra ID (``/api/v1/auth/sso/*``; app/services/sso.py; UI contract
docs/design/v2/sign-in.md §14-§15; IT checklist docs/deploy/sso-entra.md).

Public: ``GET /providers`` (the login page's ``auth`` block + TR/EN texts), ``GET /entra/start`` (302 to Microsoft),
``GET /entra/callback`` (302 back to the panel), ``POST /exchange`` (one-time ticket -> SmartSched JWT),
``GET /invites/{token}`` (invite banner).
Signed in: ``GET /me``, ``POST /entra/link`` (password + confirm), ``DELETE /entra/link``.
``planning.admin``: ``GET/PUT /admin/entra``, ``GET/POST /admin/entra/mappings``, ``DELETE /admin/entra/mappings/{id}``.
``setup.users``: ``GET/POST /admin/invites``, ``POST /admin/invites/{id}/renew``, ``DELETE /admin/invites/{id}``,
``POST /admin/users/{id}/bind``, ``DELETE /admin/users/{id}/identity``, ``PUT /admin/users/{id}/instructor``,
``GET /admin/user-status``.

Wave 3b W3-IDP (several providers, app/services/identity/**): public ``GET /{slug}/start``, ``GET /{slug}/callback``
(OIDC kinds), ``POST /{slug}/acs`` + ``GET /{slug}/metadata`` (SAML), ``GET /test-done`` (the test-login popup's last
page), ``POST /invites/{token}/password`` (local-password invites). ``planning.admin``: ``GET /admin/kinds``,
``GET/POST /admin/providers``, ``PUT /admin/providers/order``, ``GET/PUT/DELETE /admin/providers/{id}``,
``GET /admin/providers/{id}/setup``, ``POST /admin/providers/{id}/discover``, ``POST /admin/providers/{id}/test``,
``GET /admin/providers/{id}/test/{test_id}``, ``GET/POST/DELETE /admin/providers/{id}/mappings``. ``setup.users``:
``POST /admin/invites/{id}/resend``, ``POST /admin/invites/bulk``.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.api.deps import DB, Admin, CurrentUser, UsersAdmin
from app.core.config import get_settings
from app.core.security import user_token
from app.schemas.sso import (
    AuthorizeOut,
    BindIn,
    ExchangeIn,
    InstructorIn,
    InstructorOut,
    InviteIn,
    InviteOut,
    LinkIn,
    MappingIn,
    MappingOut,
    ProvidersOut,
    PublicInviteOut,
    SsoConfigIn,
    SsoConfigOut,
    SsoMeOut,
    SsoTokenOut,
)
from app.services import sso as svc
from app.services.identity import invites as idp_invites
from app.services.identity import kinds as idp_kinds
from app.services.identity import providers as idp
from app.services.identity import saml as idp_saml
from app.services.identity.schemas import (
    BulkInviteIn,
    LocalPasswordIn,
    OrderIn,
    ProviderCreateIn,
    ProviderIn,
    ProviderMappingIn,
    ResendIn,
)

router = APIRouter(prefix="/auth/sso", tags=["sso"])


async def _guarded[T](coro: Awaitable[T]) -> T:
    try:
        return await coro
    except svc.SsoAdminError as exc:
        raise HTTPException(exc.status, exc.detail()) from exc


def _redirect(url: str) -> RedirectResponse:
    resp = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"  # the code / ticket never leaks to another site
    return resp


# --------------------------------------------------------------------------------------------------
# public
# --------------------------------------------------------------------------------------------------


@router.get("/providers", response_model=ProvidersOut)
async def providers(db: DB) -> dict[str, Any]:
    """The login page: ``auth`` (Microsoft button on/off, domain hint, self sign-up, password door, LDAP, the
    sign-up role's name) and the TR/EN texts of the ``error`` codes. Nothing about any account."""
    return await svc.providers_out(db)


@router.post("/exchange", response_model=SsoTokenOut)
async def exchange(body: ExchangeIn, db: DB) -> SsoTokenOut:
    """The panel turns the one-time ticket (2 minutes) into SmartSched's normal bearer token (``tv`` claim: sign-out,
    disabling and role changes revoke it like any other session), plus ``next`` and the ``welcome`` kind."""
    got = await svc.exchange_ticket(db, body.ticket)
    if got is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired sign-in ticket")
    return SsoTokenOut(
        access_token=user_token(got.user),
        expires_in=get_settings().jwt_expire_minutes * 60,
        next=got.next,
        welcome=got.welcome,
        inviter_name=got.inviter_name,
    )


@router.get("/invites/{token}", response_model=PublicInviteOut)
async def invite_banner(token: str, db: DB) -> dict[str, Any]:
    """The banner of ``/login?invite=<token>``: inviter, role, masked address, days left. 404 unknown / used /
    revoked, 410 expired."""
    out = await svc.public_invite(db, token[:256])
    if out is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invite_invalid")
    if out.get("expired"):
        raise HTTPException(status.HTTP_410_GONE, "invite_expired")
    return out


# --------------------------------------------------------------------------------------------------
# signed-in user
# --------------------------------------------------------------------------------------------------


@router.get("/me", response_model=SsoMeOut)
async def my_identity(user: CurrentUser, db: DB) -> dict[str, Any]:
    return await svc.me(db, user)


@router.post(f"/{svc.PROVIDER}/link", response_model=AuthorizeOut)
async def link(body: LinkIn, user: CurrentUser, db: DB) -> AuthorizeOut:
    """Profile -> "Microsoft hesabını bağla": the user re-enters the SmartSched password and confirms; the panel then
    navigates to ``authorize_url``. The only way an existing account links without an administrator's mark."""
    url = await _guarded(svc.start_link(db, user, body.password))
    await db.commit()
    return AuthorizeOut(authorize_url=url)


@router.delete(f"/{svc.PROVIDER}/link", status_code=status.HTTP_204_NO_CONTENT)
async def unlink(user: CurrentUser, db: DB) -> Response:
    await _guarded(svc.unlink_own(db, user))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------------------------------
# planning.admin: configuration and role mapping
# --------------------------------------------------------------------------------------------------


@router.get(f"/admin/{svc.PROVIDER}", response_model=SsoConfigOut)
async def get_config(db: DB, _: Admin) -> dict[str, Any]:
    return await svc.config_out(db)


@router.put(f"/admin/{svc.PROVIDER}", response_model=SsoConfigOut)
async def put_config(body: SsoConfigIn, db: DB, me: Admin) -> dict[str, Any]:
    """Partial update. 422: incomplete client or no public URL when enabling, a privileged sign-up role; 409: the
    break-glass rule (``oidc_only_non_admins`` needs an active administrator with a local password)."""
    try:
        await svc.update_config(db, me, body.model_dump(exclude_unset=True))
    except svc.SsoAdminError as exc:
        await db.rollback()
        raise HTTPException(exc.status, exc.detail()) from exc
    await db.commit()
    return await svc.config_out(db)


@router.get(f"/admin/{svc.PROVIDER}/mappings", response_model=list[MappingOut])
async def get_mappings(db: DB, _: Admin) -> list[dict[str, Any]]:
    return await svc.list_mappings(db)


@router.post(f"/admin/{svc.PROVIDER}/mappings", response_model=MappingOut, status_code=status.HTTP_201_CREATED)
async def post_mapping(body: MappingIn, db: DB, me: Admin) -> dict[str, Any]:
    """Entra app role value or group object id -> SmartSched role. Applied at every login only while
    ``role_mapping_enabled`` is on. 403: the editor lacks a permission of the role (no escalation); 422: an
    administrative role while ``allow_admin_mapping`` is off."""
    m = await _guarded(svc.add_mapping(db, me, body.claim, body.value, body.role_id))
    await db.commit()
    return next(x for x in await svc.list_mappings(db) if x["id"] == m.id)


@router.delete(f"/admin/{svc.PROVIDER}/mappings/{{mapping_id}}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mapping(mapping_id: int, db: DB, me: Admin) -> Response:
    await _guarded(svc.delete_mapping(db, me, mapping_id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------------------------------
# setup.users: invites, "bind on next SSO login", instructor link, status
# --------------------------------------------------------------------------------------------------


@router.get("/admin/invites", response_model=list[InviteOut])
async def get_invites(
    db: DB, _: UsersAdmin, provider: str | None = Query(default=None, max_length=40)
) -> list[dict[str, Any]]:
    return await svc.list_invites(db, provider)


@router.post("/admin/invites/bulk")
async def bulk_invites(body: BulkInviteIn, db: DB, me: UsersAdmin) -> dict[str, Any]:
    """CSV (``;`` or ``,``, BOM and NBSP tolerated; header ``E-posta;Ad Soyad;Rol[;Sağlayıcı][;Gün]`` or English):
    one invite per row, each row refused on its own (``errors`` with line, code, TR/EN)."""
    out = await idp_invites.bulk(db, me, body.model_dump())
    await db.commit()
    return out


@router.post("/admin/invites/{invite_id}/resend")
async def resend_invite(invite_id: int, db: DB, me: UsersAdmin, body: ResendIn | None = None) -> dict[str, Any]:
    """The same link again by e-mail; 409 when the invite expired (renew it)."""
    out = await _guarded(idp_invites.resend(db, me, invite_id, body.locale if body else None))
    await db.commit()
    return out


@router.post("/admin/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
async def post_invite(body: InviteIn, db: DB, me: UsersAdmin) -> dict[str, Any]:
    """Create an account (no password) for an institution e-mail / UPN: status ``invited`` until the first Entra
    login of the pinned tenant whose verified UPN equals it binds ``oid + tid`` (once). 409 ``invite_pending`` (renew
    it), ``account_bound``, ``account_exists`` (use ``POST /admin/users/{id}/bind``)."""
    out = await _guarded(svc.create_invite(db, me, body.model_dump()))
    if body.send_email:
        from app.models.sso import SsoInvite

        inv = await db.get(SsoInvite, out["id"])
        if inv is not None:
            out["email_status"] = (await idp_invites.send_invite_email(db, me, inv, body.locale))["status"]
    await db.commit()
    return out


@router.post("/admin/invites/{invite_id}/renew", response_model=InviteOut)
async def renew_invite(invite_id: int, db: DB, me: UsersAdmin) -> dict[str, Any]:
    """A new link and the full validity again; the old link stops working."""
    out = await _guarded(svc.renew_invite(db, me, invite_id))
    await db.commit()
    return out


@router.delete("/admin/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invite(invite_id: int, db: DB, me: UsersAdmin) -> Response:
    """Revoke an invite or cancel a scheduled binding (the account itself stays)."""
    await _guarded(svc.delete_invite(db, me, invite_id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/admin/users/{user_id}/bind", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
async def bind_user(user_id: int, body: BindIn, db: DB, me: UsersAdmin) -> dict[str, Any]:
    """Mark an existing account (also another administrator's, under the no-escalation rule; never your own)
    "bind on next SSO login" for ``email`` (default: the account's e-mail)."""
    out = await _guarded(svc.mark_bind(db, me, user_id, body.email, body.days, body.provider))
    await db.commit()
    return out


@router.delete("/admin/users/{user_id}/identity", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_user(user_id: int, db: DB, me: UsersAdmin) -> Response:
    await _guarded(svc.admin_unlink(db, me, user_id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/admin/users/{user_id}/instructor", response_model=InstructorOut)
async def set_instructor(user_id: int, body: InstructorIn, db: DB, me: UsersAdmin) -> dict[str, Any]:
    """Link the login to an instructor record (``instructors.user_id``; ``null`` clears). Audited."""
    out = await _guarded(svc.set_instructor(db, me, user_id, body.instructor_id))
    await db.commit()
    return out


@router.get("/admin/user-status")
async def user_status(db: DB, _: UsersAdmin) -> dict[str, dict[str, Any]]:
    """``{user_id: {status, auth_methods, invite, binding_pending, self_signup_at, break_glass, instructor_id}}`` for
    every account (the Users screen's columns, sign-in.md §13)."""
    return await svc.user_status(db)


# --------------------------------------------------------------------------------------------------
# wave 3b: several identity providers (planning.admin), guided setup and test login
# --------------------------------------------------------------------------------------------------


async def _provider(db: Any, provider_id: int) -> Any:
    return await _guarded(idp.get_row(db, provider_id))


@router.get("/admin/kinds")
async def kinds(_: Admin) -> list[dict[str, Any]]:
    """The "add provider" gallery: one card per kind with its presets and fields (SAML: ``library_required``)."""
    return idp_kinds.catalog(saml_available=idp_saml.AVAILABLE)


@router.get("/admin/providers")
async def list_providers(db: DB, _: Admin) -> dict[str, Any]:
    return await idp.list_out(db)


@router.post("/admin/providers", status_code=status.HTTP_201_CREATED)
async def create_provider(body: ProviderCreateIn, db: DB, me: Admin) -> dict[str, Any]:
    """A draft provider (off). 409 ``exists`` for a second Microsoft / Google provider."""
    row = await _guarded(idp.create(db, me, body.model_dump()))
    await db.commit()
    return await idp.provider_out(db, row)


@router.put("/admin/providers/order")
async def order_providers(body: OrderIn, db: DB, me: Admin) -> dict[str, Any]:
    """The /login button order (the listed ids first, in this order)."""
    await _guarded(idp.reorder(db, me, body.ids))
    await db.commit()
    return await idp.list_out(db)


@router.get("/admin/providers/{provider_id}")
async def get_provider(provider_id: int, db: DB, _: Admin) -> dict[str, Any]:
    return await idp.provider_out(db, await _provider(db, provider_id))


@router.put("/admin/providers/{provider_id}")
async def put_provider(provider_id: int, body: ProviderIn, db: DB, me: Admin) -> dict[str, Any]:
    """Partial update; a changed issuer / metadata is discovered at once (``discovery`` in the answer). 422: invalid
    values, incomplete when enabling, an ineligible sign-up role; 403: no escalation; 409: ``conflict`` (stale
    ``version``), ``break_glass``, ``last_admin_path``."""
    row = await _provider(db, provider_id)
    try:
        extra = await idp.update(db, me, row, body.model_dump(exclude_unset=True))
    except svc.SsoAdminError as exc:
        await db.rollback()
        raise HTTPException(exc.status, exc.detail()) from exc
    await db.commit()
    out = await idp.provider_out(db, row)
    if extra.get("discovery") is not None:
        out["discovery"] = {**out["discovery"], **extra["discovery"]}
    return out


@router.delete("/admin/providers/{provider_id}")
async def delete_provider(provider_id: int, db: DB, me: Admin) -> Response:
    """Only while off: its identities, mappings and invites go; the accounts stay."""
    row = await _provider(db, provider_id)
    await _guarded(idp.remove(db, me, row))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin/providers/{provider_id}/setup")
async def provider_setup(provider_id: int, db: DB, _: Admin) -> dict[str, Any]:
    """Step 2 of the guided setup: the values to paste into the provider's console (built from the public URL), the
    steps in TR/EN and the fields to fill in."""
    return await idp.setup_out(db, await _provider(db, provider_id))


@router.post("/admin/providers/{provider_id}/discover")
async def provider_discover(provider_id: int, db: DB, me: Admin) -> dict[str, Any]:
    """Fetch and validate the discovery document / IdP metadata now (one check row per item, TR/EN)."""
    row = await _provider(db, provider_id)
    out = await idp.discover(db, row, actor=me)
    await db.commit()
    return out


@router.post("/admin/providers/{provider_id}/test")
async def provider_test(provider_id: int, db: DB, me: Admin) -> dict[str, Any]:
    """Start a test login (the panel opens ``authorize_url`` in a popup and polls the result). Works while the
    provider is off; nothing is created or signed in; the tokens are never stored."""
    row = await _provider(db, provider_id)
    try:
        url, test_id = await svc.start_test(db, me, row)
    except svc.SsoError as err:
        raise HTTPException(
            409,
            {"code": err.code, "en": "the provider is not configured yet", "tr": "Sağlayıcı henüz yapılandırılmadı"},
        ) from err
    await db.commit()
    return {"authorize_url": url, "test_id": test_id}


@router.get("/admin/providers/{provider_id}/test/{test_id}")
async def provider_test_result(provider_id: int, test_id: str, db: DB, me: Admin) -> dict[str, Any]:
    row = await _provider(db, provider_id)
    out = await svc.test_result(db, me, row, test_id)
    if out is None:
        raise HTTPException(404, {"code": "not_found", "en": "unknown or expired test", "tr": "Test bulunamadı"})
    return out


@router.get("/admin/providers/{provider_id}/mappings", response_model=list[MappingOut])
async def provider_mappings(provider_id: int, db: DB, _: Admin) -> list[dict[str, Any]]:
    row = await _provider(db, provider_id)
    return await svc.list_mappings(db, row.name)


@router.post("/admin/providers/{provider_id}/mappings", response_model=MappingOut, status_code=status.HTTP_201_CREATED)
async def provider_add_mapping(provider_id: int, body: ProviderMappingIn, db: DB, me: Admin) -> dict[str, Any]:
    row = await _provider(db, provider_id)
    m = await _guarded(svc.add_mapping(db, me, body.claim, body.value, body.role_id, row.name))
    await db.commit()
    return next(x for x in await svc.list_mappings(db, row.name) if x["id"] == m.id)


@router.delete("/admin/providers/{provider_id}/mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
async def provider_delete_mapping(provider_id: int, mapping_id: int, db: DB, me: Admin) -> Response:
    row = await _provider(db, provider_id)
    await _guarded(svc.delete_mapping(db, me, mapping_id, row.name))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


_TEST_PAGE = """<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport"
content="width=device-width,initial-scale=1"><title>SmartSched</title><style>body{{font:16px/1.5 system-ui,sans-serif;
margin:0;display:grid;place-items:center;min-height:100vh;background:#f5f5f7;color:#1d1d1f}}main{{max-width:28rem;
padding:2rem;text-align:center}}h1{{font-size:1.25rem}}</style></head><body><main><h1>{tr_title}</h1><p>{tr_body}</p>
<p lang="en">{en_title} {en_body}</p></main></body></html>"""


@router.get("/test-done", response_class=HTMLResponse)
async def test_done(ok: str = Query(default="0", max_length=1)) -> HTMLResponse:
    """The popup's last page after a test login: plain bilingual text, no script (the panel polls the result)."""
    good = ok == "1"
    html = _TEST_PAGE.format(
        tr_title="Test girişi tamamlandı" if good else "Test girişi başarısız",
        tr_body="Bu pencereyi kapatabilirsiniz; sonuç kurulum ekranında görünür.",
        en_title="Test sign-in finished." if good else "Test sign-in failed.",
        en_body="You can close this window; the result shows in the setup screen.",
    )
    return HTMLResponse(html, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.post("/invites/{token}/password")
async def accept_local_invite(token: str, body: LocalPasswordIn, db: DB) -> dict[str, Any]:
    """A local-password invite: the invited person sets the password, then signs in with the form. 404 for an
    unknown / used / expired / non-local invite (one answer: no enumeration)."""
    user = await idp_invites.accept_local(db, token[:256], body.password)
    if user is None:
        raise HTTPException(
            404,
            {
                "code": "invite_invalid",
                "en": svc.MESSAGES["invite_invalid"]["en"],
                "tr": svc.MESSAGES["invite_invalid"]["tr"],
            },
        )
    await db.commit()
    return {"ok": True, "email": user.email}


# --------------------------------------------------------------------------------------------------
# public sign-in routes of every provider (declared last: ``{slug}`` must not shadow the fixed paths above)
# --------------------------------------------------------------------------------------------------


@router.get("/{slug}/start", status_code=status.HTTP_302_FOUND)
async def start(
    slug: str,
    db: DB,
    next: str | None = Query(default=None, max_length=255),  # noqa: A002 - the panel's parameter name
    invite: str | None = Query(default=None, max_length=256),
    prompt: str | None = Query(default=None, max_length=32),
    login_hint: str | None = Query(default=None, max_length=255),
) -> RedirectResponse:
    """A real navigation from a provider button: 302 to the provider (OIDC: PKCE + state + nonce, 10 minutes; SAML:
    an AuthnRequest). ``next`` is kept only when it is a same-origin path. Refusals: 302 to ``/login?error=…``
    (``not_enabled``, ``invite_invalid``, ``invite_expired``, ``invite_provider``)."""
    slug = slug[:40].lower()
    try:
        url = await svc.start_login(db, next, invite=invite, prompt=prompt, login_hint=login_hint, slug=slug)
    except svc.SsoError as err:
        return _redirect(await svc.refuse(db, err, "login", slug=slug))
    await db.commit()
    return _redirect(url)


@router.get("/{slug}/callback", status_code=status.HTTP_302_FOUND)
async def callback(
    slug: str,
    db: DB,
    code: str | None = Query(default=None, max_length=4096),
    state: str | None = Query(default=None, max_length=512),
    error: str | None = Query(default=None, max_length=256),
) -> RedirectResponse:
    """The provider's redirect (the registered redirect URI). Always a 302: ``/login/sso?ticket=…[&next=…]
    [&welcome=self|invited|bound]`` after a sign-in, ``/profile?sso=linked`` after a link, the test page after a test
    login, or ``/login?error=<code>[&ref=…][&provider=…][&invite=…&invited_masked=…&signed_in=…]``."""
    return _redirect(await svc.finish(db, code=code, state=state, error=error, slug=slug[:40].lower()))


@router.post("/{slug}/acs", status_code=status.HTTP_302_FOUND)
async def saml_acs(
    slug: str,
    db: DB,
    SAMLResponse: str | None = Form(default=None, max_length=1_100_000),  # noqa: N803 - the SAML binding's name
    RelayState: str | None = Form(default=None, max_length=512),  # noqa: N803
) -> RedirectResponse:
    """The SAML IdP's HTTP-POST to the Assertion Consumer Service. Same answers as the OIDC callback."""
    url = await svc.finish_saml(db, slug=slug[:40].lower(), saml_response=SAMLResponse, relay_state=RelayState)
    return _redirect(url)


@router.get("/{slug}/metadata")
async def saml_metadata(slug: str, db: DB) -> Response:
    """The SP metadata to import at the IdP / federation (YETKİM, eduGAIN)."""
    row = await svc.get_provider(db, slug=slug[:40].lower())
    xml = await idp.sp_metadata_xml(db, row) if row is not None else None
    if xml is None:
        raise HTTPException(404, "not a SAML provider")
    return Response(xml, media_type="application/samlmetadata+xml", headers={"Cache-Control": "no-cache"})
