// E2EA-F11 / E2EA2-F07 (FIX-K): the class inspector edits "Öğrenci sayısı" on every surface (phone included) for a
// class (PUT /requests/meetings/{id}) and an exam (PUT /requests/exams/{id}); 16 px input, 44 px stepper on touch.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

const toasts = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), toasts) }));
vi.mock("@/lib/api/endpoints", async (orig) => {
  const real = await orig<typeof import("@/lib/api/endpoints")>();
  const put = (path: string) => async (id: number, body: unknown) => {
    calls.push({ key: `PUT /api/v1/requests/${path}/${id}`, body });
    return {};
  };
  return { ...real, api: { ...real.api, requests: { ...real.api.requests, updateMeeting: put("meetings"), updateExam: put("exams") } } };
});
import { EnrolmentField } from "./enrolment-field";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
let calls: { key: string; body: unknown }[] = [];
beforeEach(() => {
  calls = [];
  vi.stubGlobal("fetch", vi.fn(async () => res(200, {})));
});
afterEach(() => vi.unstubAllGlobals());

const wrap = (kind: "meetings" | "exams") =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">
        <EnrolmentField kind={kind} requestId={12} value={54} />
      </I18nProvider>
    </QueryClientProvider>,
  );

describe("EnrolmentField", () => {
  it("steps +1 and saves a class's enrolment with PUT /requests/meetings/{id}", async () => {
    wrap("meetings");
    const input = screen.getByLabelText("Öğrenci sayısı");
    expect(input).toHaveValue("54");
    expect(input.className).toContain("pointer-coarse:text-base");
    fireEvent.click(screen.getByRole("button", { name: "Öğrenci sayısını bir artır" }));
    expect(input).toHaveValue("55");
    const save = screen.getByRole("button", { name: "Kaydet" });
    save.focus();
    fireEvent.click(save);
    await waitFor(() => expect(calls.find((c) => c.key === "PUT /api/v1/requests/meetings/12")?.body).toEqual({ enrolment: 55 }));
    await waitFor(() => expect(toasts.success).toHaveBeenCalled());
    expect(document.activeElement).toBe(input);
  });

  it("an exam's head count goes to PUT /requests/exams/{id}", async () => {
    wrap("exams");
    fireEvent.change(screen.getByLabelText("Öğrenci sayısı"), { target: { value: "60" } });
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));
    await waitFor(() => expect(calls.find((c) => c.key === "PUT /api/v1/requests/exams/12")?.body).toEqual({ enrolment: 60 }));
  });

  it("refuses a negative or broken number inline, without a request", () => {
    wrap("meetings");
    fireEvent.change(screen.getByLabelText("Öğrenci sayısı"), { target: { value: "-3" } });
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));
    expect(screen.getByRole("alert")).toHaveTextContent("0 ya da daha büyük bir tam sayı yazın.");
    expect(calls.some((c) => c.key.startsWith("PUT"))).toBe(false);
  });
});
