import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { MyChannels } from "@/components/channels/my-channels";
import { IdentityStatusCell, MethodCell } from "@/components/admin/users-admin-identity";
import { SsoSettings } from "./sso-settings";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/components/bookings/use-booking-format", () => ({
  useBookingFormat: () => ({
    short: (d: string) => d,
    dateTime: (d: string | null | undefined) => d ?? "",
    long: (d: string) => d,
    weekday: (d: string) => d,
    time: (d: string) => d,
  }),
}));
vi.mock("@/lib/permissions", async (orig) => ({
  ...(await orig<typeof import("@/lib/permissions")>()),
  usePermissions: () => ({
    perms: [],
    can: () => false,
    canAll: () => false,
    userId: 1,
    loading: false,
    departmentId: null,
  }),
}));
vi.mock("@/lib/api/crbs", () => ({
  useRoles: () => ({ data: undefined }),
  useDepartments: () => ({ data: [] }),
  crbs: { org: { i18n: () => Promise.reject(new Error("x")) } },
}));

type Route = (url: string, init?: RequestInit) => { status: number; body?: unknown } | undefined;
function mockFetch(route: Route) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const r = route(url, init) ?? {
      status: 404,
      body: { detail: "not found" },
    };
    return new Response(r.body === undefined ? null : JSON.stringify(r.body), {
      status: r.status,
      headers: { "content-type": "application/json" },
    });
  });
}

function wrap(node: ReactNode, locale: "tr" | "en" = "tr") {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: { queries: { retry: false } },
        })
      }
    >
      <I18nProvider initialLocale={locale}>{node}</I18nProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("MyChannels (Profile › Bağlı kanallar)", () => {
  const mine = {
    available: [
      {
        kind: "telegram",
        label_tr: "Telegram",
        label_en: "Telegram",
        link: "telegram_deeplink",
        content_mode: "link_only",
      },
      {
        kind: "whatsapp",
        label_tr: "WhatsApp",
        label_en: "WhatsApp",
        link: "phone_code",
        content_mode: "link_only",
        opt_in_tr: "Kurumun WhatsApp hesabından bildirim almayı kabul ediyorum.",
        opt_in_en: "I agree.",
      },
      {
        kind: "teams",
        label_tr: "Microsoft Teams (bölüm kanalı)",
        label_en: "Teams",
        link: "department",
        content_mode: "link_only",
        department_target: false,
      },
    ],
    linked: [
      {
        id: 7,
        kind: "telegram",
        display_hint: "@ayse",
        label: null,
        status: "active",
        last_error: null,
        verified_at: null,
        created_at: null,
      },
    ],
  };

  it("lists e-mail and the linked address with a status word, offers the switched-on channels, explains departments", async () => {
    mockFetch((url) => (url.startsWith("/api/v1/me/channels") ? { status: 200, body: mine } : undefined));
    wrap(<MyChannels email="ayse@ornek.edu.tr" />);
    await screen.findByTestId("linked-telegram");
    expect(screen.getByText("ayse@ornek.edu.tr")).toBeInTheDocument();
    expect(screen.getByTestId("linked-telegram")).toHaveTextContent("@ayse");
    expect(screen.getByTestId("linked-telegram")).toHaveTextContent("Etkin");
    expect(screen.getByTestId("linker-whatsapp")).toBeInTheDocument();
    expect(screen.getByText(/bölümünüz için henüz kanal tanımlanmadı/)).toBeInTheDocument();
  });

  it("WhatsApp needs the institution-naming opt-in before a code is sent", async () => {
    const f = mockFetch((url, init) => {
      if (url.startsWith("/api/v1/me/channels/whatsapp/link"))
        return {
          status: 201,
          body: {
            display_hint: "+90 532 *** ** 33",
            expires_at: null,
            sender: "whatsapp",
          },
        };
      if (url.startsWith("/api/v1/me/channels") && (!init || init.method === "GET" || !init.method)) return { status: 200, body: mine };
      return undefined;
    });
    wrap(<MyChannels email={null} />);
    fireEvent.click(await screen.findByTestId("channel-link-whatsapp"));
    fireEvent.change(screen.getByTestId("whatsapp-phone"), {
      target: { value: "0532 111 22 33" },
    });
    fireEvent.click(screen.getByTestId("whatsapp-send-code"));
    expect(await screen.findByText("Bu numaraya mesaj almak için onay kutusunu işaretleyin.")).toBeInTheDocument();
    expect(f.mock.calls.some(([u]) => String(u).includes("/whatsapp/link"))).toBe(false);
    fireEvent.click(screen.getByTestId("whatsapp-consent"));
    fireEvent.click(screen.getByTestId("whatsapp-send-code"));
    expect(await screen.findByText("+90 532 *** ** 33 numarasına bir kod gönderdik.")).toBeInTheDocument();
    const call = f.mock.calls.find(([u]) => String(u).includes("/whatsapp/link"))!;
    expect(JSON.parse(String(call[1]!.body))).toEqual({
      phone: "0532 111 22 33",
      consent: true,
    });
  });
});

const CONFIG = {
  enabled: false,
  configured: true,
  tenant_id: "00000000-0000-4000-8000-000000000001",
  client_id: "00000000-0000-4000-8000-000000000002",
  client_secret_set: true,
  from_environment: [],
  authority: null,
  redirect_uri: "https://panel.ornek.edu.tr/api/v1/auth/sso/entra/callback",
  public_url_source: "setting",
  self_signup: true,
  domain_hint: "ornek.edu.tr",
  default_role: { id: 2, code: "TEACHER", name: "Öğretim elemanı" },
  oidc_only_non_admins: false,
  role_mapping_enabled: false,
  allow_admin_mapping: false,
  invite_days: 30,
  break_glass_admins: 0,
  updated_at: "2026-10-16T00:00:00",
};

describe("SsoSettings (Settings › Microsoft ile giriş)", () => {
  it("never shows the secret: only 'Ayarlandı', and Değiştir reveals an empty write-only field", async () => {
    mockFetch((url) => (url.endsWith("/auth/sso/admin/entra") ? { status: 200, body: CONFIG } : url.endsWith("/mappings") ? { status: 200, body: [] } : undefined));
    wrap(<SsoSettings />);
    expect(await screen.findByTestId("sso-secret-set")).toHaveTextContent("Ayarlandı");
    expect(screen.queryByTestId("sso-secret")).toBeNull();
    fireEvent.click(screen.getByTestId("sso-secret-replace"));
    expect(screen.getByTestId("sso-secret")).toHaveValue("");
    expect(screen.getByTestId("sso-secret")).toHaveAttribute("type", "password");
    expect(screen.getByTestId("sso-redirect")).toHaveValue(CONFIG.redirect_uri);
  });

  it("shows the backend's 422 when enabling is refused, and the break-glass rule on a 409", async () => {
    mockFetch((url, init) => {
      if (url.endsWith("/auth/sso/admin/entra") && init?.method === "PUT") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        if ("enabled" in body)
          return {
            status: 422,
            body: {
              detail: {
                code: "no_public_url",
                en: "needs the public URL",
                tr: "genel adres gerekli",
              },
            },
          };
        return {
          status: 409,
          body: { detail: { code: "break_glass", en: "x", tr: "x" } },
        };
      }
      if (url.endsWith("/auth/sso/admin/entra")) return { status: 200, body: CONFIG };
      if (url.endsWith("/mappings")) return { status: 200, body: [] };
      return undefined;
    });
    wrap(<SsoSettings />);
    fireEvent.click(await screen.findByTestId("sso-enabled"));
    await waitFor(() => expect(screen.getByTestId("sso-error")).toHaveTextContent("genel adres gerekli"));
    fireEvent.click(screen.getByTestId("sso-oidc-only"));
    await waitFor(() => expect(screen.getByTestId("sso-error")).toHaveTextContent("acil durum hesabı"));
  });
});

describe("Users identity cells", () => {
  it("status dot + word with the days left and the inviter; method with the Microsoft mark", () => {
    wrap(
      <>
        <IdentityStatusCell
          view={{
            tone: "pending",
            word: "invited",
            daysLeft: 27,
            expiredAt: null,
          }}
          inviterName="Fatih Demir"
        />
        <MethodCell m="microsoftInvite" />
      </>,
    );
    expect(screen.getByTestId("identity-status")).toHaveTextContent("Davet bekliyor");
    expect(screen.getByTestId("identity-status")).toHaveTextContent("27 gün kaldı · Fatih Demir");
    expect(screen.getByTestId("identity-method")).toHaveTextContent("Microsoft · davet");
    expect(screen.getByTestId("microsoft-logo")).toBeInTheDocument();
  });
});
