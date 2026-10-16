/**
 * P18-LANG (owner decision 2026-10-15: Turkish and English only): a user whose stored profile language is a
 * CRBS code (`de`, from a legacy import) keeps it and is shown English; the profile offers only tr / en.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider, useI18n } from "@/lib/i18n/provider";

const state = vi.hoisted(() => ({
  profile: { id: 7, email: "ogretmen@uni.edu.tr", username: "ogretmen", firstname: "Ayşe", lastname: "Yılmaz", displayname: null, ext: null, language: "de" as string | null, department_id: null, role: "TEACHER", role_name: "Öğretim elemanı" },
  put: vi.fn(),
  success: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: state.success, error: vi.fn(), message: vi.fn() } }));
vi.mock("next/navigation", () => ({ usePathname: () => "/profile", useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }), useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/api/crbs", async (orig) => {
  const real = await orig<typeof import("@/lib/api/crbs")>();
  return {
    ...real,
    useProfile: () => ({ data: state.profile, isLoading: false }),
    useCrbsMe: () => ({ data: { id: 7, force_password_reset: false } }),
    useOrgPublic: () => ({ data: { default_language: "tr", languages: ["tr", "en"] } }),
    useOrgI18n: () => ({ data: { default_language: "tr", languages: ["tr", "en"] } }),
    crbs: { ...real.crbs, auth: { ...real.crbs.auth, putProfile: (body: unknown) => state.put(body) } },
  };
});

import { ProfileView } from "./profile-view";
import { useProfileLanguage } from "@/components/bookings/use-booking-format";

function Locale() {
  useProfileLanguage();
  return <p data-testid="locale">{useI18n().locale}</p>;
}

function renderProfile() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale="tr">
        <Locale />
        <ProfileView />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("profile language: Turkish and English only", () => {
  beforeEach(() => {
    state.profile.language = "de";
    state.put.mockReset();
    state.success.mockReset();
    state.put.mockImplementation(async (body: Record<string, unknown>) => ({ ...state.profile, ...body }));
    sessionStorage.clear();
  });

  it("offers the institution default, Turkish and English", () => {
    renderProfile();
    const select = screen.getByTestId("profile-language");
    expect(within(select).getAllByRole("option").map((o) => (o as HTMLOptionElement).value)).toEqual(["", "tr", "en"]);
  });

  it("renders a user stored as de in English and keeps the stored code on save", async () => {
    renderProfile();
    // the session applies the profile language: de is shown English
    await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("en"));
    expect(screen.getByTestId("profile-language")).toHaveValue("en");
    expect(screen.getByText(/Your stored language \(de\) is no longer offered/)).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("profile-save"));
    await waitFor(() => expect(state.put).toHaveBeenCalledTimes(1));
    expect(state.put.mock.calls[0]![0]).not.toHaveProperty("language"); // de is kept, never re-sent
  });

  it("sends the language only when the user picks another one", async () => {
    renderProfile();
    await userEvent.selectOptions(screen.getByTestId("profile-language"), "tr");
    await userEvent.click(screen.getByTestId("profile-save"));
    await waitFor(() => expect(state.put).toHaveBeenCalledTimes(1));
    expect(state.put.mock.calls[0]![0]).toMatchObject({ language: "tr" });
  });

  // T-R1-37 (round-1 R1-A-30): the "saved" toast is in the language just chosen, not the previous one
  it("says Saved after switching to English and Kaydedildi after switching back", async () => {
    state.profile.language = "tr";
    renderProfile();
    await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("tr"));
    await userEvent.selectOptions(screen.getByTestId("profile-language"), "en");
    await userEvent.click(screen.getByTestId("profile-save"));
    await waitFor(() => expect(state.success).toHaveBeenCalledTimes(1));
    expect(state.success).toHaveBeenLastCalledWith("Saved");
    await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("en"));
    state.profile.language = "en";
    await userEvent.selectOptions(screen.getByTestId("profile-language"), "tr");
    await userEvent.click(screen.getByTestId("profile-save"));
    await waitFor(() => expect(state.success).toHaveBeenCalledTimes(2));
    expect(state.success).toHaveBeenLastCalledWith("Kaydedildi");
  });
});
