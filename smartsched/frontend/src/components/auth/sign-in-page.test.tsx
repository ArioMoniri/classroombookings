import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { OrgPublicAuth } from "@/lib/api/identity";
import { I18nProvider } from "@/lib/i18n/provider";
import { SignInPage } from "./sign-in-page";
import { readSignInParams, type InviteState } from "./signin-model";

const nav = vi.hoisted(() => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => nav, useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/api/crbs", () => ({ useAppVersion: () => ({ data: "1.4.0" }), crbs: { org: { i18n: () => Promise.reject(new Error("x")) } } }));
vi.mock("@/components/bookings/use-booking-format", () => ({ applySessionLanguage: vi.fn() }));

function org(over: Partial<OrgPublicAuth> & { ms?: boolean; local?: boolean; self?: boolean } = {}): OrgPublicAuth {
  const { ms = true, local = true, self = true, ...rest } = over;
  return {
    name: "Örnek Üniversitesi",
    logo_url: null,
    login_message: null,
    maintenance_mode: false,
    maintenance_message: null,
    ldap_enabled: false,
    setup_required: false,
    default_language: "tr",
    languages: ["tr", "en"],
    auth: { microsoft: { enabled: ms, label: "Microsoft", start_url: "/api/v1/auth/sso/entra/start", domain_hint: "ornek.edu.tr", self_signup: self }, local_enabled: local, ldap_enabled: false, self_signup_role_name: "Standart kullanıcı" },
    ...rest,
  };
}

function view(o: OrgPublicAuth | null, query = "", invite: InviteState = null, locale: "tr" | "en" = "tr", lastMethodLocal = false) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLocale={locale}>
        <SignInPage org={o} params={readSignInParams(new URLSearchParams(query))} invite={invite} lastMethodLocal={lastMethodLocal} />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

const SIGNUP = /kaydol|kayıt ol|sign ?up|register|hesap oluştur|create account/i;

describe("SignInPage (docs/design/v2/sign-in.md)", () => {
  beforeEach(() => {
    nav.replace.mockReset();
    document.cookie = "smartsched_last_signin=; max-age=0; path=/";
  });
  afterEach(() => vi.restoreAllMocks());

  it("Microsoft on: one link to the start route with next, hints with the domain and the sign-up role; no sign-up control (§15 #1 #6 #7)", () => {
    view(org(), "next=/timetable");
    const ms = screen.getByRole("link", { name: "Microsoft ile giriş yap" });
    expect(ms.getAttribute("href")).toBe("/api/v1/auth/sso/entra/start?next=%2Ftimetable");
    expect(ms.getAttribute("aria-describedby")).toContain("signin-hint-account");
    const hints = screen.getByTestId("signin-hints");
    expect(hints).toHaveTextContent("Örnek Üniversitesi iş veya okul hesabınızı kullanın (ad.soyad@ornek.edu.tr).");
    expect(hints).toHaveTextContent("Standart kullanıcı");
    for (const el of [...screen.queryAllByRole("link"), ...screen.queryAllByRole("button")]) expect(el.textContent ?? "").not.toMatch(SIGNUP);
    expect(document.body.textContent).not.toMatch(/Azure|Active Directory|Entra|Office 365/);
  });

  it("draws the official logo: four squares in Microsoft's colours (§15 #2)", () => {
    view(org());
    const fills = [...screen.getByTestId("microsoft-logo").querySelectorAll("rect")].map((r) => r.getAttribute("fill"));
    expect(fills).toEqual(["#f25022", "#7fba00", "#00a4ef", "#ffb900"]);
  });

  it("English copy", () => {
    view(org(), "", null, "en");
    expect(screen.getByRole("link", { name: "Sign in with Microsoft" })).toBeInTheDocument();
    expect(screen.getByTestId("signin-hints")).toHaveTextContent("work or school account");
  });

  it("door 2 starts closed with no fields in the tree, opens on click and focuses the identifier (§15 #8 #9 #11)", async () => {
    view(org());
    const disclosure = screen.getByTestId("login-disclosure");
    expect(disclosure).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByLabelText("Parola")).toBeNull();
    expect(screen.queryByTestId("forgot-password")).toBeNull();
    fireEvent.click(disclosure);
    expect(disclosure).toHaveAttribute("aria-expanded", "true");
    await waitFor(() => expect(document.activeElement).toBe(screen.getByTestId("login-identifier")));
    expect(screen.getByTestId("forgot-password")).toHaveAttribute("href", "/reset-password");
    expect(screen.getByTestId("login-submit")).not.toHaveAttribute("data-primary");
    expect(screen.getByTestId("login-identifier")).toHaveAttribute("placeholder", "ad.soyad");
  });

  it("?method=local opens door 2; local sign-in hidden for everyone removes the disclosure (§15 #10)", () => {
    const a = view(org({ local: false }));
    expect(screen.queryByTestId("login-disclosure")).toBeNull();
    a.unmount();
    view(org({ local: false }), "method=local");
    expect(screen.getByTestId("login-disclosure")).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("login-identifier")).toBeInTheDocument();
    expect(screen.queryByTestId("forgot-password")).toBeNull();
  });

  it("Microsoft off: no Microsoft link, no disclosure, the open form is primary, the ask-an-administrator line (§15 #5)", () => {
    view(org({ ms: false }));
    expect(screen.queryByTestId("login-sso-microsoft")).toBeNull();
    expect(screen.queryByTestId("login-disclosure")).toBeNull();
    expect(screen.getByTestId("login-submit")).toHaveAttribute("data-primary", "true");
    expect(screen.getByTestId("login-no-account")).toHaveTextContent("Hesabınız yoksa bir yöneticiye başvurun.");
  });

  it("backend unreachable: the form is open and the offline notice shows", () => {
    view(null);
    expect(screen.getByTestId("signin-offline")).toBeInTheDocument();
    expect(screen.getByTestId("login-identifier")).toBeInTheDocument();
  });

  it.each([
    ["tenant", "Bu hesapla giriş yapılamıyor."],
    ["unavailable", "Microsoft'a şu anda ulaşılamıyor."],
    ["signup_closed", "Hesabınız yok."],
    ["invite_expired", "Davetin süresi doldu."],
    ["invite_invalid", "Bu davet artık geçerli değil."],
    ["invite_mismatch", "Davet başka bir adres için."],
    ["failed", "Giriş yapılamadı."],
  ])("?error=%s renders its alert and takes focus (§15 #15)", async (code, title) => {
    view(org(), `error=${code}&ref=7F3A-21C`);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(title);
    await waitFor(() => expect(document.activeElement).toBe(screen.getByTestId("signin-error-focus")));
  });

  it("failed and an unknown code render byte-identical text; only the ref is shown (§15 #16)", () => {
    const a = view(org(), "error=failed&ref=7F3A-21C");
    const one = screen.getByRole("alert").textContent;
    a.unmount();
    view(org(), "error=nonsense&ref=7F3A-21C");
    expect(screen.getByRole("alert").textContent).toBe(one);
    expect(one).toContain("7F3A-21C");
  });

  it("tenant and mismatch actions restart with select_account (+ the invite's login_hint) (§15 #17)", () => {
    const a = view(org(), "error=tenant&next=/x");
    const u = new URL(screen.getByTestId("signin-try-another").getAttribute("href")!, "http://h");
    expect(u.searchParams.get("prompt")).toBe("select_account");
    expect(u.searchParams.get("next")).toBe("/x");
    a.unmount();
    const invite: InviteState = { state: "valid", token: "tok_12345678", inviter: "Fatih Demir", role: "Planlamacı", masked: "ay•••@ornek.edu.tr", loginHint: "ayse.yilmaz@ornek.edu.tr", daysLeft: 27 };
    view(org(), "error=invite_mismatch&invite=tok_12345678&invited_masked=ay•••@ornek.edu.tr&signed_in=ba•••@ornek.edu.tr", invite);
    expect(screen.getByRole("alert")).toHaveTextContent("ay•••@ornek.edu.tr");
    const m = new URL(screen.getByTestId("signin-switch-account").getAttribute("href")!, "http://h");
    expect(m.searchParams.get("prompt")).toBe("select_account");
    expect(m.searchParams.get("login_hint")).toBe("ayse.yilmaz@ornek.edu.tr");
    expect(m.searchParams.get("invite")).toBe("tok_12345678");
  });

  it("cancelled is a status, not an alert, and does not take focus (§15 #18)", () => {
    view(org(), "error=cancelled");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByTestId("signin-notice-cancelled")).toHaveAttribute("role", "status");
    expect(document.activeElement).toBe(document.body);
  });

  it("?reason=expired: neutral notice; next survives on both doors; an external next is dropped (§15 #19)", () => {
    const a = view(org(), "reason=expired&next=/timetable&method=local");
    expect(screen.getByTestId("login-session-notice")).toHaveTextContent("Oturumunuzun süresi doldu.");
    expect(screen.getByTestId("login-sso-microsoft").getAttribute("href")).toContain("next=%2Ftimetable");
    a.unmount();
    view(org(), "next=//evil.example");
    expect(screen.getByTestId("login-sso-microsoft").getAttribute("href")).toBe("/api/v1/auth/sso/entra/start");
  });

  it("maintenance and the login message show with the doors still usable (§15 #20)", () => {
    view(org({ maintenance_mode: true, maintenance_message: "Rezervasyonlar 18:00'e kadar durdu.", login_message: "Personel hesabınızı kullanın." }));
    expect(screen.getByTestId("login-maintenance")).toHaveTextContent("Rezervasyonlar bakımda.");
    expect(screen.getByTestId("login-maintenance")).toHaveTextContent("18:00");
    expect(screen.getByTestId("login-message")).toHaveTextContent("Personel hesabınızı kullanın.");
    expect(screen.getByTestId("login-sso-microsoft")).toBeInTheDocument();
  });

  it("invite: banner with inviter, role, masked address and days; no disclosure; start link carries invite + login_hint (§15 #21)", () => {
    const invite: InviteState = { state: "valid", token: "tok_12345678", inviter: "Fatih Demir", role: "Planlamacı", masked: "ay•••@ornek.edu.tr", loginHint: "ayse.yilmaz@ornek.edu.tr", daysLeft: 27 };
    view(org(), "invite=tok_12345678", invite);
    const banner = screen.getByTestId("signin-invite");
    expect(banner).toHaveTextContent("Fatih Demir sizi SmartSched'e davet etti.");
    expect(within(banner).getByText(/Planlamacı/)).toHaveTextContent("ay•••@ornek.edu.tr · 27 gün geçerli");
    expect(screen.queryByTestId("login-disclosure")).toBeNull();
    const u = new URL(screen.getByTestId("login-sso-microsoft").getAttribute("href")!, "http://h");
    expect(u.searchParams.get("invite")).toBe("tok_12345678");
    expect(u.searchParams.get("login_hint")).toBe("ayse.yilmaz@ornek.edu.tr");
    for (const el of [...screen.queryAllByRole("link"), ...screen.queryAllByRole("button")]) expect(el.textContent ?? "").not.toMatch(SIGNUP);
  });

  it("an expired invite token reads as the invite_expired error", () => {
    view(org(), "invite=tok_12345678", { state: "expired", token: "tok_12345678" });
    expect(screen.getByRole("alert")).toHaveTextContent("Davetin süresi doldu.");
  });

  it("self sign-up off replaces hint 2 with ask-an-administrator", () => {
    view(org({ self: false }));
    expect(screen.getByTestId("signin-hints")).toHaveTextContent("Hesabınız yoksa bir yöneticiye başvurun.");
    expect(screen.getByTestId("signin-hints")).not.toHaveTextContent("Standart kullanıcı");
  });

  it("remembers the password door and says so", () => {
    view(org(), "", null, "tr", true);
    expect(screen.getByTestId("login-disclosure")).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("login-last-method")).toHaveTextContent("Son girişiniz: kullanıcı adı ve parola");
  });

  it("a 401 shows one generic alert, marks both fields invalid, clears the password and keeps the identifier (§15 #12)", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "x" }), { status: 401, headers: { "content-type": "application/json" } }));
    view(org(), "method=local");
    fireEvent.change(screen.getByTestId("login-identifier"), { target: { value: "ayilmaz" } });
    fireEvent.change(screen.getByTestId("login-password"), { target: { value: "wrong-one" } });
    await act(async () => {
      fireEvent.submit(screen.getByTestId("login-form"));
    });
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Kullanıcı adı, e-posta veya parola yanlış."));
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.getByTestId("login-identifier")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByTestId("login-password")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByTestId("login-password")).toHaveValue("");
    expect(screen.getByTestId("login-identifier")).toHaveValue("ayilmaz");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/auth/login", expect.objectContaining({ method: "POST" }));
  });

  it("a 429 shows the minutes and disables submit; a network failure the offline string (§15 #14)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response("{}", { status: 429, headers: { "retry-after": "125" } }));
    view(org(), "method=local");
    fireEvent.change(screen.getByTestId("login-identifier"), { target: { value: "ayilmaz" } });
    fireEvent.change(screen.getByTestId("login-password"), { target: { value: "x" } });
    await act(async () => {
      fireEvent.submit(screen.getByTestId("login-form"));
    });
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Çok fazla deneme. 3 dakika sonra tekrar deneyin."));
    expect(screen.getByTestId("login-submit")).toBeDisabled();
  });

  it("offline submit", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(new TypeError("Failed to fetch"));
    view(org(), "method=local");
    fireEvent.change(screen.getByTestId("login-identifier"), { target: { value: "ayilmaz" } });
    fireEvent.change(screen.getByTestId("login-password"), { target: { value: "x" } });
    await act(async () => {
      fireEvent.submit(screen.getByTestId("login-form"));
    });
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Sunucuya ulaşılamıyor."));
  });

  it("labels exactly one field as the password; the toggle names its action and controls it", () => {
    view(org(), "method=local", null, "en");
    expect(screen.getByLabelText("Password", { exact: true })).toBe(screen.getByTestId("login-password"));
    expect(screen.getByRole("button", { name: "Show password" })).toHaveAttribute("aria-controls", "password");
    // placeholders never repeat their label (§15 #27)
    expect(screen.getByTestId("login-identifier").getAttribute("placeholder")).not.toBe("Username or e-mail");
  });

  it("the Microsoft button ignores a second click while it hands over", () => {
    view(org());
    const ms = screen.getByTestId("login-sso-microsoft");
    const first = fireEvent.click(ms);
    expect(first).toBe(true);
    expect(ms).toHaveAttribute("aria-disabled", "true");
    expect(fireEvent.click(ms)).toBe(false); // default prevented
  });

  it("shows the backend version in the footer and a TR/EN radiogroup", () => {
    view(org());
    expect(screen.getByTestId("app-version")).toHaveTextContent("v1.4.0");
    expect(screen.getByRole("radiogroup", { name: "Dil" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Türkçe" })).toHaveAttribute("aria-checked", "true");
  });
});
