/**
 * HX-17 (API.md HB-D §1): "Bunu hatırla". The server decides (app/ai/helper/remember.py `detect`, 0 model calls) and
 * answers the `remember_note` confirm card; the client sends the typed text to `POST /helper/turn` as it is and never
 * calls `POST /helper/notes` for it. {@link rememberText} mirrors the server's rule only so that Rehber modu (no
 * composer) can offer the one "Bunu hatırla: …" row. `remember_note` is not a registry action (it is not in
 * `GET /helper/actions`), so its label comes from {@link clientActionLabel}.
 */
import { translate, type Locale, type MessageKey } from "@/lib/i18n";

const TR = String.raw`(?:(?:bunu|şunu|sunu)\s+)?(?:hat[ıi]rla|akl[ıi]nda\s+tut)\s*[:\-–—]`;
const EN = String.raw`remember(?:\s+this)?\s*[:\-–—]|remember\s+that\b`;
const ASK = new RegExp(String.raw`^\s*(?:${TR}|${EN})\s*([\s\S]*)$`, "iu");

/** The person's own words after "bunu hatırla:" at the start ("" when nothing follows), or null (a question too). */
export function rememberText(text: string): string | null {
  const raw = text ?? "";
  // "İ" / "I" as Turkish capitals first (same length, so the positions stay), like the server
  const folded = raw.replace(/İ/g, "i").replace(/I/g, "ı");
  const m = ASK.exec(folded) ?? ASK.exec(raw);
  if (!m) return null;
  const note = raw
    .slice(m[0].length - (m[1] ?? "").length)
    .split(/\s+/)
    .filter(Boolean)
    .join(" ");
  if (note && /\?\s*$/.test(note)) return null;
  return note;
}

/** Labels of the actions that are not in `GET /helper/actions` (the server words the rest). */
const CLIENT_LABELS: Readonly<Record<string, MessageKey>> = { remember_note: "helper.action.remember_note" };

export const clientActionLabel =
  (locale: Locale) =>
  (action: string): string | null => {
    const key = CLIENT_LABELS[action];
    return key ? translate(locale, key) : null;
  };
