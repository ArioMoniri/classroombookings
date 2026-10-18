/** W3-AI UI: the near / at-limit banner and Profil card, the no-access page, routing issues shown before saving. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

const state = vi.hoisted(() => ({
  perms: ["setup.settings"] as string[],
  me: {} as Record<string, unknown>,
  calls: [] as string[],
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }), useSearchParams: () => new URLSearchParams("tab=models") }));
vi.mock("@/lib/permissions", async (orig) => {
  const real = await orig<typeof import("@/lib/permissions")>();
  return { ...real, usePermissions: () => ({ loading: false, perms: state.perms, can: (need: string | string[] | null) => real.hasPermission(state.perms, need), canAll: () => true, userId: 1, departmentId: null }) };
});
const provider = (id: string, over: Record<string, unknown> = {}) => ({
  id,
  label_tr: id,
  label_en: id,
  secrets: ["api_key"],
  config: { enabled: true },
  config_fields: ["base_url"],
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
vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return {
    ...real,
    request: async (path: string) => {
      state.calls.push(path);
      if (path === "/ai/me/usage") return state.me;
      if (path === "/ai/admin/providers") return { providers: [provider("anthropic"), provider("openai", { transfer_ok: false })], kvkk_mechanisms: ["standard_contract"] };
      if (path === "/ai/admin/routes")
        return {
          default: null,
          features: { chat: { provider: "openai", model: "m-1" } },
          effective: { chat: { provider: "openai", model: "m-1", source: "feature", caps: {} }, rules: { provider: "anthropic", model: "claude-opus-5-5", source: "legacy", caps: {} } },
          feature_list: [],
          efforts: ["low"],
          legacy_model: "claude-opus-5-5",
        };
      throw new Error(`unexpected ${path}`);
    },
  };
});

import { AiAdmin } from "./ai-admin";
import { MyAiUsage } from "./my-ai-usage";

function renderIt(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale="tr">{ui}</I18nProvider>
    </QueryClientProvider>,
  );
}

const usage = (over: Record<string, unknown>) => ({
  user_id: 3,
  day_tokens: 320,
  month_tokens: 320,
  day_calls: 1,
  month_calls: 1,
  daily_limit: 400,
  monthly_limit: 0,
  daily_pct: 80,
  monthly_pct: null,
  pct: 80,
  state: "soft",
  soft_pct: 80,
  org_state: "none",
  by_feature: [{ key: "rules", calls: 1, tokens: 320, cost_usd: 0, refused: 0 }],
  ...over,
});

describe("MyAiUsage", () => {
  beforeEach(() => {
    state.calls = [];
  });

  it("shows the near-limit banner with the percentage, the meters and the transparency notice", async () => {
    state.me = usage({});
    renderIt(<MyAiUsage />);
    expect(await screen.findByTestId("ai-banner-near")).toHaveTextContent("%80");
    expect(screen.getByTestId("my-ai-day")).toHaveAttribute("data-state", "near");
    expect(screen.getByTestId("ai-notice")).toBeInTheDocument();
    expect(screen.getByText(/Metinden kural/)).toBeInTheDocument();
  });

  it("shows the at-limit alert and hides itself for someone who never used AI", async () => {
    state.me = usage({ day_tokens: 400, daily_pct: 100, pct: 100, state: "hard" });
    const { unmount } = renderIt(<MyAiUsage />);
    const alert = await screen.findByTestId("ai-banner-at");
    expect(alert).toHaveTextContent("sınırınıza ulaştınız");
    unmount();
    state.me = usage({ day_tokens: 0, month_tokens: 0, daily_limit: 0, daily_pct: null, pct: null, state: "none", by_feature: [] });
    renderIt(<MyAiUsage />);
    await waitFor(() => expect(state.calls).toContain("/ai/me/usage"));
    expect(screen.queryByTestId("my-ai-usage")).toBeNull();
  });
});

describe("AiAdmin", () => {
  it("answers no access without planning.admin / setup.settings", () => {
    state.perms = ["book_single.create"];
    renderIt(<AiAdmin />);
    expect(screen.queryByTestId("ai-admin")).toBeNull();
    expect(screen.getByText("Bu sayfaya erişiminiz yok")).toBeInTheDocument();
  });

  it("models tab: effective routes and the missing transfer record are shown before saving", async () => {
    state.perms = ["setup.settings"];
    renderIt(<AiAdmin />);
    expect(await screen.findByTestId("ai-route-chat")).toBeInTheDocument();
    expect(screen.getByTestId("ai-route-effective-chat")).toHaveTextContent("bu özelliğe özel");
    expect(screen.getByTestId("ai-route-effective-rules")).toHaveTextContent("Ayarlar'daki model");
    expect(screen.getByTestId("ai-route-issues-chat")).toHaveTextContent("KVKK aktarım kaydı yok");
    expect(screen.getByTestId("ai-routes-save")).not.toBeDisabled(); // a missing record warns, the backend refuses calls
    // MOBILE M-05: below lg the save is in the page-actions capsule above the tab bar (sweep2-2026-10-18)
    expect(screen.getByTestId("ai-routes-save").closest('[data-slot="page-actions"]')).not.toBeNull();
  });
});
