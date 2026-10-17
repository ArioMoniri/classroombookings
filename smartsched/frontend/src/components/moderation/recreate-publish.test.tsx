/**
 * Round-2 T-R2-23 (R2-M-02): publishing from the re-solve preview. The server's 2xx is the truth: the dialog shows
 * the Turkish publish toast and refreshes the preview (`onPublished`) whatever the body's shape, and it never prints
 * "Invalid response for POST /runs/<id>/activate".
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import recorded from "@/lib/api/__fixtures__/activate-run-8.json";
import { DiffOut } from "@/lib/api/moderation";
import { I18nProvider } from "@/lib/i18n/provider";
import { PublishDialog } from "./recreate-preview";

const toastSuccess = vi.fn();
vi.mock("sonner", () => ({ toast: { success: (...a: unknown[]) => toastSuccess(...a), error: vi.fn() } }));

const diff = DiffOut.parse({ run_id: 15, base_run_id: 8, status: "FEASIBLE_PARTIAL", ready: true, counts: { moved: 1, newly_placed: 1, unplaceable: 0, newly_unplaced: 0, affected_people: 1 }, unplaceable: [] });
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function mount(activateBody: unknown) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (/\/runs\/15\/activate$/.test(url)) return json(activateBody);
      return json({ items: [], total: 0 });
    }),
  );
  const onPublished = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLocale="tr">
        <PublishDialog open onOpenChange={onOpenChange} diff={diff} termId={2} onPublished={onPublished} />
      </I18nProvider>
    </QueryClientProvider>,
  );
  return { calls, onPublished, onOpenChange };
}

afterEach(() => {
  vi.unstubAllGlobals();
  toastSuccess.mockClear();
});

describe("re-solve publish (T-R2-23)", () => {
  it("publishes with the real activate body: toast, closed dialog, preview refreshed, no English error", async () => {
    const { calls, onPublished, onOpenChange } = mount({ ...recorded, id: 15, is_active: true });
    await userEvent.click(await screen.findByTestId("publish-confirm"));
    await waitFor(() => expect(onPublished).toHaveBeenCalledTimes(1));
    expect(calls.some((c) => /^POST .*\/runs\/15\/activate$/.test(c))).toBe(true);
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(toastSuccess).toHaveBeenCalledWith(expect.stringContaining("Yayınlandı: #15"));
    expect(screen.queryByTestId("publish-refused")).toBeNull();
    expect(document.body.textContent).not.toMatch(/Invalid response/);
  });
  it("treats a 2xx whose body fails the client schema as published", async () => {
    const { onPublished } = mount({ ok: true }); // no run id at all: even the loose schema refuses it
    await userEvent.click(await screen.findByTestId("publish-confirm"));
    await waitFor(() => expect(onPublished).toHaveBeenCalledTimes(1));
    expect(toastSuccess).toHaveBeenCalledWith(expect.stringContaining("Yayınlandı: #15"));
    expect(screen.queryByTestId("publish-refused")).toBeNull();
    expect(document.body.textContent).not.toMatch(/Invalid/);
  });
  it("still shows the server's own refusal", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => (/activate$/.test(url) ? json({ detail: { code: "forced_breaks", message: "run 15 breaks 2 hard rules", message_tr: "#15 2 kesin kuralı bozuyor" } }, 409) : json({ items: [], total: 0 }))));
    const onPublished = vi.fn();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <I18nProvider initialLocale="tr">
          <PublishDialog open onOpenChange={() => undefined} diff={diff} termId={2} onPublished={onPublished} />
        </I18nProvider>
      </QueryClientProvider>,
    );
    await userEvent.click(await screen.findByTestId("publish-confirm"));
    expect(await screen.findByTestId("publish-refused")).toHaveTextContent("#15 2 kesin kuralı bozuyor");
    expect(onPublished).not.toHaveBeenCalled();
  });
});
