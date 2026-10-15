/** Settings › AI policy (KVKK): off by default, the full notice before the first enable, the sign-off after. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import type { AiPolicy } from "@/lib/api/ai-policy";

const NOTICE = { tr: "Bu özellik açıldığında yüklenen dosyaların metni yurt dışındaki Claude API'ye gönderilir.", en: "When enabled, the text of uploaded files is sent to the Claude API." };
const state = vi.hoisted(() => ({ policy: null as unknown, put: vi.fn(), admin: true }));

vi.mock("@/lib/api/shell-extra", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/shell-extra")>()),
  usePermissions: () => ({ perms: [], me: undefined, can: () => state.admin }),
}));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  request: async (path: string, opts: { method?: string; body?: unknown } = {}) => {
    if (path !== "/ai/policy") throw new Error(`unexpected ${path}`);
    return opts.method === "PUT" ? state.put(opts.body) : state.policy;
  },
}));

import { AiPolicyCard } from "./ai-policy";

const off: AiPolicy = { intake_enabled: false, vision_enabled: false, signoff: null, notice: NOTICE, notice_version: "2026-10-15", legal_basis: "KVKK Art. 9" };

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale="en">
        <AiPolicyCard />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("AI policy card", () => {
  beforeEach(() => {
    state.policy = off;
    state.admin = true;
    state.put.mockReset();
    state.put.mockImplementation(async (b: { intake_enabled?: boolean; vision_enabled?: boolean }) => {
      const on = !!b.intake_enabled;
      state.policy = { ...off, intake_enabled: on, vision_enabled: !!b.vision_enabled, signoff: { by: 1, by_label: "Sistem Yöneticisi", at: "2026-10-15T18:00:00+00:00", features: on ? ["intake"] : [], enabled: on, notice_version: "2026-10-15" } };
      return state.policy;
    });
  });

  it("is off by default: pill AI off, no sign-off, vision locked behind intake", async () => {
    renderCard();
    expect(await screen.findByText("AI off")).toBeInTheDocument();
    expect(screen.getByText(/No sign-off recorded/)).toBeInTheDocument();
    expect(screen.getByTestId("ai-policy-vision")).toHaveAttribute("data-disabled");
  });

  it("shows the full notice before the first enable, needs the acknowledgement, then shows the sign-off", async () => {
    renderCard();
    await userEvent.click(await screen.findByTestId("ai-policy-intake"));
    expect(await screen.findByTestId("ai-policy-notice-text")).toHaveTextContent(NOTICE.en);
    const confirm = screen.getByTestId("ai-policy-confirm");
    expect(confirm).toBeDisabled();
    expect(state.put).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId("ai-policy-ack"));
    await userEvent.click(confirm);
    await waitFor(() => expect(state.put).toHaveBeenCalledWith({ intake_enabled: true, kvkk_ack: true }));
    expect(await screen.findByText("AI on")).toBeInTheDocument();
    expect(screen.getByTestId("ai-signoff")).toHaveTextContent(/Turned on by Sistem Yöneticisi on .*2026/);
  });

  it("turns off at any time without the acknowledgement", async () => {
    state.policy = { ...off, intake_enabled: true, signoff: { by: 1, by_label: "Sistem Yöneticisi", at: "2026-10-15T18:00:00+00:00", features: ["intake"], enabled: true } };
    renderCard();
    await userEvent.click(await screen.findByTestId("ai-policy-intake"));
    await waitFor(() => expect(state.put).toHaveBeenCalledWith({ intake_enabled: false }));
    expect(screen.queryByTestId("ai-policy-notice-text")).toBeNull();
    expect(await screen.findByText("AI off")).toBeInTheDocument();
  });

  it("is read-only for non-administrators", async () => {
    state.admin = false;
    renderCard();
    expect(await screen.findByText("Only an administrator can change the AI policy.")).toBeInTheDocument();
    expect(screen.getByTestId("ai-policy-intake")).toHaveAttribute("data-disabled");
  });
});
