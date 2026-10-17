/** Security follow-up wave3-sec2 (docs/SECURITY.md R12): the local-server opt-in of the OpenAI-compatible provider. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

const state = vi.hoisted(() => ({ puts: [] as { path: string; body: unknown }[], allow: false }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const base = { secrets: ["api_key"], config_fields: ["base_url"], keys: { api_key: { set: false } }, has_credentials: true, usable: true, models: [], last_test: {}, transfer: {}, transfer_ok: true };
const WARN = { code: "local_url_opt_in", message_tr: "Yerel sunucuya izin verildi: bu sağlayıcı kurum içi ağdaki bir adrese istek gönderebilir.", message_en: "A local server is allowed." };
vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return {
    ...real,
    request: async (path: string, opts?: { method?: string; body?: unknown }) => {
      if (opts?.method === "PUT") {
        state.puts.push({ path, body: opts.body });
        state.allow = Boolean((opts.body as { allow_local?: boolean }).allow_local ?? state.allow);
        return {};
      }
      if (path === "/ai/admin/providers")
        return {
          providers: [
            { ...base, id: "openai_compatible", label_tr: "OpenAI uyumlu sunucu", label_en: "OpenAI-compatible server", keyless: true, config: { enabled: true, base_url: "http://127.0.0.1:11434/v1" }, local: true, allow_local: state.allow, warnings: state.allow ? [WARN] : [] },
            { ...base, id: "openai", label_tr: "OpenAI", label_en: "OpenAI", config: { enabled: true }, allow_local: false, warnings: [] },
          ],
          kvkk_mechanisms: [],
        };
      return {};
    },
  };
});

import { ProvidersTab } from "./providers-tab";

describe("ProvidersTab · local server opt-in", () => {
  it("offers the switch only on the OpenAI-compatible card and shows the warning once it is on", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <I18nProvider initialLocale="tr">
          <ProvidersTab canEdit />
        </I18nProvider>
      </QueryClientProvider>,
    );
    const toggle = await screen.findByTestId("ai-provider-allow-local-openai_compatible");
    expect(screen.queryByTestId("ai-provider-allow-local-openai")).not.toBeInTheDocument();
    expect(screen.getByText("Yerel sunucuya izin ver")).toBeInTheDocument();
    expect(screen.queryByTestId("ai-provider-warning-openai_compatible")).not.toBeInTheDocument();
    fireEvent.click(toggle);
    await waitFor(() => expect(state.puts).toContainEqual({ path: "/ai/admin/providers/openai_compatible", body: { allow_local: true } }));
    expect(await screen.findByTestId("ai-provider-warning-openai_compatible")).toHaveTextContent("Yerel sunucuya izin verildi");
  });
});
