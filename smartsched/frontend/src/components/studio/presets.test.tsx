import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { PresetMenu } from "./presets";

vi.mock("./studio-context", () => ({ useStudio: () => ({ kind: "COURSE", local: { preset_id: null } }) }));
vi.mock("@/lib/api/studio-hooks", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/studio-hooks")>()),
  usePresets: () => ({ data: [{ id: 1, name: "Bahar varsayılan", author: "Fatih", rules: [], created_at: "2026-10-01T00:00:00Z", updated_at: null }] }),
}));

describe("PresetMenu (admin persona M-12: the menu crashed with Base UI error #31)", () => {
  it("opens and lists the shared presets under their group label", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <I18nProvider initialLocale="tr">
          <PresetMenu />
        </I18nProvider>
      </QueryClientProvider>,
    );
    await userEvent.click(screen.getByTestId("preset-menu"));
    const menu = await screen.findByRole("menu");
    expect(menu).toHaveTextContent("Bahar varsayılan");
    expect(screen.getByRole("group")).toContainElement(screen.getByTestId("preset-item"));
  });
});
