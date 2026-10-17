/**
 * mobile-b phase 2, fix 1 (CLS): /settings rendered the fallback tab ("Görünüm") while /auth/me was loading and then
 * swapped to the requested tab when the permissions arrived (session-window CLS 0.41-0.63 at 390 and 768). While
 * the permissions are unknown it shows one placeholder of a fixed height instead of a tab that is about to change.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

const state = vi.hoisted(() => ({ perms: undefined as string[] | undefined }));
vi.mock("next/navigation", () => ({ usePathname: () => "/settings", useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }), useSearchParams: () => new URLSearchParams("tab=integrations") }));
vi.mock("@/lib/api/shell-extra", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/shell-extra")>()),
  usePermissions: () => ({ perms: state.perms, me: undefined, can: () => false }),
}));

import { SettingsView } from "./settings-view";

describe("/settings while the permissions load", () => {
  it("shows a fixed-height placeholder, not the fallback tab that is replaced a moment later", () => {
    state.perms = undefined;
    render(
      <QueryClientProvider client={new QueryClient()}>
        <I18nProvider initialLocale="tr">
          <SettingsView />
        </I18nProvider>
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("settings-loading")).toBeInTheDocument();
    expect(screen.queryByRole("tablist")).toBeNull();
  });
});
