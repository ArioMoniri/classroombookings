# KVKK note: the helper file router's encrypted file stage (HB-23b, 2026-10-18)

Status: recorded by the HB-23b backend lane after the HB-23 KVKK/security review (approve with conditions, C2).
The KVKK officer's own sign-off is still open; this note is what they review.

## What it is

When a person drops a file on the helper ("Yardımcı"), `POST /helper/files/classify` reads its header area to say what
kind of file it is (`app/ai/helper/files.py`). If the card offers a button that carries the file to a page (İçe aktar,
Kurulum sihirbazı, Kullanıcılar › İçe aktar), the bytes are kept so the person does not upload them twice.

## How it is recorded

**Short-term encrypted storage as one step of the import processing activity.** It is *not* recorded as "transient
processing, not storage": KVKK Art. 3(1)(e) counts recording and keeping as processing, and has no exemption for
short or encrypted storage. Inventory entry: `kvkk.DATA_CLASSES["helper_file_stage"]` (`GET /admin/kvkk/inventory`).

| Item | Value |
|---|---|
| Purpose | Tell the file's type and hand it to the page the person chose; the page's own preview and "Uygula" do the import |
| Legal basis | The same as the import it belongs to: KVKK m.5/2(c), (ç), (f) |
| Data | Whatever the file holds (planning lists name instructors; user lists hold e-mails) |
| Where | `${UPLOAD_DIR}/helper-stage/<owner-tag>-<stage-id>.bin`, mode 0600, excluded from `deploy/backup.sh` |
| Protection | AES-256-GCM. The key is HKDF(token key, salt = stage id, info = HMAC(APP_SECRET, "helper-file-kek")); the token key exists only inside the person's signed `upload_token`, so neither the server alone nor a copied token alone can decrypt (crypto-shredding) |
| Bound to | The person and their sign-in session (AU-15 session row + token version); no stage without a session |
| Retention | At most 10 minutes. Deleted when the target page consumes it (once), when the person cancels (✕, "Vazgeç", sheet close), on a new drop, on sign-out, on KVKK erasure, and by the sweeper (every minute and at start-up; `deploy/purge-uploads.sh` also removes anything older than 10 minutes) |
| Recipients | None. No database row, no job, no helper history; the only audit row (`helper.file.handoff`) stores kind, page, term, extension, size and 12 characters of the SHA-256, never the file name |
| Cross-border transfer | None in v1. Classification is deterministic and calls no model |
| `HELPER_FILE_STAGE=off` | Nothing is staged; the browser sends the same File object to the target page again |

## Conditions for any future change

- The optional model tie-breaker (router spec §4.6) may only run when `ai_allowed(session, "intake")` is true (the
  council AI switch with its KVKK sign-off) **and** `gateway.transfer_ok(provider)` allows the provider, and it may
  only send the canonical column labels the detectors matched plus allow-listed sheet titles, never cell values.
- Card evidence stays name-free: canonical labels, counts, ICS dates, CRBS table names; sheet titles only when every
  word is a week / term / day / month / sheet word (`files.safe_sheet_title`).
- Starlette spools uploads larger than 1 MiB to `/tmp`; the backend container mounts `/tmp` as tmpfs
  (`deploy/docker-compose.yml`), so no plain bytes reach persistent disk.
