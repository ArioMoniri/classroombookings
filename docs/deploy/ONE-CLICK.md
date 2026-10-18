# One-click deploy: both branches

Two branches, the same code, one difference: `smartsched/deploy/profile.env`.

| Branch | `SEED_PROFILE` | First boot loads | AWS pod |
|---|---|---|---|
| `claude/gracious-cerf-w1598m` | `institution` | the Bahar / Güz / Final workbooks, the room master, their preference rules, the learning extraction, `bookings.approval_mode=all` | `--pod gracious` (SSM `/smartsched`) |
| `claude/smartsched-universal` | `empty` | nothing. The administrator starts at `/admin/welcome` (the welcome guide) and `/onboarding` (uploads any files) | `--pod universal` (SSM `/smartsched-universal`) |

Every setting is reachable in one of two ways:

- **At deploy time**, from the command line: flags or environment variables of `deploy.sh` /
  `smartsched_aws.py up`.
- **Afterwards**, from the first administrator's panel (Kurulum). No step needs SSH or a hand-edited file
  on the server.

Settings given on the command line are written into the database once, by
`smartsched/deploy/seed/bootstrap_settings.py`. It calls the same handlers the panel uses, so the values get the
same validation, encryption and audit record. A settings row (`deploy.bootstrap_settings`) records each group
once it is written. Later deploys skip that group, so a value an administrator changed in the panel is never
overwritten. A group the panel had already set before the first deploy is kept too. `BOOTSTRAP_FORCE=1` writes
the groups again.

## 1. Local or any Docker host

Requirements: Docker Engine 24+ with Compose v2.

### The command

```bash
cd smartsched/deploy
./deploy.sh --admin-email you@university.edu.tr
```

That is the whole deploy for both branches. `profile.env` picks what gets loaded. `--profile empty|institution`
overrides it for one run.

The optional values below are listed in `./deploy.sh --help`. Every flag also works as `--flag=value`.

| Value | Flag | Environment | Where it ends up |
|---|---|---|---|
| Administrator e-mail | `--admin-email` | `ADMIN_EMAIL` | `.env`, first start only (deploy.sh asks on a terminal when it is missing) |
| Public domain + HTTPS | `--domain smartsched.uni.edu.tr` (`--acme-email`, default: the admin e-mail) | | `.env`: `TLS_DOMAIN`, `PUBLIC_URL`, `CORS_ORIGINS`, `ACME_EMAIL`. The Caddy edge stays on for later runs (`--no-tls` turns it off for one run) |
| Seed profile | `--profile` | `SEED_PROFILE` | this run only (`profile.env` stays as it is) |
| Observability (Prometheus, Loki, Grafana) | `--observability` / `--no-observability` | `OBSERVABILITY=1` (first run) | `.env` `OBSERVABILITY` (default 1 on hosts with 7 GiB or more) |
| Nightly backup | `--backups` | `BACKUP_CRON_FILE` | `/etc/cron.d/smartsched-backup` (when run as root; otherwise deploy.sh prints the line to install) |
| Institution name | `--org-name "Örnek Üniversitesi"` | `ORG_NAME` | database `org.name` (once) |
| AI provider + key | `--ai-provider anthropic` (default), `--ai-base-url` | `AI_PROVIDER`, **`AI_API_KEY`** | database, the key encrypted (once) |
| Outgoing mail | `--smtp-host`, `--smtp-port`, `--smtp-security starttls\|ssl\|none`, `--smtp-user`, `--smtp-from`, `--smtp-from-name` | `SMTP_*`, **`SMTP_PASSWORD`** | database `smtp.*`, the password encrypted (once) |
| security.txt contact | `--security-contact security@uni.edu.tr` | `SECURITY_CONTACT` | database `security.contact_email` (once) |
| Calendar OAuth clients | | `GOOGLE_CLIENT_ID` + **`GOOGLE_CLIENT_SECRET`**, `MICROSOFT_CLIENT_ID` + **`MICROSOFT_CLIENT_SECRET`** (+ `MICROSOFT_TENANT`) | database `integrations.*` (once) |

The **bold** values are secrets. They come from the environment only, never from a flag, so they stay out of
shell history and the process list. deploy.sh passes them to the backend container by name, and they are never
written to `.env`.

Example with everything set, for the universal branch:

```bash
AI_API_KEY=sk-ant-... SMTP_PASSWORD=... ./deploy.sh --admin-email it@uni.edu.tr --domain smartsched.uni.edu.tr \
  --org-name "Örnek Üniversitesi" --smtp-host smtp.uni.edu.tr --smtp-user noreply@uni.edu.tr \
  --smtp-from noreply@uni.edu.tr --security-contact security@uni.edu.tr --backups
```

Bad input stops the deploy before anything is built (`SMTP_PORT` without `SMTP_HOST`, a non-numeric port, a
`--domain` with `https://`, an unknown provider). A value that the backend refuses later, such as a password
over an unencrypted connection, is reported. The other groups are still written, and you can set the refused one
in the panel.

### What it asks

Only the administrator e-mail, and only when it is missing and the shell is a terminal. Everything else has a
default that works.

### What it prints

```
[settings] org: ORG_NAME=Örnek Üniversitesi  (institution name (Kurum ayarları, /admin/settings))
[settings] ai: AI_API_KEY=<set>, AI_PROVIDER=anthropic  (AI provider key (Yapay zekâ yönetimi, /admin/ai))
...
[deploy] seed profile: institution (owner files, once; ...)        | empty (nothing loaded; ... /admin/welcome and /onboarding)
[deploy] deploy-time settings: written once into the database (the admin panel wins on later deploys)
[deploy] SmartSched is up:  https://smartsched.uni.edu.tr            (http://localhost:8080 without --domain)
[deploy] Admin login:       it@uni.edu.tr  (password: ADMIN_PASSWORD in smartsched/deploy/.env)
[deploy] Admin password:    <20 characters>  (shown once; you must change it at the first login)
[deploy] Seed profile:      institution  (smartsched/deploy/profile.env)
[deploy] Observability:     https://.../grafana/ (admins only)  ·  panel: https://.../admin/ops
```

The password line appears on the first deploy only, and only on a terminal (`SHOW_ADMIN_PASSWORD=0` hides it,
`=1` forces it on the first run). The password stays in `.env` as `ADMIN_PASSWORD`. Changing that value later
has no effect: the first login forces a new password.

## 2. AWS (one EC2 pod per branch)

```bash
python infra/aws/smartsched_aws.py up --pod gracious      # claude/gracious-cerf-w1598m, institution data
python infra/aws/smartsched_aws.py up --pod universal     # claude/smartsched-universal, empty
```

The deploy-time flags are the same as locally: `--org-name`, `--ai-provider`, `--ai-base-url`, `--smtp-host`,
`--smtp-port`, `--smtp-security`, `--smtp-user`, `--smtp-from`, `--smtp-from-name`, `--security-contact`,
`--observability` / `--no-observability`. The secrets come from the caller's environment the same way
(`AI_API_KEY`, `SMTP_PASSWORD`, `GOOGLE_CLIENT_*`, `MICROSOFT_CLIENT_*`). `--admin-email` and `--acme-email` set
the administrator and the Let's Encrypt account. The domain is always `<elastic-ip-with-dashes>.sslip.io`.

How the values travel:

1. `up` checks them with the deploy tool before any AWS call.
2. `up` stores them in SSM `{prefix}/bootstrap/<KEY>`: String for plain values, SecureString for secrets. This
   happens before the instance launches.
3. On first boot, `pod-bootstrap.sh` reads them (`python3 -m podci bootstrap-env`) into a 0600 file owned by the
   CI user. It sources that file for the first `deploy.sh --tls` and then deletes it.
4. Every pod CI deploy passes the same parameters to `deploy.sh` as environment variables. Test gates never
   receive them.

Because of step 4, values stored with a later `up` on a running pod are applied by its next deploy, once per
group, and the panel still wins. The pod role can already read `{prefix}/*`, so no IAM change is needed. Only
the parameter names show up in the output and the JSON result, never the values.

What it prints: the panel URL, the instance id, the admin e-mail, the command that reads the admin password, the
SSM parameter names, and `bootstrap_parameters` (the names it wrote). The pod needs about 15 to 25 minutes after
`up` returns.

```bash
aws ssm get-parameter --region <region> --name /smartsched/admin_password --with-decryption \
  --query Parameter.Value --output text          # universal pod: /smartsched-universal/admin_password
```

Through GitHub Actions (`infra/aws/POD_ACTION`, docs/deploy/AWS.md section 3), `up pod=universal <timestamp>`
runs the same `up`. Deploy-time settings go on the same line as `key=value` (`org="Örnek Üniversitesi"
admin=it@uni.edu.tr smtp-host=... security=... observability=off`, list in AWS.md section 3), and the optional repo
secrets `AI_API_KEY` / `SMTP_PASSWORD` (plus the Google / Microsoft client ones) are passed from the environment,
never printed. `domain=` is refused there: the pod's domain is always the sslip.io name.

On the pod, backups run as `smartsched-backup.timer`: nightly at 02:30 Istanbul time, 7 days kept in
`/var/lib/smartsched-ci/backups` on the pod disk. That protects against a bad migration or a deletion, but not
against losing the volume. Off-host (S3) backups are not set up, by the owner's decision of 2026-10-18: backups stay
on the pod. Uploads are purged by `smartsched-upload-purge.timer`.

## 3. First login checklist (Kurulum)

Sign in with the admin e-mail and the generated password. The first screen forces a new password. Then:

| # | Where (menu, path) | What | Needed for |
|---|---|---|---|
| 1 | Kurum ayarları, `/admin/settings` | Institution name (set if `--org-name` was given), website, logo, booking display, time zone, languages | the header, e-mails |
| 2 | Ayarlar > Genel, `/settings` | **Güvenlik iletişimi**: the security.txt contact (set if `--security-contact` was given) | `/.well-known/security.txt` |
| 3 | E-posta, `/admin/email` | SMTP (guided wizard, test mail, DNS check; set if `--smtp-host` was given). A provider abroad (Gmail, Microsoft 365, ...) needs the KVKK art. 9 acknowledgement here | invitations, booking and approval mails |
| 4 | Yapay zekâ yönetimi, `/admin/ai` | Provider keys (the deploy's key is already stored), **the KVKK transfer record per provider**, models, routes per feature (voice: the speech-to-text route and the voice card), limits, guardrails | AI features. Without a key, everything works without AI |
| 5 | Ayarlar > Yapay zekâ, `/settings` | the council AI switch (KVKK acknowledgement) | AI in `/onboarding` |
| 6 | KVKK, `/admin/kvkk` | Privacy notices, retention, the AI personal-data default, data subject requests | KVKK |
| 7 | Entegrasyonlar, `/admin/integrations` | Sign-in providers (Entra / Google / SAML / OIDC, guided setup, invitations), calendar sync sign-off + Google / Microsoft OAuth clients (set if the `*_CLIENT_*` variables were given), webhooks, notification channels | SSO, calendar push |
| 8 | Oturum açma (LDAP), `/admin/authentication` | LDAP directory sign-in | LDAP |
| 9 | Kullanıcılar, `/admin/users` | Further administrators, roles, invitations | |
| 10 | universal: Karşılama rehberi `/admin/welcome` and `/onboarding`; institution: the imported terms under Planlama | data | |
| 11 | Operasyon, `/admin/ops` | health, errors, the Grafana link (observability on) | operations |

Settings that are deliberately not in the panel, and are set at deploy time only:

- `TLS_DOMAIN`, `ACME_EMAIL`, `OBSERVABILITY`, `GRAFANA_ADMIN_PASSWORD` (generated; Grafana's own login form is
  off, and admins reach `/grafana/` through the panel session);
- the sizing values (`*_CPUS`, `*_MEMORY`, `UVICORN_WORKERS`, `SOLVER_WORKERS`);
- `APP_SECRET`, `JWT_SECRET` and `POSTGRES_PASSWORD` (generated);
- the seed profile.

Scaling notes: smartsched/deploy/README.md "Scaling" and docs/deploy/AWS.md section 7.

## 4. Verification

- `bash -n` on every deploy script (`pod-ci/tests/test_deploy_oneclick.py::test_bash_syntax`).
- Dry deploys of both profiles behind a fake docker, end to end:
  - `.env` creation and secrets, flags, TLS, observability;
  - the seed run only for `institution`;
  - the settings container with values passed by name only, and the secrets in neither `.env` nor argv;
  - the summary (`test_deploy_oneclick.py`).
- The real backend handlers on SQLite: values stored once, secrets encrypted, an admin edit kept on redeploy,
  refused values reported with exit 3 and no value echoed (`test_bootstrap_settings.py`).
- The pod path: SSM `bootstrap/*` reaches the first deploy and every pod CI deploy, and an SSM outage does not
  block a deploy (`test_pod_bootstrap_settings.py`).
- `up` stores the values before the launch, as SecureString for secrets, with the values absent from the result
  (`infra/aws/tests/test_bootstrap_settings.py`).
