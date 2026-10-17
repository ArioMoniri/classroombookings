/** Backend asks batch 3 in Admin › KVKK: retention 422 `errors[]` at their fields; the queue's "Tümü" (`status=all`). */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

const state = vi.hoisted(() => ({ calls: [] as { path: string; method: string; query?: Record<string, unknown>; body?: unknown }[], putError: null as unknown }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return {
    ...real,
    request: async (path: string, opts: { method?: string; body?: unknown; query?: Record<string, unknown> } = {}) => {
      const method = opts.method ?? "GET";
      state.calls.push({ path, method, query: opts.query, body: opts.body });
      if (path === "/admin/retention") return [policy("audit", 365), policy("booking", 365)];
      if (path.startsWith("/admin/retention/") && method === "PUT") throw new real.HttpError(422, "422", { detail: state.putError });
      if (path === "/admin/dsr") {
        const status = opts.query?.status;
        return status === "all" ? [dsr(1, "OPEN"), dsr(2, "DONE"), dsr(3, "REFUSED")] : status === "open" ? [dsr(1, "OPEN")] : [];
      }
      throw new Error(`unexpected ${method} ${path}`);
    },
  };
});

import { DsrQueue } from "./dsr-queue";
import { RetentionEditor } from "./retention-editor";

function policy(data_class: string, days: number) {
  return { data_class, label_tr: data_class === "audit" ? "Denetim kaydı" : "Rezervasyonlar", label_en: data_class, retain_days: days, floor_days: 365, action: data_class === "booking" ? "anonymise" : "delete", enabled: false, legal_hold: false, legal_hold_reason: null, last_run_at: null, last_result: null, updated_at: null };
}
function dsr(id: number, status: string) {
  return { id, kind: "info", status, created_at: "2026-10-10T09:00:00", due_at: "2026-11-09T09:00:00", overdue: false, days_left: 24, subject: `Kişi ${id}`, downloadable: false };
}
const fieldError = (code: string, field: string, en: string, tr: string, extra: Record<string, unknown> = {}) => ({ code, field, message: en, message_en: en, message_tr: tr, ...extra });

function renderIt(ui: React.ReactNode, locale: "en" | "tr" = "tr") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale={locale}>{ui}</I18nProvider>
    </QueryClientProvider>,
  );
}

describe("retention 422 field errors", () => {
  beforeEach(() => {
    state.calls = [];
    toast.success.mockReset();
  });

  it("shows each errors[] entry under its field, in the reader's words, until that field is edited", async () => {
    const days = fieldError("retain_days", "retain_days", "retain_days: a whole number of days between 365 and 36500", "saklama süresi: 365 ile 36500 arasında tam gün sayısı", { floor_days: 365, max_days: 36500 });
    state.putError = { ...days, errors: [days, fieldError("legal_hold_reason", "legal_hold_reason", "a legal hold needs a reason", "yasal saklama için gerekçe yazın")] };
    renderIt(<RetentionEditor />);
    const card = await screen.findByTestId("retention-audit");
    const input = within(card).getByTestId("retention-days-audit");
    await userEvent.clear(input);
    await userEvent.type(input, "40000");
    await userEvent.click(within(card).getByTestId("retention-save-audit"));
    const err = await within(card).findByTestId("retention-field-error-audit-retain_days");
    expect(err).toHaveTextContent("365 ile 36500 gün arasında.");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input.getAttribute("aria-describedby")).toBe(err.id);
    expect(input).toHaveAttribute("max", "36500");
    // the reason error has no visible reason field (hold is off): it is shown at the legal hold switch
    expect(within(card).getByTestId("retention-field-error-audit-legal_hold")).toHaveTextContent("yasal saklama için gerekçe yazın");
    expect(within(card).queryByTestId("retention-error-audit")).toBeNull();
    await userEvent.type(input, "0");
    expect(within(card).queryByTestId("retention-field-error-audit-retain_days")).toBeNull();
  });

  it("action: the server's sentence and the allowed actions; an unknown class is the row's message", async () => {
    const action = fieldError("action", "action", "bookings are anonymised, not deleted (room usage statistics stay)", "rezervasyonlar silinmez, anonimleştirilir (kullanım istatistikleri korunur)", { allowed: ["anonymise"] });
    state.putError = { ...action, errors: [action] };
    renderIt(<RetentionEditor />, "en");
    const card = await screen.findByTestId("retention-booking");
    const input = within(card).getByTestId("retention-days-booking");
    await userEvent.clear(input);
    await userEvent.type(input, "400");
    await userEvent.click(within(card).getByTestId("retention-save-booking"));
    expect(await within(card).findByTestId("retention-field-error-booking-action")).toHaveTextContent("bookings are anonymised, not deleted (room usage statistics stay) Allowed: Anonymise");

    const cls = fieldError("unknown_class", "data_class", "'x' has no retention policy; one of booking, audit", "'x' için saklama kuralı yok; şunlardan biri: booking, audit", { allowed: ["booking", "audit"] });
    state.putError = { ...cls, errors: [cls] };
    await userEvent.type(input, "1");
    await userEvent.click(within(card).getByTestId("retention-save-booking"));
    expect(await within(card).findByTestId("retention-error-booking")).toHaveTextContent("'x' has no retention policy");
  });

  it("an older 422 without errors[] still lands at its field", async () => {
    state.putError = fieldError("below_floor", "retain_days", "audit must be kept at least 365 days", "audit verisi en az 365 gün saklanmalı", { floor_days: 365 });
    renderIt(<RetentionEditor />);
    const card = await screen.findByTestId("retention-audit");
    const input = within(card).getByTestId("retention-days-audit");
    await userEvent.type(input, "1");
    await userEvent.click(within(card).getByTestId("retention-save-audit"));
    expect(await within(card).findByTestId("retention-field-error-audit-retain_days")).toHaveTextContent("En az 365 gün olmalı.");
  });
});

describe("KVKK queue filters", () => {
  beforeEach(() => {
    state.calls = [];
  });

  it("asks open by default; Tümü asks status=all and shows every status", async () => {
    renderIt(<DsrQueue />);
    expect(await screen.findByTestId("dsr-1")).toBeInTheDocument();
    expect(state.calls.find((c) => c.path === "/admin/dsr")?.query).toEqual({ status: "open" });
    await userEvent.click(screen.getByTestId("dsr-filter-all"));
    expect(await screen.findByTestId("dsr-3")).toHaveTextContent("Reddedildi");
    expect(screen.getByTestId("dsr-2")).toBeInTheDocument();
    expect(state.calls.some((c) => c.path === "/admin/dsr" && c.query?.status === "all")).toBe(true);
    await userEvent.click(screen.getByTestId("dsr-filter-done"));
    await waitFor(() => expect(state.calls.some((c) => c.path === "/admin/dsr" && c.query?.status === "DONE")).toBe(true));
    expect(await screen.findByTestId("dsr-empty")).toHaveTextContent("Tamamlanan talep yok.");
  });
});
