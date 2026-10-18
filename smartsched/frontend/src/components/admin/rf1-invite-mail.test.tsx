/** RF-03 (audit 2026-10-17 A3): the /admin/users invite sheet's "Davet e-postası gönder" switch sends `send_email`. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";
import { I18nProvider } from "@/lib/i18n/provider";
import { InviteSheet } from "./users-admin-identity";

vi.mock("sonner", async (orig) => ({ ...(await orig<typeof import("sonner")>()), toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn(), warning: vi.fn() }) }));

let configured = true;
let emailStatus = "SENT";
let posts: Record<string, unknown>[] = [];
/** holds GET /invite-mail back until released (the loading state) */
let mailGate: Promise<void> | null = null;

function mockApi() {
  posts = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const u = String(url);
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
      if (u.includes("/auth/me")) return json({ id: 1, username: "admin", role: "ADMIN", permissions: ["setup.users"], department_id: null });
      if (u.includes("/auth/sso/admin/invite-mail")) {
        if (mailGate) await mailGate;
        return json({ configured });
      }
      if (u.includes("/auth/sso/admin/invites") && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        posts.push(body);
        return json({ id: 9, user_id: 5, email: body.email, kind: "entra", status: "invited", created_at: "2026-10-18T08:00:00Z", expires_at: "2026-10-25T08:00:00Z", link: "https://x/invite/abc", email_status: body.send_email ? emailStatus : null }, 201);
      }
      if (u.includes("/departments")) return json([]);
      return json({});
    }),
  );
}

function renderIt(locale: "tr" | "en" = "tr") {
  mockApi();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale={locale}>
        <InviteSheet open onOpenChange={() => undefined} auth={undefined} canListRoles={false} />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

async function fillAndSubmit() {
  fireEvent.change(await screen.findByTestId("invite-email"), { target: { value: "ayse.yilmaz@uni.edu.tr" } });
  fireEvent.click(await screen.findByTestId("invite-role-code:TEACHER"));
  fireEvent.click(screen.getByRole("button", { name: "Davet et" }));
  await waitFor(() => expect(posts).toHaveLength(1));
  return posts[0];
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  configured = true;
  emailStatus = "SENT";
  mailGate = null;
});

describe("invite sheet: Davet e-postası gönder (RF-03)", () => {
  it("is on by default when SMTP is set up and sends send_email", async () => {
    renderIt();
    const sw = await screen.findByTestId("invite-send-mail");
    await waitFor(() => expect(sw).toHaveAttribute("aria-checked", "true"));
    expect(sw).not.toHaveAttribute("data-disabled");
    expect(screen.getByTestId("invite-mail-hint")).toHaveTextContent("Bağlantı bu adrese e-postayla gider");
    const body = await fillAndSubmit();
    expect(body).toMatchObject({ email: "ayse.yilmaz@uni.edu.tr", role: "TEACHER", send_email: true, locale: "tr" });
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Davet e-postası gönderildi · ayse.yilmaz@uni.edu.tr", expect.anything()));
  });

  it("can be switched off: no e-mail, the link is copied by hand", async () => {
    renderIt();
    const sw = await screen.findByTestId("invite-send-mail");
    await waitFor(() => expect(sw).toHaveAttribute("aria-checked", "true"));
    fireEvent.click(sw);
    await waitFor(() => expect(sw).toHaveAttribute("aria-checked", "false"));
    expect(screen.getByTestId("invite-mail-hint")).toHaveTextContent("E-posta gitmez");
    const body = await fillAndSubmit();
    expect(body.send_email).toBe(false);
  });

  it("without SMTP says 'E-posta ayarlanmadı' with a link to set it up, and sends no e-mail", async () => {
    configured = false;
    renderIt();
    const link = await screen.findByTestId("invite-mail-setup");
    expect(link).toHaveAttribute("href", "/admin/email");
    expect(link).toHaveTextContent("E-postayı ayarla");
    expect(screen.getByTestId("invite-mail-hint")).toHaveTextContent("E-posta ayarlanmadı");
    const sw = screen.getByTestId("invite-send-mail");
    expect(sw).toHaveAttribute("aria-checked", "false");
    expect(sw).toHaveAttribute("data-disabled");
    const body = await fillAndSubmit();
    expect(body.send_email).toBe(false);
  });

  it("warns when the e-mail could not be sent", async () => {
    emailStatus = "FAILED";
    renderIt();
    await waitFor(() => expect(screen.getByTestId("invite-send-mail")).toHaveAttribute("aria-checked", "true"));
    await fillAndSubmit();
    await waitFor(() => expect(toast.warning).toHaveBeenCalledWith("Davet oluşturuldu ama e-posta gönderilemedi. Bağlantıyı kopyalayıp iletin.", expect.anything()));
  });

  it("does not say 'E-posta ayarlanmadı' while the SMTP status is still loading (e2e 2026-10-18)", async () => {
    let release: () => void = () => undefined;
    mailGate = new Promise<void>((r) => (release = r));
    renderIt();
    const hint = await screen.findByTestId("invite-mail-hint");
    expect(hint).not.toHaveTextContent("E-posta ayarlanmadı");
    expect(hint).toHaveTextContent("Kontrol ediliyor");
    release();
    await waitFor(() => expect(screen.getByTestId("invite-send-mail")).toHaveAttribute("aria-checked", "true"));
    expect(screen.getByTestId("invite-mail-hint")).toHaveTextContent("Bağlantı bu adrese e-postayla gider");
  });

  it("is English in English", async () => {
    configured = false;
    renderIt("en");
    expect(await screen.findByText("Set up e-mail")).toBeInTheDocument();
    expect(screen.getByTestId("invite-mail-hint")).toHaveTextContent("E-mail is not set up");
  });
});
