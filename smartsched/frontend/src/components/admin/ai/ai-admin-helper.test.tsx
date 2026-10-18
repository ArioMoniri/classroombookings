/** HX-09 / HX-10 mounts in /admin/ai: the "Yardımcı" tab and, under Limitler, Fakülteler + the faculty view. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

const state = vi.hoisted(() => ({ tab: "helper", edit: [] as boolean[] }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }), useSearchParams: () => new URLSearchParams(`tab=${state.tab}`) }));
vi.mock("@/lib/permissions", async (orig) => {
  const real = await orig<typeof import("@/lib/permissions")>();
  return { ...real, usePermissions: () => ({ loading: false, perms: ["setup.settings"], can: (need: string | string[] | null) => real.hasPermission(["setup.settings"], need), canAll: () => true, userId: 1, departmentId: null }) };
});
vi.mock("@/components/helper/admin/helper-admin", () => ({
  HelperAdminTab: ({ canEdit }: { canEdit?: boolean }) => {
    state.edit.push(!!canEdit);
    return <p data-testid="stub-helper-admin">helper admin</p>;
  },
}));
vi.mock("@/components/helper/admin/faculty-limits", () => ({ FacultyLimits: () => <p data-testid="stub-faculty-limits" /> }));
vi.mock("@/components/helper/admin/faculty-usage", () => ({ FacultyUsageView: () => <p data-testid="stub-faculty-usage" /> }));
vi.mock("@/lib/api/ai-admin", async (orig) => {
  const real = await orig<typeof import("@/lib/api/ai-admin")>();
  const limits = real.Limits.parse({
    org_monthly_tokens: 0,
    org_monthly_cost_usd: 0,
    user_daily_tokens: 0,
    user_monthly_tokens: 0,
    soft_pct: 80,
    requests_per_minute: 30,
    max_concurrent: 2,
    org: { day_tokens: 0, month_tokens: 0, month_cost_usd: 0, month_calls: 0, budget_tokens: 0, budget_cost_usd: 0, pct: null, state: "none", soft_pct: 80, month: "2026-10" },
  });
  return { ...real, useAiLimits: () => ({ isLoading: false, isError: false, data: limits }) };
});

import { AI_TABS, AiAdmin } from "./ai-admin";

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
  state.edit = [];
});

describe("/admin/ai helper mounts", () => {
  it("has a Yardımcı tab that renders the helper settings with the edit right", () => {
    state.tab = "helper";
    expect(AI_TABS).toContain("helper");
    renderIt();
    expect(screen.getByTestId("ai-tab-helper")).toHaveTextContent("Yardımcı");
    expect(screen.getByTestId("stub-helper-admin")).toBeInTheDocument();
    expect(state.edit).toContain(true);
  });

  it("shows Fakülteler and the faculty view under Limitler", () => {
    state.tab = "limits";
    renderIt();
    expect(screen.getByTestId("ai-limits")).toBeInTheDocument();
    expect(screen.getByTestId("stub-faculty-limits")).toBeInTheDocument();
    expect(screen.getByTestId("stub-faculty-usage")).toBeInTheDocument();
  });
});
