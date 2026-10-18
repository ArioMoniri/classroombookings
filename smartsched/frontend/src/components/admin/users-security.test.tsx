// AUX-08 (docs/design/v3/auth.md §7) + AU-15: Admin › Kullanıcılar sign-in security — the account kinds, the SSO
// explanation instead of buttons, the reset dialog's client checks (reason ≥ 10, identity check, the compromise chip
// hides "koru"), the reset-link refusals that offer the on-screen code, and "Oturumları sonlandır" with a confirm.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { I18nProvider } from "@/lib/i18n/provider";
import { matchesMfaFilter, mfaListState, resetProblem, securityAccount, useUserSecurity, type SecurityUser } from "./users-security";

const toasts = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: toasts }));

beforeAll(() => {
  if (!document.elementFromPoint) Object.defineProperty(document, "elementFromPoint", { value: () => null, configurable: true });
});

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const SUMMARY = { user_id: 7, account_type: "local", totp_enabled: true, totp_enabled_at: "2026-10-01T09:00:00", recovery_codes_remaining: 8, passkeys: [{ name: "iCloud", created_at: "2026-10-02T09:00:00", last_used_at: null }, { name: "1Password", created_at: "2026-10-03T09:00:00", last_used_at: null }], trusted_devices: 1, locked_until: null, can_reset_mfa: true, can_send_reset_link: true };
let calls: { key: string; body: unknown }[];
let routes: Record<string, (b: unknown) => Response>;
beforeEach(() => {
  calls = [];
  Object.values(toasts).forEach((f) => f.mockReset());
  routes = { "GET /api/v1/admin/users/7/mfa": () => res(200, SUMMARY) };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url}`;
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ key, body });
      return routes[key]?.(body) ?? res(404, {});
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const LOCAL: SecurityUser = { id: 7, name: "Ayşe Yılmaz", email: "ayse@ornek.edu.tr", account: "local", mfa: "on", role: "PLANNER", lastLoginAt: null };
const SSO: SecurityUser = { id: 8, name: "Mehmet Kaya", email: "mehmet@ornek.edu.tr", account: "sso", providerName: "Microsoft" };

function Harness({ user, meId = 1, onShowCode }: { user: SecurityUser; meId?: number; onShowCode?: (id: number) => void }) {
  const { menuItems, block, dialogs } = useUserSecurity({ meId, onShowCode });
  return (
    <>
      <DropdownMenu defaultOpen>
        <DropdownMenuTrigger>menu</DropdownMenuTrigger>
        <DropdownMenuContent>{menuItems(user)}</DropdownMenuContent>
      </DropdownMenu>
      <div data-testid="sheet">{block(user)}</div>
      {dialogs}
    </>
  );
}
const wrap = (ui: React.ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">{ui}</I18nProvider>
    </QueryClientProvider>,
  );

describe("model", () => {
  it("maps the method view to the account kind and reads the list state", () => {
    expect(securityAccount("microsoft")).toBe("sso");
    expect(securityAccount("microsoftInvite")).toBe("sso");
    expect(securityAccount("ldap")).toBe("ldap");
    expect(securityAccount("binding")).toBe("local");
    expect(mfaListState({ mfa_state: "pending" })).toBe("pending");
    expect(mfaListState({})).toBeNull();
    expect(matchesMfaFilter(null, "")).toBe(true);
    expect(matchesMfaFilter("on", "off")).toBe(false);
  });
  it("needs 10–500 characters and an identity check", () => {
    expect(resetProblem("kısa neden", "in_person")).toBeNull();
    expect(resetProblem("9 harfli.", "in_person")).toBe("reason");
    expect(resetProblem("telefonunu kaybetti", "")).toBe("identity");
  });
});

describe("menu and edit-sheet block", () => {
  it("SSO: one explanation, no reset or link button; 'Oturumları sonlandır' stays", async () => {
    wrap(<Harness user={SSO} />);
    expect(await screen.findByTestId("user-security-note-8")).toHaveTextContent("Bu hesap Microsoft ile giriş yapıyor.");
    expect(screen.queryByTestId("user-reset-mfa-8")).toBeNull();
    expect(screen.queryByTestId("user-send-link-8")).toBeNull();
    expect(screen.getByTestId("user-end-sessions-8")).toBeInTheDocument();
    expect(screen.queryByTestId("block-reset-mfa")).toBeNull();
    expect(screen.getByTestId("block-note")).toHaveTextContent("Microsoft");
  });

  it("own row: the link to Profil instead of the reset; no 'Oturumları sonlandır'", async () => {
    wrap(<Harness user={LOCAL} meId={7} />);
    expect(await screen.findByTestId("user-own-security-7")).toHaveTextContent("Profil › Giriş ve güvenlik");
    expect(screen.queryByTestId("user-reset-mfa-7")).toBeNull();
    expect(screen.queryByTestId("user-end-sessions-7")).toBeNull();
  });

  it("local: the edit-sheet block shows 'Açık · uygulama + 2 geçiş anahtarı'", async () => {
    wrap(<Harness user={LOCAL} />);
    await waitFor(() => expect(screen.getByTestId("user-security-status")).toHaveTextContent("Açık · uygulama + 2 geçiş anahtarı"));
  });
});

describe("2FA'yı sıfırla", () => {
  it("refuses a 9-character reason and a missing identity check without calling the API; the compromise chip hides 'koru'", async () => {
    routes["POST /api/v1/admin/users/7/mfa/reset"] = () => res(200, { user_id: 7, signed_out: true });
    wrap(<Harness user={LOCAL} />);
    fireEvent.click(await screen.findByTestId("block-reset-mfa"));
    expect(await screen.findByTestId("reset-mfa-dialog")).toHaveTextContent("Ayşe Yılmaz için iki aşamalı doğrulama sıfırlansın mı?");
    expect(await screen.findByTestId("reset-keep-passkeys")).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("reset-reason"), { target: { value: "9 harfli." } });
    fireEvent.click(screen.getByTestId("reset-confirm"));
    expect(await screen.findByTestId("reset-reason-error")).toHaveTextContent("en az 10 karakter");
    expect(screen.getByTestId("reset-reason")).toHaveAttribute("aria-invalid", "true");
    fireEvent.click(screen.getByTestId("reset-chip-compromised"));
    expect(screen.queryByTestId("reset-keep-passkeys")).toBeNull();
    expect((screen.getByTestId("reset-reason") as HTMLTextAreaElement).value).toBe("Hesap ele geçirilmiş olabilir");
    fireEvent.click(screen.getByTestId("reset-confirm"));
    expect(await screen.findByTestId("reset-identity-error")).toBeInTheDocument();
    expect(calls.some((c) => c.key.startsWith("POST"))).toBe(false);
    fireEvent.change(screen.getByTestId("reset-identity"), { target: { value: "video_call" } });
    fireEvent.click(screen.getByTestId("reset-confirm"));
    await waitFor(() => expect(calls.find((c) => c.key === "POST /api/v1/admin/users/7/mfa/reset")?.body).toEqual({ reason: "Hesap ele geçirilmiş olabilir", identity_check: "video_call", keep_passkeys: false }));
    expect(toasts.success).toHaveBeenCalledWith("Ayşe Yılmaz için iki aşamalı doğrulama sıfırlandı. Kişiye e-posta gönderildi.");
  });

  it("maps own_account to its sentence", async () => {
    routes["POST /api/v1/admin/users/7/mfa/reset"] = () => res(409, { detail: { code: "own_account" } });
    wrap(<Harness user={LOCAL} />);
    fireEvent.click(await screen.findByTestId("block-reset-mfa"));
    fireEvent.change(await screen.findByTestId("reset-reason"), { target: { value: "telefonunu değiştirdi" } });
    fireEvent.change(screen.getByTestId("reset-identity"), { target: { value: "in_person" } });
    fireEvent.click(screen.getByTestId("reset-confirm"));
    expect(await screen.findByTestId("reset-error")).toHaveTextContent("Kendi hesabınız için Profil");
  });
});

describe("Parola sıfırlama bağlantısı gönder", () => {
  it("masks the address; no_email offers 'Kodu göster'", async () => {
    const onShowCode = vi.fn();
    routes["POST /api/v1/admin/users/7/password-reset-link"] = () => res(409, { detail: { code: "no_email" } });
    wrap(<Harness user={LOCAL} onShowCode={onShowCode} />);
    fireEvent.click(await screen.findByTestId("block-send-link"));
    const dlg = await screen.findByTestId("reset-link-dialog");
    expect(dlg).toHaveTextContent("ay•••@ornek.edu.tr adresine 24 saat geçerli bir bağlantı gönderilir.");
    fireEvent.click(screen.getByTestId("reset-link-send"));
    expect(await screen.findByTestId("reset-link-error")).toHaveTextContent("e-posta adresi yok");
    fireEvent.click(screen.getByTestId("reset-link-show-code"));
    expect(onShowCode).toHaveBeenCalledWith(7);
  });

  it("429 names the minutes", async () => {
    routes["POST /api/v1/admin/users/7/password-reset-link"] = () => res(429, { detail: { code: "rate_limited", retry_after: 300 } });
    wrap(<Harness user={LOCAL} />);
    fireEvent.click(await screen.findByTestId("block-send-link"));
    fireEvent.click(await screen.findByTestId("reset-link-send"));
    expect(await screen.findByTestId("reset-link-error")).toHaveTextContent("5 dakika sonra");
  });
});

describe("Oturumları sonlandır (AU-15)", () => {
  it("confirms, then posts the revoke", async () => {
    routes["POST /api/v1/admin/users/8/sessions/revoke"] = () => res(200, { user_id: 8, revoked: 3, signed_out: true });
    wrap(<Harness user={SSO} />);
    fireEvent.click(await screen.findByTestId("block-end-sessions"));
    expect(await screen.findByTestId("end-sessions-dialog")).toHaveTextContent("Parolası ve iki aşamalı doğrulaması değişmez.");
    expect(calls.some((c) => c.key.includes("sessions/revoke"))).toBe(false);
    fireEvent.click(screen.getByTestId("end-sessions-confirm"));
    await waitFor(() => expect(toasts.success).toHaveBeenCalledWith("Mehmet Kaya için oturumlar sonlandırıldı (3)."));
  });
});
