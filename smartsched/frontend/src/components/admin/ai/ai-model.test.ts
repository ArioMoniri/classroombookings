import { describe, expect, it } from "vitest";
import { HttpError } from "@/lib/api/client";
import type { Provider, UsageRow } from "@/lib/api/ai-admin";
import {
  activeSeries,
  compactTokens,
  dailyLegend,
  dayChartData,
  foldOther,
  foldWeeks,
  lastIsToday,
  errorMessage,
  meterFill,
  meterState,
  parseLimit,
  pctOf,
  pctText,
  providerStatus,
  reasonOf,
  resetDate,
  routeIssues,
  routesBody,
  sortUsers,
  userPct,
} from "./ai-model";

function provider(over: Partial<Provider> = {}): Provider {
  return {
    id: "openai_compatible",
    label_tr: "OpenAI uyumlu",
    label_en: "OpenAI-compatible",
    secrets: ["api_key"],
    config: { enabled: true },
    config_fields: ["base_url"],
    keyless: true,
    default_base_url: null,
    keys: {},
    has_credentials: true,
    usable: true,
    models: [{ id: "llama3.1" }, { id: "qwen3" }],
    fetched_at: "2026-10-17T18:40:00",
    sync_error: null,
    allow_local: false,
    warnings: [],
    last_test: {},
    transfer: {},
    transfer_ok: true,
    local: true,
    ...over,
  };
}

describe("numbers", () => {
  it("formats tokens compactly per locale and percentages Turkish-first", () => {
    expect(compactTokens(2_410_000, "tr")).toMatch(/2,41/);
    expect(compactTokens(2_410_000, "en")).toMatch(/2\.41/);
    expect(pctText(84, "tr")).toBe("%84");
    expect(pctText(84, "en")).toBe("84%");
    expect(pctText(null, "tr")).toBe("");
    expect(pctOf(50, 0)).toBeNull();
    expect(pctOf(1, 3)).toBe(33.3);
  });

  it("parses limit fields (empty = no limit, invalid = null)", () => {
    expect(parseLimit("")).toBe(0);
    expect(parseLimit("400.000")).toBe(400000);
    expect(parseLimit("-3")).toBeNull();
    expect(parseLimit("abc")).toBeNull();
  });
});

describe("meters", () => {
  it("maps a percentage to a state and fill", () => {
    expect(meterState(null, 80)).toBe("none");
    expect(meterState(40, 80)).toBe("ok");
    expect(meterState(80, 80)).toBe("near");
    expect(meterState(100, 80)).toBe("at");
    expect(meterFill("at")).toContain("infeasible");
    expect(meterFill("near")).toContain("warning");
  });

  it("names the reset day in Istanbul time", () => {
    // 2026-10-31 22:30 UTC is 1 November 01:30 in Istanbul: the daily limit resets on 2 November
    const late = new Date(Date.UTC(2026, 9, 31, 22, 30));
    expect(resetDate("day", "en", late)).toMatch(/2 November/);
    expect(resetDate("month", "tr", new Date(Date.UTC(2026, 9, 17)))).toMatch(/1 Kasım/);
  });
});

describe("providers and routes", () => {
  it("derives a provider's status", () => {
    expect(providerStatus(provider({ has_credentials: false }))).toBe("noKey");
    expect(providerStatus(provider({ config: { enabled: false } }))).toBe("disabled");
    expect(providerStatus(provider({ last_test: { ok: false, detail: "401" } }))).toBe("error");
    expect(providerStatus(provider({ sync_error: "x" }))).toBe("error");
    expect(providerStatus(provider({ last_test: { ok: true } }))).toBe("ok");
    expect(providerStatus(provider())).toBe("untested");
  });

  it("checks a route draft against synced models, fallbacks and the transfer record", () => {
    const ps = [provider(), provider({ id: "openai", usable: false, transfer_ok: false, models: [{ id: "gpt-5" }] })];
    expect(routeIssues({ provider: "openai_compatible", model: "llama3.1" }, ps, "chat")).toEqual([]);
    expect(routeIssues({ provider: "openai_compatible", model: "gpt-x" }, ps)).toEqual(["modelNotSynced"]);
    expect(routeIssues({ provider: "openai", model: "gpt-5" }, ps, "intake")).toEqual(["providerUnusable", "transferMissing"]);
    expect(routeIssues({ provider: "openai_compatible", model: "llama3.1", fallback_provider: "openai_compatible", fallback_model: "llama3.1" }, ps)).toEqual(["fallbackSame"]);
    expect(routeIssues({ provider: "openai_compatible", model: "llama3.1", fallback_model: "qwen3" }, ps)).toEqual(["fallbackIncomplete"]);
    expect(routeIssues(null, ps)).toEqual([]);
  });

  it("builds the PUT body: empty fields dropped, unset features follow the default", () => {
    const body = routesBody(
      { provider: "anthropic", model: "claude-opus-5-5", effort: "", temperature: null },
      { chat: { provider: "openai_compatible", model: "llama3.1", effort: "low" }, rules: null, intake: { provider: "", model: "" } },
    );
    expect(body).toEqual({
      default: { provider: "anthropic", model: "claude-opus-5-5" },
      features: { chat: { provider: "openai_compatible", model: "llama3.1", effort: "low" } },
    });
  });
});

describe("usage", () => {
  const rows: UsageRow[] = [
    { key: "2026-10-16", calls: 2, tokens: 300, cost_usd: 0, refused: 0, features: { chat: 200, guard: 100 } },
    { key: "2026-10-17", calls: 1, tokens: 50, cost_usd: 0, refused: 1, features: { rules: 50 } },
  ];

  it("stacks days by feature in the fixed order; up to five features keep their own series (F-CH-4)", () => {
    const pts = dayChartData(rows, "tr");
    expect(pts[0]).toMatchObject({ day: "2026-10-16", chat: 200, guard: 100, rules: 0, other: 0, total: 300 });
    expect(pts[0]!.label).toMatch(/16 Eki/);
    expect(activeSeries(pts)).toEqual(["chat", "rules", "guard"]);
    expect(dayChartData(rows, "en", 1)).toHaveLength(1);
  });

  it("F-CH-4: the five busiest features are named, the rest fold into Diğer (charts.md §4 row 1)", () => {
    const seven: UsageRow[] = [
      { key: "2026-10-16", calls: 1, tokens: 0, cost_usd: 0, refused: 0, features: { chat: 900, rules: 800, explain: 700, booking_nl: 600, voice_stt: 500, guard: 20, intake: 10 } },
      { key: "2026-10-17", calls: 1, tokens: 0, cost_usd: 0, refused: 0, features: { chat: 1 } },
    ];
    const pts = dayChartData(seven, "tr");
    const series = activeSeries(pts);
    expect(series).toEqual(["chat", "rules", "explain", "booking_nl", "voice_stt", "other"]);
    const folded = foldOther(pts, series);
    expect(folded[0]).toMatchObject({ chat: 900, booking_nl: 600, voice_stt: 500, other: 30 });
    // five features (the e2e seed): five named, no Diğer
    const five = dayChartData([{ key: "2026-10-16", calls: 1, tokens: 15, cost_usd: 0, refused: 0, features: { chat: 1, rules: 2, explain: 3, booking_nl: 4, voice_stt: 5 } }], "tr");
    expect(activeSeries(five)).toEqual(["chat", "rules", "explain", "booking_nl", "voice_stt"]);
  });

  it("F-CH-4: colours follow the feature; a feature without its own colour takes the first one not shown", () => {
    const legend = dailyLegend(["chat", "rules", "explain", "booking_nl", "voice_stt", "other"], (s) => s);
    expect(legend.map((l) => l.color)).toEqual(["var(--cat-1)", "var(--cat-2)", "var(--cat-4)", "var(--cat-3)", "var(--cat-5)", "var(--label-3)"]);
  });

  it("sorts users by share of their limit and searches Turkish-insensitively", () => {
    const users: UsageRow[] = [
      { key: 1, calls: 1, tokens: 900, cost_usd: 0, refused: 0, label: "Ayşe", email: "ayse@uni.edu.tr", limits: { daily: 0, monthly: 10000 } },
      { key: 2, calls: 1, tokens: 300, cost_usd: 0, refused: 0, label: "İlker", email: "ilker@uni.edu.tr", limits: { daily: 0, monthly: 400 } },
      { key: 3, calls: 1, tokens: 5000, cost_usd: 0, refused: 0, label: "Can", email: "can@uni.edu.tr", limits: { daily: 0, monthly: 0 } },
    ];
    expect(sortUsers(users, "").map((u) => u.key)).toEqual([2, 1, 3]);
    expect(userPct(users[1]!)).toBe(75);
    expect(userPct(users[2]!)).toBeNull();
    expect(sortUsers(users, "İLK").map((u) => u.key)).toEqual([2]);
  });

  it("maps reason codes and server errors", () => {
    expect(reasonOf("prompt_injection_override")).toBe("prompt_injection_override");
    expect(reasonOf("weird")).toBe("other");
    expect(reasonOf(null)).toBe("other");
    const e = new HttpError(422, "422 Unprocessable", { code: "model_not_synced", message_tr: "Model eşitlenmedi.", message_en: "Not synced." });
    expect(errorMessage(e, "tr", "x")).toBe("Model eşitlenmedi.");
    expect(errorMessage(e, "en", "x")).toBe("Not synced.");
    expect(errorMessage(new Error("boom"), "tr", "Bir hata oldu")).toBe("Bir hata oldu");
  });
});

describe("CH-05 daily chart helpers", () => {
  const day = (iso: string, chat: number, rules = 0) => ({ day: iso, label: iso, total: chat + rules, chat, rules, intake: 0, explain: 0, vision: 0, other: 0 });

  it("the legend keeps the fixed order and the entity colour when a series is filtered out", () => {
    const legend = dailyLegend(["chat", "intake", "other"], (s) => s.toUpperCase());
    expect(legend.map((l) => l.key)).toEqual(["chat", "intake", "other"]);
    expect(legend.map((l) => l.color)).toEqual(["var(--cat-1)", "var(--cat-3)", "var(--label-3)"]);
    expect(legend[1]!.label).toBe("INTAKE");
  });

  it("folds days into weekly sums that end with the latest day (30 days → 5 columns)", () => {
    const days = Array.from({ length: 30 }, (_, i) => day(new Date(Date.UTC(2026, 8, 17 + i)).toISOString().slice(0, 10), 10, 1));
    const weeks = foldWeeks(days, (from, to) => `${from}–${to}`);
    expect(weeks).toHaveLength(5);
    expect(weeks.at(-1)).toMatchObject({ day: "2026-10-10", label: "2026-10-10–2026-10-16", chat: 70, rules: 7, total: 77 });
    expect(weeks[0]).toMatchObject({ day: "2026-09-17", chat: 20, total: 22 });
    expect(weeks.reduce((s, w) => s + w.total, 0)).toBe(330);
  });

  it("knows when the last day is today in Istanbul", () => {
    const pts = [day("2026-10-16", 1), day("2026-10-17", 1)];
    expect(lastIsToday(pts, new Date("2026-10-17T21:30:00Z"))).toBe(false); // already the 18th in Istanbul
    expect(lastIsToday(pts, new Date("2026-10-17T20:30:00Z"))).toBe(true);
    expect(lastIsToday([], new Date())).toBe(false);
  });
});
