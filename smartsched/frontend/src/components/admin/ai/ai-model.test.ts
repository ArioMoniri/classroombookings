import { describe, expect, it } from "vitest";
import { HttpError } from "@/lib/api/client";
import type { Provider, UsageRow } from "@/lib/api/ai-admin";
import {
  activeSeries,
  compactTokens,
  dayChartData,
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
  seriesOf,
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

  it("stacks days by feature in the fixed order, unknown features as other", () => {
    const pts = dayChartData(rows, "tr");
    expect(pts[0]).toMatchObject({ day: "2026-10-16", chat: 200, other: 100, rules: 0, total: 300 });
    expect(pts[0]!.label).toMatch(/16 Eki/);
    expect(activeSeries(pts)).toEqual(["chat", "rules", "other"]);
    expect(dayChartData(rows, "en", 1)).toHaveLength(1);
    expect(seriesOf("booking_nl")).toBe("other");
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
