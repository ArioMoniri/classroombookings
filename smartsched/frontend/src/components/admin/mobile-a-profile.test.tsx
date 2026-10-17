/**
 * Mobile audit A (2026-10-17) fixes 1 and 15 on /profile:
 * - while the profile loads, a skeleton the size of the details form holds the space, so the sections below do not
 *   jump when the form arrives (CLS 0.45 phone / 0.73 tablet measured with a one-line spinner);
 * - below `lg` (phones and tablets, where the tab bar shows) the save button lives in the sticky bar, not at the end
 *   of the form that scrolls away (MOBILE M-05 at 768 failed).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

const state = vi.hoisted(() => ({
  loading: false,
  profile: { id: 7, email: "p.t@smartsched.local", username: "pt", firstname: "P.", lastname: "T.", displayname: null, ext: null, language: "tr", department_id: null, role: "TEACHER", role_name: "Öğretim elemanı" },
  compact: false,
}));
vi.mock("next/navigation", () => ({ usePathname: () => "/profile", useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }), useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/api/crbs", async (orig) => {
  const real = await orig<typeof import("@/lib/api/crbs")>();
  return {
    ...real,
    useProfile: () => (state.loading ? { data: undefined, isLoading: true } : { data: state.profile, isLoading: false }),
    useCrbsMe: () => ({ data: { id: 7, force_password_reset: false } }),
    useOrgPublic: () => ({ data: { default_language: "tr", languages: ["tr", "en"] } }),
    useOrgI18n: () => ({ data: { default_language: "tr", languages: ["tr", "en"] } }),
  };
});
vi.mock("@/components/bookings/use-is-phone", () => ({ useIsPhone: () => false, useIsCompact: () => state.compact }));

import { ProfileView } from "./profile-view";

function renderProfile() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale="tr">
        <ProfileView />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  state.loading = false;
  state.compact = false;
});

describe("mobile-a: /profile layout stability and reach", () => {
  it("holds the details form's space with a skeleton of the same six fields while the profile loads", () => {
    state.loading = true;
    renderProfile();
    const sk = screen.getByTestId("profile-skeleton");
    expect(sk).toHaveAttribute("aria-busy", "true");
    expect(sk.querySelectorAll("[data-slot=skeleton-field]")).toHaveLength(6);
  });

  it("puts the save button in the sticky bar on phones and tablets (below lg)", () => {
    state.compact = true;
    renderProfile();
    const bar = screen.getByTestId("profile-save-bar");
    expect(bar).toContainElement(screen.getByTestId("profile-save"));
    expect(screen.getAllByTestId("profile-save")).toHaveLength(1);
  });

  it("keeps the save button in the form on desktop", () => {
    renderProfile();
    expect(screen.queryByTestId("profile-save-bar")).toBeNull();
    expect(screen.getByTestId("profile-save").closest("form")).not.toBeNull();
  });
});
