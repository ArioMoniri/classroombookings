/** Ayarlar › Genel › E-posta bildirimleri (RF-11): booking reminder lead time and the new-device sign-in mail,
 *  both organisation settings of `PUT /org/settings` (backend app/services/mail_senders.py). */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { MailNoticesCard } from "./mail-notices";

vi.mock("sonner", async (orig) => ({ ...(await orig<typeof import("sonner")>()), toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));

let state: Record<string, unknown> = { reminder_lead_hours: 24, new_device_sign_in_mail: true };
let puts: Record<string, unknown>[] = [];

function renderIt(locale: "tr" | "en" = "tr") {
  puts = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
      if (String(url).includes("/org/settings") && init?.method === "PUT") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        puts.push(body);
        state = { ...state, ...body };
        return json(state);
      }
      if (String(url).includes("/org/settings")) return json(state);
      return json({});
    }),
  );
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale={locale}>
        <MailNoticesCard />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  state = { reminder_lead_hours: 24, new_device_sign_in_mail: true };
});

describe("MailNoticesCard", () => {
  it("shows the stored lead time and saves a new one in hours", async () => {
    renderIt();
    expect(await screen.findByText("E-posta bildirimleri")).toBeInTheDocument();
    const hours = await screen.findByLabelText("Hatırlatma: başlangıçtan kaç saat önce");
    await waitFor(() => expect(hours).toHaveValue(24));
    expect(hours).toHaveAttribute("inputmode", "numeric");
    fireEvent.change(hours, { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));
    await waitFor(() => expect(puts).toEqual([{ reminder_lead_hours: 2, new_device_sign_in_mail: true }]));
    expect(screen.getByRole("button", { name: "Kaydet" })).toHaveFocus();
  });

  it("refuses a lead time outside 0-336 in Turkish and keeps the focus on the field", async () => {
    renderIt();
    const hours = await screen.findByLabelText("Hatırlatma: başlangıçtan kaç saat önce");
    fireEvent.change(hours, { target: { value: "400" } });
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));
    expect(await screen.findByText("0 ile 336 arasında bir saat girin (0: hatırlatma yok).")).toBeInTheDocument();
    expect(hours).toHaveFocus();
    expect(puts).toEqual([]);
  });

  it("switches the new-device mail off for the organisation", async () => {
    renderIt("en");
    const sw = await screen.findByRole("switch", { name: "Sign-in from a new device e-mail" });
    await waitFor(() => expect(sw).toBeChecked());
    fireEvent.click(sw);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(puts).toEqual([{ reminder_lead_hours: 24, new_device_sign_in_mail: false }]));
  });
});
