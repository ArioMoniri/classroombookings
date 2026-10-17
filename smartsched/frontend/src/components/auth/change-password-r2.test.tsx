// Flow-loop round 2, lane A (T-R2-03, R2-S-02): after a forced password change the form updates the cached /me
// (force_password_reset → false) BEFORE it navigates, and the shell only sends a user to /login/change-password on a
// settled /me that still says so — never on the stale cached one while it refetches.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const router = { replace: vi.fn(), push: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() };
vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => "/login/change-password",
  useSearchParams: () => new URLSearchParams("next=%2Fmy-bookings"),
}));
const changePassword = vi.fn(async () => ({ ok: true, signedOut: false }));
vi.mock("@/lib/api/shell-extra", async (importOriginal) => ({ ...(await importOriginal<object>()), changePassword: (...a: unknown[]) => changePassword(...(a as [])) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { ChangePasswordForm } from "./change-password-form";
import { mustChangePassword } from "@/components/shell/app-shell";
import { I18nProvider } from "@/lib/i18n/provider";

describe("T-R2-03: forced password change leaves the page", () => {
  it("marks the cached /me as settled (force_password_reset false) before router.replace(next)", async () => {
    const qc = new QueryClient();
    qc.setQueryData(["me", "full"], { id: 7, force_password_reset: true, permissions: [] });
    const order: string[] = [];
    router.replace.mockImplementation((to: string) => order.push(`replace:${to}:force=${String((qc.getQueryData(["me", "full"]) as { force_password_reset?: boolean }).force_password_reset)}`));
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={qc}>
        <I18nProvider initialLocale="tr">
          <ChangePasswordForm />
        </I18nProvider>
      </QueryClientProvider>,
    );
    await user.type(document.getElementById("cur")!, "Old-2026!");
    await user.type(document.getElementById("new")!, "Flow-2026!pw");
    await user.type(document.getElementById("again")!, "Flow-2026!pw");
    await user.click(screen.getByRole("button", { name: /Kaydet/ }));
    await waitFor(() => expect(router.replace).toHaveBeenCalled());
    expect(changePassword).toHaveBeenCalledTimes(1);
    expect(order).toEqual(["replace:/my-bookings:force=false"]);
  });

  it("the shell redirects only on a settled /me that says so", () => {
    expect(mustChangePassword({ data: { force_password_reset: true }, isFetching: false })).toBe(true);
    expect(mustChangePassword({ data: { force_password_reset: true }, isFetching: true })).toBe(false);
    expect(mustChangePassword({ data: { force_password_reset: false }, isFetching: false })).toBe(false);
    expect(mustChangePassword({ data: undefined, isFetching: false })).toBe(false);
  });
});
