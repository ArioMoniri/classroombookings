/** W3-HUB gallery logic: tabs and deep links, actions and switches, search, monograms, platform presets, test result. */
import { describe, expect, it } from "vitest";
import type { ConnectorCard } from "@/lib/api/integrations";
import { attentionCards, checkUrl, countsLine, fold, galleryHref, matches, monogram, parseSetupHref, platformOfCard, primaryAction, relativeTime, switchIntent, switchState, tabOf, testResult, verifySnippet, PLATFORMS } from "./integrations-model";

function card(over: Partial<ConnectorCard> = {}): ConnectorCard {
  return {
    key: "calendar.google",
    area: "calendar",
    name_tr: "Google Takvim",
    name_en: "Google Calendar",
    summary_tr: "Rezervasyonları kullanıcıların Google Takvim'ine gönderir.",
    summary_en: "Pushes bookings to users' Google Calendar.",
    status: "not_configured",
    setup_href: "/admin/integrations?tab=calendar&setup=calendar.google",
    source: "builtin",
    ...over,
  };
}

describe("tabs and deep links", () => {
  it("defaults to Tümü and reads ?area= as well as the older ?tab=", () => {
    expect(tabOf(null)).toBe("all");
    expect(tabOf("bogus")).toBe("all");
    expect(tabOf("channels")).toBe("channels");
    expect(parseSetupHref("/admin/integrations?tab=calendar&setup=calendar.google")).toEqual({ tab: "calendar", setup: "calendar.google" });
    expect(parseSetupHref("/admin/integrations?area=email&setup=email.smtp")).toEqual({ tab: "email", setup: "email.smtp" });
    expect(parseSetupHref("/admin/ai")).toBeNull();
    expect(galleryHref("all")).toBe("/admin/integrations");
    expect(galleryHref("automation", "automation.n8n")).toBe("/admin/integrations?area=automation&setup=automation.n8n");
  });
});

describe("actions and switches", () => {
  it("offers Kur until configured, Yönet afterwards", () => {
    expect(primaryAction(card())).toBe("setup");
    expect(primaryAction(card({ status: "unknown" }))).toBe("setup");
    expect(primaryAction(card({ status: "error" }))).toBe("edit");
    expect(primaryAction(card({ status: "disabled" }))).toBe("edit");
  });

  it("asks before switching off, sends the KVKK-gated ones through the setup, toggles the rest", () => {
    const gated = card({ status: "disabled", enabled: false, toggle: { method: "PUT", path: "/calendar/admin/settings", field: "calendar_sync_enabled", enable_in_setup: true } });
    const plain = card({ status: "disabled", enabled: false, toggle: { method: "PUT", path: "/webhooks/3", field: "active", enable_in_setup: false } });
    expect(switchIntent(gated, true)).toBe("open_setup");
    expect(switchIntent(gated, false)).toBe("confirm_off");
    expect(switchIntent(plain, true)).toBe("toggle");
    expect(switchIntent(card(), true)).toBe("none");
    expect(switchState(plain)).toEqual({ checked: false, disabled: false, reason: null });
    expect(switchState(card()).disabled).toBe(true);
  });
});

describe("summary, attention, search", () => {
  it("counts per the spec's summary line and keeps the gallery order for the attention row", () => {
    expect(countsLine({ connected: 6, error: 1, not_configured: 9, disabled: 2, unknown: 1 })).toEqual({ connected: 6, error: 1, notConfigured: 9 });
    const list = [card({ key: "a", status: "error" }), card({ key: "b" }), card({ key: "c", status: "error" })];
    expect(attentionCards(list).map((c) => c.key)).toEqual(["a", "c"]);
  });

  it("searches Turkish text without caring about case or dotted / dotless i", () => {
    expect(fold("İSTANBUL Işık")).toBe("istanbul isik");
    expect(matches(card(), "takvim")).toBe(true);
    expect(matches(card(), "TAKVİM")).toBe(true);
    expect(matches(card(), "calendar")).toBe(true);
    expect(matches(card(), "slack")).toBe(false);
    expect(matches(card(), "  ")).toBe(true);
  });
});

describe("monogram and time", () => {
  it("uses text monograms, never logos", () => {
    expect(monogram(card({ key: "identity.entra", name_en: "Microsoft 365" }))).toBe("MS");
    expect(monogram(card({ key: "email.smtp", name_en: "E-mail" }))).toBe("SMTP");
    expect(monogram(card({ key: "automation.zapier", name_en: "Zapier" }))).toBe("Z");
    expect(monogram(card({ key: "identity.okta-1", name_en: "Okta" }))).toBe("OK");
  });

  it("speaks relative time in Turkish", () => {
    const now = Date.parse("2026-10-17T20:00:00Z");
    expect(relativeTime("2026-10-17T19:56:00Z", "tr-TR", now)).toBe("4 dakika önce");
    expect(relativeTime("2026-10-17T17:00:00", "tr-TR", now)).toBe("3 saat önce");
  });
});

describe("automation platforms", () => {
  it("recognises each platform's URL shape and refuses non-URLs", () => {
    expect(platformOfCard("automation.n8n")).toBe("n8n");
    expect(platformOfCard("automation.webhooks")).toBeNull();
    expect(checkUrl("https://n8n.uni.edu.tr/webhook/abc", "n8n")).toBe("ok");
    expect(checkUrl("https://hooks.zapier.com/hooks/catch/1/2/", "zapier")).toBe("ok");
    expect(checkUrl("https://eo123.m.pipedream.net", "pipedream")).toBe("ok");
    expect(checkUrl("https://cloud.activepieces.com/api/v1/webhooks/x", "activepieces")).toBe("ok");
    expect(checkUrl("https://example.org/hook", "zapier")).toBe("hint");
    expect(checkUrl("ftp://x", "n8n")).toBe("invalid");
    expect(checkUrl("not a url", "n8n")).toBe("invalid");
    expect(checkUrl("", "n8n")).toBe("empty");
  });

  it("gives a signature check that matches the backend's HMAC over timestamp.body", () => {
    for (const p of PLATFORMS) {
      const code = verifySnippet(p);
      expect(code).toContain("createHmac('sha256'");
      expect(code).toContain("ts + '.' + rawBody");
      expect(code).toContain("x-smartsched-signature");
      expect(code).toContain("timingSafeEqual");
    }
  });

  it("reads the test delivery: pending until SENT or FAILED", () => {
    expect(testResult([], null)).toBeNull();
    expect(testResult([{ id: 5, status: "PENDING" }], 5)).toEqual({ state: "pending" });
    expect(testResult([{ id: 5, status: "SENT", response_status: 204 }], 5)).toEqual({ state: "sent", http: 204 });
    expect(testResult([{ id: 5, status: "FAILED", response_status: 500, last_error: "HTTP 500" }], 5)).toEqual({ state: "failed", http: 500, error: "HTTP 500" });
  });
});
