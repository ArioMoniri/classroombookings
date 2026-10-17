/** VO-07: /admin/ai voice — speech-only route choices, capability chips, the voice test, the Ses card, voice limits. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

const state = vi.hoisted(() => ({
  tab: "models",
  calls: [] as { path: string; method?: string; body?: unknown }[],
  voice: { enabled: false, consent_required: true, max_seconds: 120, local_only: false, vocabulary: "catalog", live_captions: "off" } as Record<string, unknown>,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }), useSearchParams: () => new URLSearchParams(`tab=${state.tab}`) }));
vi.mock("@/lib/permissions", async (orig) => {
  const real = await orig<typeof import("@/lib/permissions")>();
  return { ...real, usePermissions: () => ({ loading: false, perms: ["setup.settings"], can: () => true, canAll: () => true, userId: 1, departmentId: null }) };
});
const provider = (id: string, over: Record<string, unknown> = {}) => ({
  id,
  label_tr: id,
  label_en: id,
  secrets: ["api_key"],
  config: { enabled: true },
  config_fields: [],
  keyless: false,
  keys: { api_key: { set: true, masked: "••••1234" } },
  has_credentials: true,
  usable: true,
  models: [{ id: "m-1" }],
  fetched_at: "2026-10-17T18:00:00",
  last_test: {},
  transfer: {},
  transfer_ok: true,
  local: false,
  ...over,
});
const providers = () => [
  provider("anthropic", { capabilities: ["text"], models: [{ id: "claude-opus-5-5", modalities: ["text"] }] }),
  provider("openai", {
    capabilities: ["text", "stt", "tts", "audio_native"],
    models: [
      { id: "gpt-5", modalities: ["text"] },
      { id: "gpt-4o-mini-transcribe", modalities: ["stt"] },
      { id: "gpt-transcribe", modalities: ["stt"] },
    ],
  }),
];
vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return {
    ...real,
    request: async (path: string, opts: { method?: string; body?: unknown; schema?: { parse: (x: unknown) => unknown } } = {}) => {
      state.calls.push({ path, method: opts.method, body: opts.body });
      const out = (x: unknown) => (opts.schema ? opts.schema.parse(x) : x);
      if (path === "/ai/admin/providers") return out({ providers: providers(), kvkk_mechanisms: ["standard_contract"] });
      if (path === "/ai/admin/routes")
        return out({
          default: null,
          features: {},
          effective: { voice_stt: { provider: "", model: "", source: "none", caps: {} } },
          feature_list: [],
          efforts: ["low"],
          legacy_model: "claude-opus-5-5",
        });
      if (path === "/ai/admin/providers/openai/test") return out({ ok: true, detail: "ok", model: "gpt-4o-mini-transcribe", transcript_preview: "B-204 numaralı salonda" });
      if (path === "/ai/admin/voice") {
        if (opts.method === "PUT") state.voice = { ...state.voice, ...(opts.body as object) };
        return out(state.voice);
      }
      if (path === "/ai/admin/guardrails") return out({ scope_check: true, injection_check: true, model_scope_check: false, upload_neutralize: true, output_check: true, rate_limit: true });
      if (path === "/ai/admin/refusals") return out({ rows: [] });
      if (path === "/ai/voice/status") throw new real.HttpError(404, "404");
      if (path === "/ai/admin/limits")
        return out({
          org_monthly_tokens: 0,
          org_monthly_cost_usd: 0,
          user_daily_tokens: 0,
          user_monthly_tokens: 0,
          roles: { TEACHER: { audio_daily: 300 } },
          users: {},
          soft_pct: 80,
          alert_recipients: [],
          requests_per_minute: 30,
          max_concurrent: 2,
          user_daily_audio_s: 600,
          user_monthly_audio_s: 6000,
          org_monthly_audio_s: 0,
          topups: [],
          org: { day_tokens: 0, month_tokens: 0, month_cost_usd: 0, month_calls: 0, budget_tokens: 0, budget_cost_usd: 0, pct: null, state: "none", soft_pct: 80, month: "2026-10" },
        });
      throw new Error(`unexpected ${path}`);
    },
  };
});

import { isSpeechModel, routesBody, secondsOf, speechProviders } from "./ai-model";
import { AiAdmin } from "./ai-admin";

function renderIt() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale="tr">
        <AiAdmin />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  state.calls = [];
});

describe("voice helpers", () => {
  it("speech models by modality, else by id; providers keep only their speech models", () => {
    expect(isSpeechModel({ id: "gpt-5", modalities: ["text"] })).toBe(false);
    expect(isSpeechModel({ id: "whisper-1", modalities: [] })).toBe(true);
    expect(isSpeechModel({ id: "gpt-4o-mini-tts", modalities: [] }, "tts")).toBe(true);
    const out = speechProviders(providers() as never);
    expect(out.map((p) => p.id)).toEqual(["openai"]);
    expect(out[0]!.models.map((m) => m.id)).toEqual(["gpt-4o-mini-transcribe", "gpt-transcribe"]);
  });
  it("the routes body carries voice_stt; minutes become seconds", () => {
    expect(routesBody(null, { voice_stt: { provider: "openai", model: "gpt-transcribe" } }).features).toEqual({ voice_stt: { provider: "openai", model: "gpt-transcribe" } });
    expect(secondsOf("10")).toBe(600);
    expect(secondsOf("")).toBeUndefined();
    expect(secondsOf("-1")).toBeNull();
  });
});

describe("Modeller: Sesle yazma", () => {
  it("offers only speech-capable providers and models, says the mic is hidden without a model, and saves the route", async () => {
    state.tab = "models";
    renderIt();
    const row = await screen.findByTestId("ai-route-voice_stt");
    expect(row).toHaveTextContent("Sesle yazma");
    expect(screen.getByTestId("ai-route-note-voice_stt")).toHaveTextContent("Model seçilmezse mikrofon kimseye gösterilmez.");
    const prov = screen.getByTestId("ai-route-provider-voice_stt") as HTMLSelectElement;
    expect(Array.from(prov.options).map((o) => o.value)).toEqual(["", "openai"]);
    expect(prov.options[0]!.textContent).toBe("Seçilmedi (mikrofon gizli)");
    fireEvent.change(prov, { target: { value: "openai" } });
    const model = screen.getByTestId("ai-route-model-voice_stt") as HTMLSelectElement;
    expect(Array.from(model.options).map((o) => o.value)).toEqual(["gpt-4o-mini-transcribe", "gpt-transcribe"]);
    expect(within(row).getByTestId("ai-route-effort-voice_stt").closest("div")).toHaveClass("hidden"); // no effort for speech
    await act(async () => {
      fireEvent.click(screen.getByTestId("ai-routes-save"));
    });
    const put = state.calls.find((c) => c.path === "/ai/admin/routes" && c.method === "PUT");
    expect((put!.body as { features: Record<string, unknown> }).features.voice_stt).toEqual({ provider: "openai", model: "gpt-4o-mini-transcribe" });
   }, 20_000); // the first render of the admin screen imports every tab
});

describe("Sağlayıcılar: capabilities and the voice test", () => {
  it("shows Metin · Ses→yazı · Sesli okuma and runs the voice test with the speech model", async () => {
    state.tab = "providers";
    renderIt();
    expect(await screen.findByTestId("ai-provider-caps-openai")).toHaveTextContent("Metin · Ses→yazı · Sesli okuma · Doğal ses");
    expect(screen.getByTestId("ai-provider-caps-anthropic")).toHaveTextContent("Metin");
    expect(screen.queryByTestId("ai-provider-voice-test-anthropic")).toBeNull();
    await act(async () => {
      fireEvent.click(screen.getByTestId("ai-provider-voice-test-openai"));
    });
    await waitFor(() => expect(state.calls.find((c) => c.path === "/ai/admin/providers/openai/test")?.body).toEqual({ model: "gpt-4o-mini-transcribe" }));
    expect(screen.getByTestId("ai-transfer-voice-openai")).toBeInTheDocument();
    expect(screen.queryByTestId("ai-transfer-voice-anthropic")).toBeNull();
  });
});

describe("Koruma: Ses card", () => {
  it("one switch turns voice on (shared setting), no route is pointed at Modeller, advanced settings are folded", async () => {
    state.tab = "guard";
    renderIt();
    const card = await screen.findByTestId("ai-voice-card");
    expect(await within(card).findByTestId("ai-voice-no-route")).toHaveTextContent("Sesle yazma");
    expect(screen.getByTestId("ai-voice-advanced")).not.toHaveAttribute("open");
    await act(async () => {
      fireEvent.click(screen.getByTestId("ai-voice-enabled"));
    });
    await waitFor(() => expect(state.calls.some((c) => c.path === "/ai/admin/voice" && c.method === "PUT" && (c.body as { enabled?: boolean }).enabled === true)).toBe(true));
    fireEvent.change(screen.getByTestId("ai-voice-max"), { target: { value: "500" } });
    await act(async () => {
      fireEvent.click(screen.getByTestId("ai-voice-save"));
    });
    expect(screen.getByTestId("ai-voice-error")).toHaveTextContent("10 ile 120");
  });
});

describe("Limitler: voice time", () => {
  it("shows minutes and saves seconds, role overrides merged", async () => {
    state.tab = "limits";
    renderIt();
    const card = await screen.findByTestId("ai-limits-audio");
    expect(within(card).getByTestId("ai-limit-audio-daily")).toHaveValue("10");
    fireEvent.change(within(card).getByTestId("ai-limit-audio-daily"), { target: { value: "15" } });
    await act(async () => {
      fireEvent.click(screen.getByTestId("ai-limits-save"));
    });
    const put = state.calls.find((c) => c.path === "/ai/admin/limits" && c.method === "PUT")!.body as Record<string, unknown>;
    expect(put.user_daily_audio_s).toBe(900);
    expect(put.user_monthly_audio_s).toBe(6000);
    expect((put.roles as Record<string, unknown>).TEACHER).toEqual({ audio_daily: 300 });
  });
});
