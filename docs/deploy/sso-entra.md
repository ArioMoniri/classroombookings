# Sign-in with Microsoft 365 (Microsoft Entra ID): steps for the university IT department

SmartSched lets staff sign in with their university Microsoft 365 account. Microsoft checks the password and MFA,
so SmartSched stores no password for these users. SmartSched is the relying party of the university's own Entra ID
tenant, using OpenID Connect: the authorization code flow with PKCE, state and nonce. No broker and no third party
sit in between. Owner decision of 2026-10-15; design in
[docs/product/2026-10-15-integrations-options.md](../product/2026-10-15-integrations-options.md) §5.5.

This page has two parts:

* **Part A** is for the university IT department (Bilgi İşlem). It covers the app registration in Entra ID.
* **Part B** is for the SmartSched administrator. It says what to ask IT for and where to enter it.

> **Never send secret values by e-mail, chat or a ticket comment, and never commit them to the repository.** The
> client secret goes straight from the Entra portal into the SmartSched settings screen or into AWS SSM. Nobody else
> needs to see it.

---

## Part A. App registration (for the IT department)

You need the **Application Administrator** or **Cloud Application Administrator** role in the university tenant.
**Global Administrator** also works. The SmartSched administrator gives you one value before you start: the panel's
public address, `https://<domain>` (for example `https://rezervasyon.<universite>.edu.tr`).

### A1. Register the application

1. Go to the [Microsoft Entra admin center](https://entra.microsoft.com) › **Identity** › **Applications** ›
   **App registrations** › **New registration**.
2. **Name**: `SmartSched`.
3. **Supported account types**: **Accounts in this organizational directory only (single tenant)**.
   - Do not choose a multi-tenant option. SmartSched refuses the `common`, `organizations` and `consumers` authorities.
4. **Redirect URI**: platform **Web**, value exactly:

   ```
   https://<domain>/api/v1/auth/sso/entra/callback
   ```

   - It must use `https`, have no trailing slash, and match character for character.
   - The SmartSched administrator can read the exact value under Admin › Microsoft 365 girişi (`redirect_uri`), or
     from `GET /api/v1/auth/sso/admin/entra`.
5. Click **Register**.

### A2. Authentication settings

1. Open the app › **Authentication**.
2. Leave **Implicit grant and hybrid flows** unticked: neither *Access tokens* nor *ID tokens*. SmartSched uses the
   authorization code flow only.
3. **Allow public client flows**: **No**.
4. Leave the **Front-channel logout URL** empty. SmartSched has no single logout yet.

### A3. Client credential

1. Open the app › **Certificates & secrets** › **Client secrets** › **New client secret**.
2. Description: `SmartSched sign-in`. Expiry: 12 or 24 months.
   - Put a reminder in the IT calendar one month before expiry. An expired secret stops every Microsoft sign-in;
     password sign-in for the break-glass administrator keeps working.
3. Copy the secret **Value** once and enter it yourself, together with the SmartSched administrator, in the
   settings screen or in SSM (Part B, step B2).
   - The *Secret ID* is not the secret.
   - Do not send the value to anyone.

Certificates (`private_key_jwt`) are not supported yet. Use a client secret. Certificate credentials are a roadmap
item.

### A4. Token configuration (claims)

SmartSched reads only the ID token. Open the app › **Token configuration**:

1. **Add optional claim** › token type **ID** › tick:
   - `email`: the user's e-mail, shown in SmartSched.
   - `upn`: used together with `preferred_username` to match admin invites.
   - `xms_edov`: "email domain owner verified". SmartSched trusts an `email` value for an invite match only when this
     flag is true.
   - `acct`: account status. SmartSched refuses guests (`acct = 1`).

   If the portal asks to add the Microsoft Graph `email` / `profile` permission, accept.
2. Optional, only if SmartSched should take roles from Entra (Part B, B4):
   - **Add groups claim** › **Groups assigned to the application** › ID token: **Group ID**.
   - Choose *Groups assigned to the application*, not *All groups*. A user in more than 200 groups otherwise gets no
     `groups` claim at all (group overage). SmartSched then keeps the user's role unchanged.

The claims SmartSched uses and why:

| Claim | Source | Use in SmartSched |
|---|---|---|
| `iss` | always | Must equal `https://login.microsoftonline.com/<tenant-id>/v2.0` exactly |
| `tid` | always | Must equal the pinned tenant id |
| `aud` | always | Must equal the application (client) id |
| `exp`, `nbf`, `iat` | always | Token lifetime (2 minutes of clock skew tolerated) |
| `nonce` | always | Must equal the nonce SmartSched sent (replay protection) |
| `oid` | `profile` scope | **The identity key**, with `tid`. Immutable. Never the e-mail |
| `preferred_username` | `profile` scope | The UPN: shown, and matched against admin invites (one time) |
| `name` | `profile` scope | Display name |
| `email`, `upn`, `xms_edov`, `acct` | optional claims (A4) | See above |
| `roles` | app roles (A5) | Optional role mapping |
| `groups` | groups claim (A4.2) | Optional role mapping (group object ids) |
| `idp` | guests only | Present and different from `iss`: the guest is refused |

### A5. App roles (optional)

Do this only if the SmartSched owner decides that Entra assigns roles (Part B, B4). By default, roles are managed in
SmartSched by its administrators, and this step can be skipped.

1. Open the app › **App roles** › **Create app role**, once per role. Use these **Values** (SmartSched maps them;
   the display names are up to you):

   | Display name | Allowed member types | Value |
   |---|---|---|
   | SmartSched Planner | Users/Groups | `SmartSched.Planner` |
   | SmartSched Viewer | Users/Groups | `SmartSched.Viewer` |
   | SmartSched Teacher | Users/Groups | `SmartSched.Teacher` |

   - Only create an administrator role (`SmartSched.Admin`) if the owner asks for it explicitly.
   - SmartSched ignores a mapping to its Administrator role unless its own administrator has switched
     `allow_admin_mapping` on.
2. Assign these roles to **groups**, not to individual users, under **Enterprise applications** › SmartSched ›
   **Users and groups** › **Add user/group**. Assigning groups needs Entra ID P1 or higher.

### A6. Who may sign in (important)

SmartSched creates an account automatically for anyone of the tenant who signs in. It always gives the lowest role
(Teacher), and SmartSched administrators change roles later. Students are in the same tenant. To keep SmartSched
staff-only:

1. Go to **Enterprise applications** › SmartSched › **Properties** › **Assignment required?** › **Yes** › Save.
2. Go to **Users and groups** › assign the staff groups: academic staff, the planning office and IT.
   - Unassigned accounts are stopped by Microsoft before they reach SmartSched (error AADSTS50105).

### A7. Consent

1. Go to **App registrations** › SmartSched › **API permissions**. Microsoft Graph *Delegated*: `openid`, `profile`,
   `email`. `User.Read` may stay; SmartSched does not call Graph for sign-in.
2. Click **Grant admin consent for <university>**, so staff do not see a consent prompt.

### A8. What to give the SmartSched administrator

| Item | Where in the portal | Secret? |
|---|---|---|
| **Directory (tenant) ID**, a GUID | App registration › Overview | No |
| **Application (client) ID**, a GUID | App registration › Overview | No |
| **Client secret value** | Certificates & secrets (A3) | **Yes**: enter it yourself in the settings screen or SSM, never send it |
| Secret expiry date | Certificates & secrets | No |
| The registered redirect URI | Authentication | No |
| Whether *Assignment required* is on, and which groups are assigned | Enterprise applications | No |
| Optional: the app role values (A5) or the group object IDs to map | App roles / Groups | No |

---

## Part B. SmartSched administrator

### B1. What to ask IT for

Send IT the panel address and a link to this page, and ask for the following:

1. A **single-tenant** app registration named SmartSched, with the redirect URI
   `https://<domain>/api/v1/auth/sso/entra/callback` (A1–A2).
2. The **Directory (tenant) ID** and the **Application (client) ID** (A8).
3. A **client secret** (A3), entered by IT and you together, directly into SmartSched or SSM. Ask for its expiry date.
4. The optional ID token claims `email`, `upn`, `xms_edov` and `acct` (A4).
5. **Assignment required = Yes**, with the staff groups assigned (A6).
6. **Admin consent** granted (A7).
7. Only if Entra should assign roles: the app roles (A5) or the group object IDs.

### B2. Enter the values

The settings screen is Admin › Microsoft 365 girişi (frontend follow-up). Until it exists, use the API with an
administrator's token:

```bash
curl -X PUT https://<domain>/api/v1/auth/sso/admin/entra \
  -H "Authorization: Bearer $ADMIN_JWT" -H "Content-Type: application/json" \
  -d '{"tenant_id": "<directory-tenant-id>", "client_id": "<application-client-id>", "client_secret": "<paste here, never in chat>"}'
```

- The secret is encrypted at rest with `APP_SECRET` (Fernet) and never returned; the API shows only
  `client_secret_set`.
- An empty `client_secret` in a later `PUT` keeps the stored secret.
- To rotate the secret, `PUT` the new value.

**SSM instead of the screen.** Store `/smartsched/sso_entra_tenant_id`, `/smartsched/sso_entra_client_id` and
`/smartsched/sso_entra_client_secret` (SecureString) in SSM. The deploy then passes them to the backend as
`SSO_ENTRA_TENANT_ID`, `SSO_ENTRA_CLIENT_ID` and `SSO_ENTRA_CLIENT_SECRET`; wiring this into the deploy is a devops
follow-up. Values entered on the screen take precedence; the environment fills only the fields the screen leaves
empty (`from_environment` in `GET /api/v1/auth/sso/admin/entra`).

The public URL (`PUBLIC_URL`, or `integrations.public_url` on the settings screen) must be set. The redirect URI is
built from it, and SmartSched refuses to enable sign-in without it.

### B3. Switch on and test

1. `PUT /api/v1/auth/sso/admin/entra {"enabled": true}`. SmartSched refuses this until the tenant, the client id, the
   secret and the public URL are all present.
2. Open the login page in a private window › **Microsoft 365 ile giriş yap**. Sign in with a staff test account.
   The new account appears in Users with the role **Teacher**.
3. Try a student account, or any account not assigned in A6. Microsoft should stop it (AADSTS50105).
4. The audit log shows `auth.self_signup`, `auth.login` (method `oidc`) and, for refusals, `auth.login_refused`
   with the reason. The panel itself only shows a generic code plus a `ref` (the audit row id), so it never reveals
   whether an account exists.

### B4. Rules SmartSched applies (owner decisions 2026-10-15)

- **Two ways to get an account.**
  - (a) The person signs in with Entra, from the pinned tenant only. The account is created with the lowest role
    (`self_signup`, the `sso_self_signup` setting, on by default; `default_role_id`, Teacher, can never be an
    administrative role). With `self_signup` off, sign-in is invite-only.
  - (b) An administrator creates it:
    - `POST /api/v1/auth/sso/admin/invites {"email": "<UPN>", "role": "PLANNER"}` creates the account as
      **invited**.
    - The first Microsoft sign-in whose verified UPN equals the invite binds the Microsoft account. This happens
      once and is audited as `auth.identity_bound` and `user.invite_accepted`.
    - Invites expire after `invite_days` (30). An expired invite blocks sign-in for that address until an
      administrator renews it (`POST /api/v1/auth/sso/admin/invites/{id}/renew`) or deletes it.
    - The invite has a link, `/login?invite=<token>`, to copy or e-mail. Binding also works from the plain login
      page.

  There is no self-registration with a local password.
- **Existing accounts.**
  - An administrator marks an account "bind on next Microsoft sign-in" with
    `POST /api/v1/auth/sso/admin/users/{id}/bind`. Another administrator's account can be marked too, but only by
    someone who holds all of its permissions.
  - Alternatively, the user links the account themselves from Profile, after re-entering the SmartSched password.
  - SmartSched **never** links an account just because the e-mail is the same.
- **Identity.** After binding, SmartSched recognises the person by the Entra `oid` + `tid` only. A renamed UPN or a
  changed e-mail keeps the same SmartSched account.
- **Roles are managed in SmartSched** by its administrators, under the no-escalation rule.
  - The Entra role mapping is optional and **off** by default (`role_mapping_enabled`).
  - When it is on, the mapping is applied at every sign-in, and a demotion signs the user out everywhere.
  - A mapping to an administrative role needs `allow_admin_mapping`. Only an Administrator can turn that on.
- **Break-glass administrator.** At least one active administrator keeps a local password and password sign-in at
  all times.
  - SmartSched refuses to switch on "Microsoft sign-in only for non-administrators" (`oidc_only_non_admins`) without
    one.
  - A role mapping never demotes the last such administrator.
  - Keep that password in the university's password safe, not in a personal account.
- **Guests** (B2B accounts of other organisations) are refused. Personal Microsoft accounts are refused too.
- **Nothing of Microsoft is stored** except `oid`, `tid`, the e-mail at sign-in and the display name. The access,
  refresh and ID tokens are discarded at once.

### B5. Known limits

- **No deprovisioning push (SCIM).**
  - Someone disabled in Entra can no longer sign in, but a session that is already open lasts until it expires
    (`JWT_EXPIRE_MINUTES`).
  - Disable the account in SmartSched too, or keep the session lifetime short.
- **No single logout.** Signing out of SmartSched does not sign the person out of Microsoft.
- **Not yet tested against the real tenant.** The flow is tested against a local fake of the Microsoft identity
  platform (`smartsched/backend/tests/test_sso_*.py`). Run the pod smoke test (B3) once IT has registered the app.
