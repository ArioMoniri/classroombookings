# E-mail (SMTP) setup and themed e-mails

Owner: wave 3b W3-MAIL. Screen: **/admin/email** (also the E-posta card of /admin/integrations). Design:
[`../design/v3/emails.md`](../design/v3/emails.md) (every message), [`../design/v3/integrations.md`](../design/v3/integrations.md) §7 (wizard).

## What an administrator does

1. **Sağlayıcı**: pick a preset (`app/services/mail_presets.py`): Google Workspace / Gmail (app password, OAuth2 or the
   SMTP relay service), Microsoft 365 (OAuth2; Exchange Online turns password SMTP off by default from December 2026,
   MC786329), Amazon SES, SendGrid, Mailgun, Postmark, Brevo, Resend, Yandex 360, or a campus server. The preset fills
   host, port, TLS mode and sign-in method, and lists what to create in the provider console, with copy buttons.
2. **Bağlantı**: username and the secret. Secrets (password, OAuth2 client secret, refresh token) are Fernet-encrypted
   with `APP_SECRET`, write-only (the API answers `{set, masked}`; `null` keeps, `""` clears) and audited without their
   value. Credentials are refused over an unencrypted connection.
3. **Gönderen**: from-address, from-name, reply-to. Providers abroad (SES, SendGrid, Mailgun, Postmark, Brevo, Resend)
   need the KVKK md. 9 acknowledgement, which is stored with the administrator's name and the date (`smtp.abroad_ack`).
4. **Alan adı**: SPF / DKIM / DMARC of the from-domain over DNS (`app/services/mail_dns.py`, standard library resolver,
   IDNA for Turkish domains) with plain Turkish guidance. The step warns and never blocks.
5. **Deneme**: a themed test e-mail to any address; the answer carries an SMTP transcript excerpt (`C:` / `S:` lines;
   AUTH exchanges and the message body are never included) and a Turkish hint for the usual failures.
6. **Etkinleştir**: notifications that waited while SMTP was not set up (last 7 days) can be sent now; reset codes never.

Every value is an organisation row (`settings`, keys `smtp.*`): every administrator sees and edits the same setup;
"Son değişiklik: <ad>, <zaman>" comes from the audit log.

## OAuth2 (XOAUTH2)

* **Microsoft 365**: app registration with the application permission `Office 365 Exchange Online › SMTP.SendAsApp`,
  admin consent, `New-ServicePrincipal` + `Add-MailboxPermission` in Exchange Online PowerShell, SMTP AUTH on for the
  mailbox. Paste tenant ID, client ID and secret; the server uses the client-credentials grant
  (`https://outlook.office365.com/.default`). A stored refresh token switches to the delegated grant.
* **Google**: an OAuth client and a refresh token for the scope `https://mail.google.com/` (for example from the OAuth
  Playground with your own client).

## Messages

`app.emails.render(kind, locale, **ctx) -> (subject, html, text)` renders every message (25 kinds, Turkish and English):
table layout, inline styles, 600 px, dark-mode swaps, bulletproof button with VML for Outlook, hidden preheader, the app
tile as a CID image, `multipart/alternative` with the plain text first. The wired send paths (approvals, bookings,
KVKK, AI alerts, ops alerts, password reset, the test) keep their recipients and their plain text: the outbox body is
the bell's text and the text part starts with it. Admins override the subject and the opening text per kind and
language on the Şablonlar tab (rows of `translations`, set `email`), with a live preview at desktop and phone width
and "Test gönder". The outbox stores the button link and the reader's language (alembic `0038_email_templates`).

## Local test sink

The backend tests start an SMTP sink on `127.0.0.1:2721` (`tests/w3b_mail_sink.py`: STARTTLS with a self-signed
certificate, AUTH PLAIN / LOGIN / XOAUTH2). `e2e/w3-mail.spec.ts` starts its own plain sink on the same port.
