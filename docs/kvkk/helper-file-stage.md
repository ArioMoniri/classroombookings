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

## Proposed privacy notice paragraph (aydınlatma metni, for the next published version; HB-23c, 2026-10-18)

Privacy notices are versioned rows an administrator publishes (`POST /kvkk/notices`); none is in the repository. After
the deploy, publish version n+1 with this paragraph (Turkish and English notices), so every user acknowledges it again.
The wording matches the helper's own lines (`helper.file.privacy`, `helper.file.privacyMany`).

**TR**

> **Yardımcıya bıraktığınız dosyalar.** Yardımcıya bir dosya bıraktığınızda, eklediğinizde ya da yapıştırdığınızda dosya
> yalnızca türünü anlamak (planlama listesi, sınav listesi, haftalık derslik takvimi vb.) ve sizi doğru sayfaya
> yönlendirmek için okunur. Okuma kurumun kendi sunucusunda yapılır; yapay zekâ modeline ya da yurt dışına
> gönderilmez. Dosya, açılan sayfada Önizle'ye basabilmeniz için en çok 10 dakika şifreli olarak tutulur; şifre
> anahtarı yalnızca sizin tarayıcınızdadır. Dosya kullanıldığında, vazgeçtiğinizde, oturumu kapattığınızda ya da 10
> dakika dolduğunda silinir. Siz Önizle'ye ve ardından Uygula'ya basana kadar hiçbir veri kaydedilmez. Düğmeye
> bastığınızda yalnızca dosyanın türü, uzantısı, boyutu ve açılan sayfa kayıt altına alınır; dosyanın adı ve içeriği
> kaydedilmez. Birden çok dosya bıraktığınızda dosyalar cihazınızda kalır ve Kurulum sihirbazında Başlat'a basana
> kadar hiçbir yere gönderilmez. Hukuki sebep: KVKK m.5/2(f) (yalnızca sizin başlattığınız içe aktarmayı
> kolaylaştırmak).

**EN**

> **Files you give the helper.** When you drop, attach or paste a file into the helper, it is only read to find out
> what it is (planning list, exam list, weekly room timetable and so on) and to take you to the right page. It is
> read on the institution's own server; it is not sent to an AI model or abroad. The file is kept encrypted for at
> most 10 minutes so that you can press Preview on the page that opens; the key is held only by your browser. It is
> deleted when it is used, when you cancel, when you sign out, or after 10 minutes. Nothing is saved until you press
> Preview and then Apply. When you press the button, only the file's type, extension and size and the page it opens
> are recorded; the file's name and contents are not. When you drop several files, they stay on your device and
> nothing is sent until you press Start in the setup wizard. Legal basis: KVKK Art. 5(2)(f) (making the import you
> started easier).
