/**
 * HX-06 hand-over prefills (helper.md §4.3, ROADMAP HX-06): the helper never writes for these; it opens the page's
 * own sheet or field with values in the address, and the person's click on the page's own button does the write.
 *
 * - `/runs/<id>?publish=1` (or `/runs?publish=<id>`, which forwards there): the run's publish dialog;
 * - `/admin/users?invite=1&email=&name=&role=&department=`: the invite sheet (or "Yeni kullanıcı" without Microsoft);
 * - `/profile?calendar=1`: the "Takvimime ekle" sheet (CAL-F, calendar-export-section.tsx);
 * - `/runs/<id>?chat=<text>`: the run chat's composer, prefilled, not sent.
 *
 * Values are plain text with bounded length; nothing from the address is rendered as HTML or used as a URL.
 */

/** Control and bidi-override characters (never useful in a prefill, and a spoofing vector). */
// eslint-disable-next-line no-control-regex
const CONTROL = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F‎‏‪-‮⁦-⁩]/g;

function plain(value: string | null, max: number): string {
  return (value ?? "").replace(CONTROL, "").replace(/\s+/g, " ").trim().slice(0, max);
}

/** `?publish=1` or `?publish=<this run's id>`. */
export function publishRequested(params: URLSearchParams, runId: number): boolean {
  const v = params.get("publish");
  return v === "1" || v === String(runId);
}

/** The `/runs?publish=<id>` forward target, or null. */
export function publishForward(params: URLSearchParams): string | null {
  const v = params.get("publish") ?? "";
  return /^\d{1,9}$/.test(v) && Number(v) > 0 ? `/runs/${Number(v)}?publish=1` : null;
}

/** `?chat=<text>`: the run chat composer's draft (≤ 500 characters), or null. */
export function chatPrefill(params: URLSearchParams): string | null {
  const text = plain(params.get("chat"), 500);
  return text || null;
}

export interface InvitePrefill {
  email: string;
  name: string;
  /** a role code ("TEACHER") or id ("3", "id:3"); mapped onto the form's options by {@link roleValueFor} */
  role: string;
  /** a department id */
  department: string;
}

/** `?invite=1&email=&name=&role=&department=` → the invite fields (invalid values become ""), or null. */
export function invitePrefill(params: URLSearchParams): InvitePrefill | null {
  if (params.get("invite") !== "1") return null;
  const email = plain(params.get("email"), 254);
  const role = plain(params.get("role"), 40);
  const department = plain(params.get("department"), 9);
  return {
    email: /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ? email : "",
    name: plain(params.get("name"), 120),
    role: /^(id:)?[A-Za-z0-9_]+$/.test(role) ? role : "",
    department: /^\d+$/.test(department) ? department : "",
  };
}

const SEEDED_CODES = ["ADMIN", "PLANNER", "VIEWER", "TEACHER"];

/** A role code or id → the role field's option value (`id:<n>`, or `code:<CODE>` without the role list); "" = none. */
export function roleValueFor(role: string, roles: readonly { id: number; code?: string | null }[] | undefined): string {
  const r = role.trim();
  if (!r) return "";
  const id = /^(?:id:)?(\d+)$/.exec(r)?.[1];
  if (roles) {
    const hit = id ? roles.find((x) => String(x.id) === id) : roles.find((x) => (x.code ?? "").toLocaleUpperCase("en") === r.toLocaleUpperCase("en"));
    return hit ? `id:${hit.id}` : "";
  }
  const code = r.toLocaleUpperCase("en");
  return !id && SEEDED_CODES.includes(code) ? `code:${code}` : "";
}
