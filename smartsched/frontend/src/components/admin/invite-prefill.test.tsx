/**
 * HX-06 hand-over: /admin/users?invite=1&email=&name=&role=&department= opens the invite sheet with the fields
 * filled; nothing is sent until the admin presses "Davet et".
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { InviteSheet } from "./users-admin-identity";

vi.mock("sonner", async (orig) => ({ ...(await orig<typeof import("sonner")>()), toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn(), warning: vi.fn() }) }));

let posts: Record<string, unknown>[] = [];

function mockApi() {
  posts = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const u = String(url);
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
      if (u.includes("/auth/me")) return json({ id: 1, username: "admin", role: "ADMIN", permissions: ["setup.users"], department_id: null });
      if (u.includes("/auth/sso/admin/invite-mail")) return json({ configured: false });
      if (u.includes("/auth/sso/admin/invites") && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        posts.push(body);
        return json({ id: 9, user_id: 5, email: body.email, kind: "entra", status: "invited", created_at: "2026-10-18T08:00:00Z", expires_at: "2026-10-25T08:00:00Z", link: null, email_status: null }, 201);
      }
      if (u.includes("/departments")) return json([{ id: 7, name: "Eczacılık" }]);
      return json({});
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("invite hand-over prefill", () => {
  it("fills e-mail, name, role and department, and sends only on Davet et", async () => {
    mockApi();
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <I18nProvider initialLocale="tr">
          <InviteSheet open onOpenChange={() => undefined} auth={undefined} canListRoles={false} prefill={{ email: "ayse.k@uni.edu.tr", name: "A. K.", role: "TEACHER", department: "7" }} />
        </I18nProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByTestId("invite-email")).toHaveValue("ayse.k@uni.edu.tr");
    expect(screen.getByTestId("invite-name")).toHaveValue("A. K.");
    expect(await screen.findByTestId("invite-role-code:TEACHER")).toBeChecked();
    await waitFor(() => expect(screen.getByLabelText("Bölüm · isteğe bağlı")).toHaveValue("7"));
    expect(posts).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Davet et" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toMatchObject({ email: "ayse.k@uni.edu.tr", full_name: "A. K.", role: "TEACHER", department_id: 7 });
  });
});
