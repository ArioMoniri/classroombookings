/**
 * HB-23c, KVKK review condition 10: the file hand-over (token + file name in sessionStorage) and the thread's live
 * stages never survive into the next person's session. Sign-out (user menu) and the 401 redirect (app shell) clear the
 * slot, delete the stages on the server and empty the helper thread, before the session goes.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { HANDOFF_STORAGE_KEY, useFileHandoffStore } from "./file-handoff";
import { HANDOFF_KEY, clearHelperFileSession } from "./file-session";
import { useHelperStore } from "./helper-store";
import { resetHelperStore } from "./test-helpers";

vi.mock("next/navigation", () => ({
  usePathname: () => "/import",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { UserMenu } from "@/components/shell/user-menu";

const tok = (sid: string) => `${btoa(JSON.stringify({ k: "file", s: sid })).replace(/=+$/, "")}.c2lnbmF0dXJlLXNpZ25hdHVyZQ`;
let calls: string[];

function seed() {
  useFileHandoffStore.getState().set({
    featureId: "import",
    kind: "planning_list",
    params: { kind: "planning-list" },
    items: [{ token: tok("handed1"), sid: "handed1", name: "Bahar_son.xlsx", size: 10, format: "xlsx", expiresAt: Date.now() + 60_000 }],
    at: Date.now(),
  });
  const key = useHelperStore.getState().pushFile([{ name: "ikinci.xlsx", size: 5 }]);
  useHelperStore.getState().updateFile(key, { phase: "shown", stage: { upload_token: tok("live1"), expires_at: new Date(Date.now() + 60_000).toISOString() }, seq: 1 });
}

beforeEach(() => {
  resetHelperStore();
  window.sessionStorage.clear();
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const path = new URL(url, "http://localhost").pathname;
      calls.push(`${init?.method ?? "GET"} ${path}`);
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
      if (path === "/api/v1/auth/me") return json({ id: 7, email: "a@uni.edu.tr", username: "a", full_name: "A. T.", role: "ADMIN", permissions: ["planning.edit"] });
      if (init?.method === "DELETE") return new Response(null, { status: 204 });
      return json([]);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("clearHelperFileSession", () => {
  it("uses the hand-over's own storage key", () => {
    expect(HANDOFF_KEY).toBe(HANDOFF_STORAGE_KEY);
  });

  it("deletes the handed and the live stages, empties the slot, sessionStorage and the thread", async () => {
    seed();
    expect(window.sessionStorage.getItem(HANDOFF_STORAGE_KEY)).toContain("Bahar_son.xlsx");
    await clearHelperFileSession();
    expect(window.sessionStorage.getItem(HANDOFF_STORAGE_KEY)).toBeNull();
    expect(useFileHandoffStore.getState().handoff).toBeNull();
    expect(useHelperStore.getState().entries).toEqual([]);
    expect(useHelperStore.getState().open).toBe(false);
    await waitFor(() => expect(calls).toEqual(expect.arrayContaining(["DELETE /api/v1/helper/files/handed1", "DELETE /api/v1/helper/files/live1"])));
  });
});

describe("sign-out paths", () => {
  it("the user menu's Çıkış clears the hand-over before the session is revoked", async () => {
    seed();
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <I18nProvider initialLocale="tr">
          <UserMenu compact />
        </I18nProvider>
      </QueryClientProvider>,
    );
    await userEvent.click(screen.getByTestId("user-menu"));
    await userEvent.click(await screen.findByTestId("logout"));
    await waitFor(() => expect(calls).toContain("POST /api/auth/logout"));
    expect(window.sessionStorage.getItem(HANDOFF_STORAGE_KEY)).toBeNull();
    expect(useFileHandoffStore.getState().handoff).toBeNull();
    const deletes = calls.findIndex((c) => c.startsWith("DELETE /api/v1/helper/files/"));
    expect(deletes).toBeGreaterThanOrEqual(0);
    expect(deletes).toBeLessThan(calls.indexOf("POST /api/auth/logout"));
  });

  it("the shell's 401 redirect clears it too (the next person never sees the token or the name)", async () => {
    const { readFileSync } = await import("node:fs");
    const { resolve } = await import("node:path");
    const src = readFileSync(resolve(import.meta.dirname, "../shell/app-shell.tsx"), "utf8");
    // the 401 listener calls the helper's session clear before it signs out and leaves
    const listener = src.slice(src.indexOf("return onUnauthorized("), src.indexOf("window.location.assign"));
    expect(listener).toMatch(/clearHelperFileSession\(\)/);
    expect(listener.indexOf("clearHelperFileSession")).toBeLessThan(listener.indexOf('fetch("/api/auth/logout"'));
    await act(async () => undefined);
  });
});
