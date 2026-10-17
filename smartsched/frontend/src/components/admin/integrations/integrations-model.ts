/**
 * Pure logic of the integrations gallery (W3-HUB, `/admin/integrations`): tabs, status tone, the card's primary
 * action and switch, setup links, and the automation-platform presets of the guided webhook setup.
 */
import { AREA_KEYS, type AreaKey, type CardStatus, type ConnectorCard } from "@/lib/api/integrations";

/** "all" (Tümü) plus the six areas; the URL carries `?area=` (spec §3) or the older `?tab=`. */
export type HubTab = "all" | AreaKey;
export const TABS: readonly HubTab[] = ["all", ...AREA_KEYS];
export const INTEGRATIONS_PATH = "/admin/integrations";

export function tabOf(value: string | null | undefined): HubTab {
  return (TABS as readonly string[]).includes(value ?? "") ? (value as HubTab) : "all";
}

export const TONE: Record<CardStatus, string> = {
  connected: "bg-status-feasible text-status-feasible-fg",
  error: "bg-status-infeasible text-status-infeasible-fg",
  not_configured: "bg-fill-2 text-label-2",
  disabled: "bg-fill-2 text-label-2",
  unknown: "bg-fill-2 text-label-2",
};

/** Cards in error, in gallery order (the "Dikkat isteyen" row). The gallery itself never reorders (spec §3). */
export function attentionCards(cards: readonly ConnectorCard[]): ConnectorCard[] {
  return cards.filter((c) => c.status === "error");
}

/** Case- and Turkish-dotless-i-insensitive search over name, summary and detail in both languages. */
export function fold(text: string): string {
  return text.replace(/İ/g, "i").replace(/I/g, "ı").toLocaleLowerCase("tr").replace(/ı/g, "i").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}
export function matches(card: ConnectorCard, q: string): boolean {
  const needle = fold(q.trim());
  if (!needle) return true;
  return fold([card.name_tr, card.name_en, card.summary_tr, card.summary_en, card.detail_tr ?? "", card.detail_en ?? ""].join(" ")).includes(needle);
}

/** Text monogram (no third-party logos in the admin; spec §2, W3-IDP BADGES). */
const MONO: Record<string, string> = { entra: "MS", microsoft: "MS", google: "G", oidc: "OIDC", saml: "SAML", ldap: "LDAP", smtp: "SMTP", webhooks: "WH", n8n: "n8n", activepieces: "AP", pipedream: "PD", zapier: "Z", providers: "AI", webpush: "WP", telegram: "TG", whatsapp: "WA", whatsapp_web: "WA", sms: "SMS", teams: "T", slack: "S", push: "ICS", all: "•" };
export function monogram(card: Pick<ConnectorCard, "key" | "name_en">): string {
  const tail = card.key.split(".").pop() ?? "";
  const hit = MONO[tail] ?? Object.entries(MONO).find(([k]) => tail.startsWith(k))?.[1];
  if (hit) return hit;
  return (card.name_en.match(/[A-Za-z0-9]/g) ?? ["?"]).slice(0, 2).join("").toUpperCase();
}

/** "4 dk önce" (Intl.RelativeTimeFormat); the absolute time goes in the tooltip. */
export function relativeTime(iso: string, locale: string, now: number = Date.now()): string {
  const d = new Date(iso.endsWith("Z") || /[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return iso;
  const s = Math.round((d.getTime() - now) / 1000);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const a = Math.abs(s);
  if (a < 60) return rtf.format(s, "second");
  if (a < 3600) return rtf.format(Math.round(s / 60), "minute");
  if (a < 86400) return rtf.format(Math.round(s / 3600), "hour");
  if (a < 86400 * 30) return rtf.format(Math.round(s / 86400), "day");
  return d.toLocaleDateString(locale, { dateStyle: "medium" });
}

/** "Kur" for a connector that is not set up (or whose state is unknown), "Düzenle" otherwise. */
export function primaryAction(card: Pick<ConnectorCard, "status">): "setup" | "edit" {
  return card.status === "not_configured" || card.status === "unknown" ? "setup" : "edit";
}

export interface SwitchState {
  checked: boolean;
  disabled: boolean;
  /** why it cannot be used (i18n key suffix under integrations.switch.*) */
  reason: "notConfigured" | "noSwitch" | null;
}
export function switchState(card: Pick<ConnectorCard, "toggle" | "enabled" | "status">): SwitchState {
  if (!card.toggle) return { checked: card.status === "connected", disabled: true, reason: card.status === "not_configured" || card.status === "unknown" ? "notConfigured" : "noSwitch" };
  return { checked: Boolean(card.enabled), disabled: false, reason: null };
}

/** What flipping the switch does: switching off asks first (it is the whole organisation's setting); switching
 *  on goes through the guided setup when the area needs it (a KVKK sign-off, a risk acknowledgement). */
export function switchIntent(card: Pick<ConnectorCard, "toggle">, next: boolean): "toggle" | "confirm_off" | "open_setup" | "none" {
  if (!card.toggle) return "none";
  if (!next) return "confirm_off";
  return card.toggle.enable_in_setup ? "open_setup" : "toggle";
}

/** A setup link inside the gallery opens the sheet in place; anything else (e.g. `/admin/ai`) is navigated to. */
export function parseSetupHref(href: string): { tab: HubTab; setup: string | null } | null {
  if (!href.startsWith(`${INTEGRATIONS_PATH}?`) && href !== INTEGRATIONS_PATH) return null;
  const q = new URLSearchParams(href.split("?")[1] ?? "");
  return { tab: tabOf(q.get("area") ?? q.get("tab")), setup: q.get("setup") };
}

export function galleryHref(tab: HubTab, setup?: string | null): string {
  const params = new URLSearchParams();
  if (tab !== "all") params.set("area", tab);
  if (setup) params.set("setup", setup);
  const q = params.toString();
  return q ? `${INTEGRATIONS_PATH}?${q}` : INTEGRATIONS_PATH;
}

/** The summary line's numbers (spec §8 `integrations.summary`). */
export function countsLine(counts: Record<string, number>): { connected: number; error: number; notConfigured: number } {
  const n = (k: string) => counts[k] ?? 0;
  return { connected: n("connected"), error: n("error"), notConfigured: n("not_configured") };
}

/* ------------------------------------------------------------------------------- automation platforms */

export const PLATFORMS = ["n8n", "activepieces", "pipedream", "zapier"] as const;
export type Platform = (typeof PLATFORMS)[number];

export interface PlatformPreset {
  id: Platform;
  name: string;
  /** the URL shape the platform gives (placeholder of the paste-in field) */
  example: string;
  /** whether a pasted URL looks like this platform's (only a hint; any https URL is accepted) */
  looksRight: (url: URL) => boolean;
  docs: string;
}

export const PRESETS: Record<Platform, PlatformPreset> = {
  n8n: {
    id: "n8n",
    name: "n8n",
    example: "https://n8n.kurum.edu.tr/webhook/…",
    looksRight: (u) => u.hostname.includes("n8n") || u.pathname.startsWith("/webhook/") || u.pathname.startsWith("/webhook-test/"),
    docs: "https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/",
  },
  activepieces: {
    id: "activepieces",
    name: "Activepieces",
    example: "https://cloud.activepieces.com/api/v1/webhooks/…",
    looksRight: (u) => u.hostname.includes("activepieces") || u.pathname.includes("/api/v1/webhooks/"),
    docs: "https://www.activepieces.com/docs/pieces/triggers/webhook",
  },
  pipedream: {
    id: "pipedream",
    name: "Pipedream",
    example: "https://eo…m.pipedream.net",
    looksRight: (u) => u.hostname.endsWith("pipedream.net") || u.hostname.endsWith("pipedream.com"),
    docs: "https://pipedream.com/docs/workflows/building-workflows/triggers/#http",
  },
  zapier: {
    id: "zapier",
    name: "Zapier",
    example: "https://hooks.zapier.com/hooks/catch/…",
    looksRight: (u) => u.hostname.endsWith("zapier.com"),
    docs: "https://help.zapier.com/hc/en-us/articles/8496288690317",
  },
};

export function platformOfCard(key: string): Platform | null {
  const id = key.startsWith("automation.") ? key.slice("automation.".length) : "";
  return (PLATFORMS as readonly string[]).includes(id) ? (id as Platform) : null;
}

/** The pasted URL: "ok", "hint" (valid https but not this platform's shape), or "invalid". */
export function checkUrl(value: string, platform: Platform): "ok" | "hint" | "invalid" | "empty" {
  const v = value.trim();
  if (!v) return "empty";
  let u: URL;
  try {
    u = new URL(v);
  } catch {
    return "invalid";
  }
  if (u.protocol !== "https:" && u.protocol !== "http:") return "invalid";
  return PRESETS[platform].looksRight(u) ? "ok" : "hint";
}

export const SIGNATURE_HEADERS = ["X-SmartSched-Signature", "X-SmartSched-Timestamp", "X-SmartSched-Event", "X-SmartSched-Event-Id"] as const;

/** Signature check to paste into the platform's code step: HMAC-SHA256 over `<timestamp>.<raw body>`,
 *  `sha256=<hex>` in X-SmartSched-Signature (app/services/webhooks.py `sign`), 5-minute tolerance. */
export function verifySnippet(platform: Platform): string {
  const core = [
    "const crypto = require('crypto');",
    "const secret = SMARTSCHED_SECRET; // whsec_…",
    "const ts = headers['x-smartsched-timestamp'];",
    "const sig = headers['x-smartsched-signature'];",
    "const mac = 'sha256=' + crypto.createHmac('sha256', secret).update(ts + '.' + rawBody).digest('hex');",
    "const fresh = Math.abs(Date.now() / 1000 - Number(ts)) < 300;",
    "if (!fresh || !crypto.timingSafeEqual(Buffer.from(mac), Buffer.from(sig))) throw new Error('bad signature');",
  ];
  switch (platform) {
    case "n8n":
      // Webhook node: "Raw Body" on; Code node (JavaScript) right after it
      return ["// n8n › Code (JavaScript) after the Webhook node (“Raw Body” on)", "const { headers } = $input.first().json;", "const rawBody = Buffer.from($input.first().binary.data.data, 'base64').toString('utf8');", "const SMARTSCHED_SECRET = $env.SMARTSCHED_SECRET;", ...core, "return $input.all();"].join("\n");
    case "pipedream":
      return ["// Pipedream › Node.js step (HTTP trigger: “Raw body” on)", "export default defineComponent({", "  async run({ steps }) {", "    const { headers } = steps.trigger.event;", "    const rawBody = steps.trigger.event.body_raw ?? JSON.stringify(steps.trigger.event.body);", "    const SMARTSCHED_SECRET = process.env.SMARTSCHED_SECRET;", ...core.map((l) => `    ${l.replace("const crypto = require('crypto');", "const crypto = await import('crypto');")}`), "  },", "});"].join("\n");
    case "activepieces":
      return ["// Activepieces › Code step: inputs headers, rawBody (Catch Webhook › Raw body), secret", "export const code = async (inputs) => {", "  const { headers, rawBody } = inputs;", "  const SMARTSCHED_SECRET = inputs.secret;", ...core.map((l) => `  ${l}`), "  return true;", "};"].join("\n");
    case "zapier":
      return ["// Zapier › Code by Zapier (JavaScript): inputData.ts, inputData.sig, inputData.raw (Catch Raw Hook)", "const headers = { 'x-smartsched-timestamp': inputData.ts, 'x-smartsched-signature': inputData.sig };", "const rawBody = inputData.raw;", "const SMARTSCHED_SECRET = inputData.secret;", ...core, "output = { verified: true };"].join("\n");
  }
}

/** The newest finished test delivery (SENT / FAILED), or null while it is still pending. */
export function testResult(deliveries: readonly { id: number; status: string; response_status?: number | null; last_error?: string | null }[], deliveryId: number | null) {
  if (deliveryId === null) return null;
  const d = deliveries.find((x) => x.id === deliveryId);
  if (!d || (d.status !== "SENT" && d.status !== "FAILED")) return { state: "pending" as const };
  return d.status === "SENT" ? { state: "sent" as const, http: d.response_status ?? null } : { state: "failed" as const, http: d.response_status ?? null, error: d.last_error ?? null };
}
