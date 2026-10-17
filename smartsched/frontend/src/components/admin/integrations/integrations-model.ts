/**
 * Pure logic of the integrations gallery (W3-HUB, `/admin/integrations`): tabs, status tone, the card's primary
 * action and switch, setup links, and the automation-platform presets of the guided webhook setup.
 */
import { AREA_KEYS, type AreaKey, type CardStatus, type ConnectorCard } from "@/lib/api/integrations";

export const TABS: readonly AreaKey[] = AREA_KEYS;
export const INTEGRATIONS_PATH = "/admin/integrations";

export function tabOf(value: string | null | undefined): AreaKey {
  return (TABS as readonly string[]).includes(value ?? "") ? (value as AreaKey) : "identity";
}

export const TONE: Record<CardStatus, string> = {
  connected: "bg-status-feasible text-status-feasible-fg",
  error: "bg-status-infeasible text-status-infeasible-fg",
  not_configured: "bg-status-warning text-status-warning-fg",
  disabled: "bg-fill-2 text-label-2",
  unknown: "bg-fill-2 text-label-2",
};

/** Cards needing attention first (error, then not configured), the rest in the backend's order. */
const RANK: Record<CardStatus, number> = { error: 0, not_configured: 1, unknown: 2, disabled: 3, connected: 4 };
export function sortCards(cards: readonly ConnectorCard[]): ConnectorCard[] {
  return cards.map((c, i) => [c, i] as const).sort((a, b) => RANK[a[0].status] - RANK[b[0].status] || a[1] - b[1]).map(([c]) => c);
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
export function parseSetupHref(href: string): { tab: AreaKey; setup: string | null } | null {
  if (!href.startsWith(`${INTEGRATIONS_PATH}?`) && href !== INTEGRATIONS_PATH) return null;
  const q = new URLSearchParams(href.split("?")[1] ?? "");
  return { tab: tabOf(q.get("tab")), setup: q.get("setup") };
}

export function galleryHref(tab: AreaKey, setup?: string | null): string {
  return `${INTEGRATIONS_PATH}?tab=${tab}${setup ? `&setup=${encodeURIComponent(setup)}` : ""}`;
}

export function countsLine(counts: Record<string, number>): { connected: number; attention: number; total: number } {
  const n = (k: string) => counts[k] ?? 0;
  return { connected: n("connected"), attention: n("error") + n("not_configured"), total: Object.values(counts).reduce((a, b) => a + b, 0) };
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
