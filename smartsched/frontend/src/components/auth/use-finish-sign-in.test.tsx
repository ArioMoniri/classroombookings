// e2e 2026-10-18 (AUX-F §16.1 on the stack): after the second step the code field unmounts with the sign-in page and
// focus fell to <body> on the landing page. Leaving the sign-in sheet hands focus to the landing page's <main>.
import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const router = { replace: vi.fn(), push: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/login/verify", useSearchParams: () => new URLSearchParams() }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), warning: vi.fn(), error: vi.fn() }) }));
vi.mock("@/components/bookings/use-booking-format", async (orig) => ({ ...(await orig<object>()), applySessionLanguage: vi.fn(async () => undefined) }));

import { I18nProvider } from "@/lib/i18n/provider";
import { useFinishSignIn } from "./use-finish-sign-in";

const wrapper = ({ children }: { children: ReactNode }) => <I18nProvider initialLocale="tr">{children}</I18nProvider>;

afterEach(() => {
  document.body.innerHTML = "";
  vi.useRealTimers();
});

describe("useFinishSignIn: focus after signing in", () => {
  it("moves focus to the landing page's <main> once it renders, never leaving it on <body>", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useFinishSignIn("/my-bookings"), { wrapper });
    // the code field is focused on the sign-in page, then unmounts with it
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();
    await result.current({ status: "signed_in", user: { id: 5, full_name: "Ayşe Yılmaz", permissions: [] } } as never, "local");
    expect(router.replace).toHaveBeenCalledWith("/my-bookings");
    input.remove();
    expect(document.activeElement).toBe(document.body);
    // the landing page renders a little later (client navigation)
    await vi.advanceTimersByTimeAsync(600);
    const main = document.createElement("main");
    main.id = "main";
    main.tabIndex = -1;
    document.body.appendChild(main);
    await vi.advanceTimersByTimeAsync(400);
    expect(document.activeElement).toBe(main);
  });
});
