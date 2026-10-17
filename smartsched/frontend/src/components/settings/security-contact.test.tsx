/** Ayarlar › Genel › Güvenlik iletişimi (security follow-up wave3-sec2): the institution's security.txt contact. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { SecurityContactCard } from "./security-contact";

vi.mock("sonner", async (orig) => ({ ...(await orig<typeof import("sonner")>()), toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));

const UNSET = { contact_email: null, contact_url: null, policy_url: null, preferred_languages: "tr, en", configured: false, warning: { code: "security_contact_unset", message_tr: "Güvenlik iletişim adresi ayarlanmadı", message_en: "The security contact address is not set" }, last_change: null };
let state: Record<string, unknown> = UNSET;
let role = "ADMIN";
let refuse: Record<string, unknown> | null = null;
let puts: Record<string, unknown>[] = [];

function mockApi() {
  puts = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const u = String(url);
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
      if (u.includes("/auth/me")) return json({ id: 1, role, permissions: [] });
      if (u.includes("/admin/security-contact") && init?.method === "PUT") {
        if (refuse) return json({ detail: refuse }, 422);
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        puts.push(body);
        state = { ...body, configured: true, warning: null, last_change: { actor: "Yönetici Ayşe", at: "2026-10-17T19:30:00+00:00" } };
        return json(state);
      }
      if (u.includes("/admin/security-contact")) return json(state);
      return json({});
    }),
  );
}

function renderIt(locale: "tr" | "en" = "tr") {
  mockApi();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale={locale}>
        <SecurityContactCard />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  state = UNSET;
  role = "ADMIN";
  refuse = null;
});

describe("SecurityContactCard", () => {
  it("warns while no contact is set and saves the contact", async () => {
    renderIt();
    expect(await screen.findByText("Güvenlik iletişimi")).toBeInTheDocument();
    expect(await screen.findByText("Güvenlik iletişim adresi ayarlanmadı")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Güvenlik iletişim e-postası"), { target: { value: "bilgi-guvenligi@uni.edu.tr" } });
    fireEvent.change(screen.getByLabelText(/Politika sayfası/), { target: { value: "https://uni.edu.tr/politika" } });
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]).toMatchObject({ contact_email: "bilgi-guvenligi@uni.edu.tr", policy_url: "https://uni.edu.tr/politika", preferred_languages: "tr, en" });
    expect(await screen.findByText(/Son değişiklik: Yönetici Ayşe,/)).toBeInTheDocument();
    expect(screen.queryByText("Güvenlik iletişim adresi ayarlanmadı")).not.toBeInTheDocument();
  });

  it("shows the server's refusal next to the named field and focuses it", async () => {
    refuse = { code: "invalid_security_contact", field: "contact_url", message_tr: "İletişim sayfası https:// ile başlayan bir adres olmalı.", message_en: "The contact page must be an https:// URL." };
    renderIt();
    fireEvent.change(await screen.findByLabelText("Güvenlik iletişim e-postası"), { target: { value: "a@uni.edu.tr" } });
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));
    expect(await screen.findByText("İletişim sayfası https:// ile başlayan bir adres olmalı.")).toBeInTheDocument();
    await waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText(/İletişim sayfası/)));
  });

  it("is English in English", async () => {
    renderIt("en");
    expect(await screen.findByText("Security contact")).toBeInTheDocument();
    expect(await screen.findByText("The security contact address is not set")).toBeInTheDocument();
  });

  it("renders nothing for a non-administrator", async () => {
    role = "TEACHER";
    renderIt();
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText("Güvenlik iletişimi")).not.toBeInTheDocument();
  });
});
