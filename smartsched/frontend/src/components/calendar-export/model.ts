/**
 * The "Takvimime ekle" sheet model (CAL-08, research doc §3.7): pure functions over `GET /calendar/export/options`
 * and `GET /calendar/subscriptions`, so the 3-tap flow (what → how → approve) is testable without React.
 */
import { withSuffix } from "@/lib/i18n/turkish";
import { googleSubscribeUrl, outlookSubscribeUrl, webcalUrl } from "@/components/bookings/reserve-model";
import { PROVIDERS, REASONS, SCOPE_KINDS, type ExportOptions, type FieldKey, type Provider, type PushChannel, type Reason, type SampleEvent, type ScopeKind, type ScopeOption, type Subscription, type SubscriptionUrls } from "@/lib/api/calendar-export";

export type Step = "what" | "how" | "approve" | "done";
export const STEPS: readonly Step[] = ["what", "how", "approve", "done"];
export const TZ = "Europe/Istanbul";

/** One tappable card on step 1: a scope, for department scopes one card per department. */
export interface ScopeChoice {
  key: string;
  kind: ScopeKind;
  departmentId: number | null;
  departmentName: string | null;
  available: boolean;
  /** a code with its own sentence (`calendarExport.reason.*`), else null */
  reason: Reason | "other" | null;
  /** the backend's own sentence for an unknown code, in the reader's language */
  reasonText: string | null;
  upcoming: number | null;
  hours: number | null;
  sample: SampleEvent | null;
  fields: string[] | null;
}

const isScope = (k: string): k is ScopeKind => (SCOPE_KINDS as readonly string[]).includes(k);
const isReason = (r: string): r is Reason => (REASONS as readonly string[]).includes(r);

function reasonOf(available: boolean, code: string | null | undefined, text: { tr?: string | null; en?: string | null }, locale: string): Pick<ScopeChoice, "reason" | "reasonText"> {
  if (available) return { reason: null, reasonText: null };
  if (code && isReason(code)) return { reason: code, reasonText: null };
  const own = (locale === "tr" ? text.tr : text.en) ?? text.en ?? text.tr ?? null;
  return { reason: "other", reasonText: own };
}

/** Step 1 cards in the doc's order (Derslerim, Bölümümün dersleri, Rezervasyonlarım); unknown kinds are dropped. */
export function scopeChoices(options: ExportOptions | undefined, locale: string): ScopeChoice[] {
  if (!options) return [];
  const out: ScopeChoice[] = [];
  const byKind = new Map(options.scopes.filter((x) => isScope(x.kind)).map((x) => [x.kind as ScopeKind, x]));
  for (const kind of SCOPE_KINDS) {
    const sc = byKind.get(kind);
    if (!sc) continue;
    if (kind === "department_classes" && sc.departments.length) {
      for (const d of sc.departments) {
        const available = sc.available !== false && d.available;
        out.push({
          key: `${kind}:${d.id}`,
          kind,
          departmentId: d.id,
          departmentName: d.name,
          available,
          ...reasonOf(available, d.reason ?? sc.reason, { tr: sc.reason_tr, en: sc.reason_en }, locale),
          upcoming: d.upcoming ?? null,
          hours: null,
          sample: d.sample ?? sc.sample ?? null,
          fields: sc.fields ?? null,
        });
      }
      continue;
    }
    out.push(single(kind, sc, locale));
  }
  return out;
}

function single(kind: ScopeKind, sc: ScopeOption, locale: string): ScopeChoice {
  return {
    key: kind,
    kind,
    departmentId: null,
    departmentName: null,
    available: sc.available,
    ...reasonOf(sc.available, sc.reason, { tr: sc.reason_tr, en: sc.reason_en }, locale),
    upcoming: sc.upcoming ?? null,
    hours: sc.hours ?? null,
    sample: sc.sample ?? null,
    fields: sc.fields ?? null,
  };
}

/** Not linked to an instructor record: Derslerim is closed for that reason (or the options say `linked: false`). */
export function notLinked(options: ExportOptions | undefined): boolean {
  if (!options) return false;
  if (options.linked === false) return true;
  const mine = options.scopes.find((x) => x.kind === "my_classes");
  return !!mine && !mine.available && mine.reason === "not_linked";
}

export type Channel = { kind: "push"; provider: Provider; connected: boolean; account: string | null; legacy: boolean } | { kind: "link" } | { kind: "file" };

/** The person's push connections: the options' own flags, overlaid by `GET /calendar/subscriptions` `push`. */
export function pushAccounts(options: ExportOptions | undefined, connections: PushChannel[] | undefined): PushChannel[] {
  const by = new Map<string, PushChannel>();
  for (const p of options?.channels.push ?? []) by.set(p.provider, p);
  for (const c of connections ?? []) by.set(c.provider, { ...by.get(c.provider), ...c, configured: by.get(c.provider)?.configured ?? c.configured });
  return [...by.values()];
}

/** Step 2: only the configured channels, push first ("Önerilen"), never a fake button. */
export function channelChoices(options: ExportOptions | undefined, connections?: PushChannel[]): Channel[] {
  if (!options) return [];
  const out: Channel[] = [];
  for (const p of pushAccounts(options, connections)) {
    if (!p.configured || !(PROVIDERS as readonly string[]).includes(p.provider)) continue;
    out.push({ kind: "push", provider: p.provider as Provider, connected: p.connected && p.status !== "REAUTH", account: p.account_email ?? null, legacy: !!p.legacy_scope });
  }
  if (options.channels.link) out.push({ kind: "link" });
  if (options.channels.file) out.push({ kind: "file" });
  return out;
}

export const channelKey = (c: Channel): string => (c.kind === "push" ? `push:${c.provider}` : c.kind);

/** The research doc's bullets, in its order; the backend's list for the scope wins when it sends one. */
export function approvalFields(choice: Pick<ScopeChoice, "kind" | "fields">, adminFields?: Record<string, boolean> | null): FieldKey[] {
  const known = new Set<string>(["code", "title", "room", "time", "department", "co_instructors", "link", "booking_title"]);
  if (choice.fields?.length) return choice.fields.filter((f): f is FieldKey => known.has(f));
  if (choice.kind === "my_bookings") return ["booking_title", "room", "time"];
  const on = (k: string, dflt: boolean) => (adminFields && k in adminFields ? !!adminFields[k] : dflt);
  const out: FieldKey[] = ["code"];
  if (on("title", false)) out.push("title");
  out.push("room", "time");
  if (on("department", true)) out.push("department");
  if (on("co_instructors", false)) out.push("co_instructors");
  if (on("link", false)) out.push("link");
  return out;
}

/** Backend timestamps are UTC, sometimes without the `Z`. */
export function parseUtc(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

const intlTag = (locale: string) => (locale === "tr" ? "tr-TR" : "en-GB");

/** "14:05" in Istanbul time. */
export function clock(d: Date, locale: string): string {
  return d.toLocaleTimeString(intlTag(locale), { timeZone: TZ, hour: "2-digit", minute: "2-digit", hour12: false });
}

function dayKey(d: Date): string {
  return d.toLocaleDateString("en-CA", { timeZone: TZ });
}

/** A sample event as one line: "PSY 262 · Şube 1 — A 308 — Pzt 13:30–15:50". */
export function sampleParts(sample: SampleEvent, locale: string, sectionWord: string): { what: string; where: string | null; when: string } {
  // the backend's own line wins ("PSY 262 · Şube 1 — A 308 — Pzt 13:30–15:50", built in Istanbul time)
  const own = locale === "tr" ? (sample.text_tr ?? sample.text_en) : (sample.text_en ?? sample.text_tr);
  if (own) {
    const parts = own.split(" — ");
    if (parts.length >= 3) return { what: parts.slice(0, -2).join(" — "), where: parts.at(-2) ?? null, when: parts.at(-1) ?? "" };
  }
  const code = sample.course_code ?? null;
  const what = code ? [code, sample.section ? `${sectionWord} ${sample.section}` : null].filter(Boolean).join(" · ") : (sample.summary ?? sample.title ?? "");
  const start = new Date(sample.starts_at);
  const end = new Date(sample.ends_at);
  const day = Number.isNaN(start.getTime()) ? "" : start.toLocaleDateString(intlTag(locale), { timeZone: TZ, weekday: "short" });
  const times = Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) ? "" : `${clock(start, locale)}–${clock(end, locale)}`;
  return { what, where: sample.location ?? null, when: [day, times].filter(Boolean).join(" ") };
}

export function sampleLine(sample: SampleEvent, locale: string, sectionWord: string): string {
  const p = sampleParts(sample, locale, sectionWord);
  return [p.what, p.where, p.when].filter(Boolean).join(" — ");
}

/**
 * "bugün 14:05" / "dün 09:10" / "12 Eki 14:05" (Istanbul time); `at` is the bare time with the Turkish locative
 * suffix for "Takviminiz en son 13:10'da çekti".
 */
export function relativeWhen(iso: string | null | undefined, locale: string, words: { today: string; yesterday: string }, now: Date = new Date()): { label: string; at: string } | null {
  const d = parseUtc(iso);
  if (!d) return null;
  const time = clock(d, locale);
  const today = dayKey(now);
  const yest = dayKey(new Date(now.getTime() - 86_400_000));
  const k = dayKey(d);
  const date = k === today ? words.today : k === yest ? words.yesterday : d.toLocaleDateString(intlTag(locale), { timeZone: TZ, day: "numeric", month: "short" });
  const label = `${date} ${time}`;
  const at = locale === "tr" ? (k === today ? withSuffix(time, "loc") : `${date} ${withSuffix(time, "loc")}`) : k === today ? `at ${time}` : `${date} at ${time}`;
  return { label, at };
}

/** The subscribe deep links; the backend's own wins, else built from the https link. */
export function subscribeLinks(urls: SubscriptionUrls, name: string): { https: string; webcal: string; google: string; outlook: string } {
  return {
    https: urls.https,
    webcal: urls.webcal || webcalUrl(urls.https),
    google: urls.google || googleSubscribeUrl(urls.https),
    outlook: urls.outlook || outlookSubscribeUrl(urls.https, name, true),
  };
}

/** Push progress "{n}/{m}" from the push row of the scope; without counts it is done once the account synced after
 * the approval (`since`, ms), else null (indeterminate). */
export function pushProgress(sub: Subscription | undefined, since?: number): { n: number; m: number; done: boolean } | null {
  if (!sub) return null;
  const pending = sub.pending_jobs ?? 0;
  if (typeof sub.total === "number" && typeof sub.synced === "number" && sub.total > 0) return { n: Math.min(sub.synced, sub.total), m: sub.total, done: sub.synced >= sub.total && pending === 0 };
  const at = parseUtc(sub.last_synced_at);
  if (!at || pending > 0) return null;
  return since === undefined || at.getTime() >= since - 5_000 ? { n: 0, m: 0, done: true } : null;
}

/** The push row (provider × scope) the approval just created, to follow its progress. */
export function findPushRow(subs: Subscription[] | undefined, provider: string, kind: ScopeKind, departmentId: number | null): Subscription | undefined {
  return subs?.find((x) => x.channel === "push" && x.provider === provider && x.scope_kind === kind && (kind !== "department_classes" || (x.scope_id ?? null) === departmentId));
}

/** The manage list: links and push rows, grouped by provider account for the disconnect action. */
export function manageRows(subs: Subscription[] | undefined): Subscription[] {
  if (!subs) return [];
  const order = (x: Subscription) => (SCOPE_KINDS as readonly string[]).indexOf(x.scope_kind);
  return [...subs].sort((a, b) => order(a) - order(b) || (a.channel === b.channel ? 0 : a.channel === "push" ? -1 : 1) || String(a.id).localeCompare(String(b.id)));
}

/** After a row is removed: the next row's id, else the previous one's, else null (focus the "Takvimime ekle" button). */
export function nextFocus(rows: Subscription[], removedId: Subscription["id"]): Subscription["id"] | null {
  const i = rows.findIndex((r) => r.id === removedId);
  if (i < 0) return rows[0]?.id ?? null;
  return rows[i + 1]?.id ?? rows[i - 1]?.id ?? null;
}

/** Push connections that need "Daha az izinle yeniden bağlan" (an old, broad Google grant). */
export function legacyProviders(options: ExportOptions | undefined, subs: Subscription[] | undefined): Set<string> {
  const out = new Set<string>();
  for (const p of options?.channels.push ?? []) if (p.connected && p.legacy_scope) out.add(p.provider);
  for (const x of subs ?? []) if (x.channel === "push" && x.legacy_scope && x.provider) out.add(x.provider);
  return out;
}

/** Where the provider's OAuth round trip comes back to, and the scope it was started for. */
export const RETURN_PATH = "/profile";
export const PENDING_KEY = "smartsched.calendarExport.pending";
export interface PendingPush {
  provider: Provider;
  kind: ScopeKind;
  departmentId: number | null;
  at: number;
}

export function readPending(raw: string | null, now = Date.now()): PendingPush | null {
  if (!raw) return null;
  try {
    const p = JSON.parse(raw) as Partial<PendingPush>;
    if (!p || !(PROVIDERS as readonly string[]).includes(String(p.provider)) || !isScope(String(p.kind))) return null;
    // a round trip older than 30 minutes is stale (the user left the provider's page)
    if (typeof p.at !== "number" || now - p.at > 30 * 60_000) return null;
    return { provider: p.provider as Provider, kind: p.kind as ScopeKind, departmentId: typeof p.departmentId === "number" ? p.departmentId : null, at: p.at };
  } catch {
    return null;
  }
}

/** The scope string the push endpoints take: `my_classes`, `department_classes:12`, `my_bookings`. */
export function pushScope(kind: ScopeKind, departmentId: number | null): string {
  return kind === "department_classes" && departmentId !== null ? `${kind}:${departmentId}` : kind;
}

/** The fallback file name ("derslerim-2026-bahar.ics"). */
export function fileName(kind: ScopeKind, termSlug: string | null | undefined, departmentName?: string | null): string {
  const base = kind === "my_classes" ? "derslerim" : kind === "my_bookings" ? "rezervasyonlarim" : `bolum-${slug(departmentName ?? "dersleri")}`;
  return `${[base, termSlug ? slug(termSlug) : null].filter(Boolean).join("-")}.ics`;
}

function slug(text: string): string {
  const map: Record<string, string> = { ç: "c", ğ: "g", ı: "i", İ: "i", ö: "o", ş: "s", ü: "u", Ç: "c", Ğ: "g", Ö: "o", Ş: "s", Ü: "u" };
  return text
    .replace(/[çğıİöşüÇĞÖŞÜ]/g, (c) => map[c] ?? c)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}
