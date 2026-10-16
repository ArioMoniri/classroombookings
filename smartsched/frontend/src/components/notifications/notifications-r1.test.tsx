/**
 * Flow-loop round 1, lane A, T-R1-04 / T-R1-05 (R1-A-19, R1-A-23): below md the bell opens a bottom sheet with
 * 44 px rows; Profil › Bildirimler shows one card per event (no sideways table) and hides approver-only and
 * room-owner events from accounts that cannot receive them.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import type { NotificationPrefs } from "@/lib/api/approval-first";

vi.mock("next/navigation", () => ({
  usePathname: () => "/bookings",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { NotificationBell } from "./notification-bell";
import { NotificationPreferencesPanel, eventAudience, receivableEvents } from "./preferences-panel";

const TEACHER = ["book_single.create", "book_recur.create", "room.view"];
const APPROVER = [...TEACHER, "approvals.decide"];

const prefs = (): NotificationPrefs => ({
  channels: [
    { name: "in_app", label_tr: "Uygulama içi", label_en: "In the app", enabled: true, available: true, default_enabled: true },
    { name: "email", label_tr: "E-posta", label_en: "E-mail", enabled: true, available: true, default_enabled: true },
  ],
  events: [
    { event: "approval.requested", label_tr: "Onayımı bekleyen yeni oda talepleri", label_en: "New room requests awaiting my approval", channels: { in_app: true, email: true } },
    { event: "approval.approved", label_tr: "Talebim onaylandı", label_en: "My request was approved", channels: { in_app: true, email: true } },
    { event: "booking.created", label_tr: "Rezervasyon oluşturuldu", label_en: "Booking created", channels: { in_app: true, email: false } },
    { event: "room_owner.booking", label_tr: "Sorumlu olduğum odaya rezervasyon yapıldı", label_en: "A room I look after was booked", channels: { in_app: true, email: true } },
    { event: "timetable.published", label_tr: "Program yayınlandı", label_en: "Timetable published", channels: { in_app: true, email: true } },
  ],
});

const notifications = [
  { id: 1, kind: "approval_approved", title: "Talebiniz onaylandı", body: "A 101 · 3. periyot", link: "/my-bookings?request=1", request_id: 1, read_at: null, created_at: "2026-10-16T08:00:00Z" },
  { id: 2, kind: "timetable_published", title: "Program yayınlandı", body: "", link: null, request_id: null, read_at: "2026-10-16T09:00:00Z", created_at: "2026-10-15T08:00:00Z" },
];

function stubFetch(permissions: string[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const u = new URL(url, "http://localhost");
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
      if (u.pathname === "/api/v1/auth/me") return json({ id: 7, email: "hoca@uni.edu.tr", username: "hoca", full_name: "A. T.", role: "TEACHER", permissions });
      if (u.pathname === "/api/v1/me/notification-preferences") return json(prefs());
      if (u.pathname === "/api/v1/me/notifications") return json(u.searchParams.get("unread") ? notifications.filter((n) => !n.read_at) : notifications);
      if (u.pathname === "/api/v1/runs") return json([]);
      return json({ detail: "not in this test" }, 404);
    }),
  );
}

function mockMedia(matching: string[]) {
  const real = window.matchMedia;
  vi.spyOn(window, "matchMedia").mockImplementation((q: string) => ({ ...real(q), matches: matching.includes(q), media: q }));
}

function wrap(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider initialLocale="tr">{ui}</I18nProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("event audiences (T-R1-05)", () => {
  it("approval.requested is for approvers, room_owner.* for designated owners, the rest for everyone", () => {
    expect(eventAudience("approval.requested")).toBe("approver");
    expect(eventAudience("room_owner.booking")).toBe("room_owner");
    expect(eventAudience("approval.approved")).toBe("everyone");
    expect(eventAudience("timetable.published")).toBe("everyone");
    const can = (perms: string[]) => (p: string) => perms.includes(p);
    expect(receivableEvents(prefs().events, can(TEACHER)).map((e) => e.event)).toEqual(["approval.approved", "booking.created", "timetable.published"]);
    expect(receivableEvents(prefs().events, can(APPROVER)).map((e) => e.event)).toEqual(prefs().events.map((e) => e.event));
  });
});

describe("Profil › Bildirimler on a phone (T-R1-05)", () => {
  beforeEach(() => mockMedia(["(max-width: 767.98px)", "(max-width: 640px)", "(pointer: coarse)"]));

  it("a teacher sees cards, never a table, and no approver or room-owner rows", async () => {
    stubFetch(TEACHER);
    wrap(<NotificationPreferencesPanel />);
    expect(await screen.findByText("Talebim onaylandı")).toBeInTheDocument();
    expect(document.querySelector("table")).toBeNull();
    expect(screen.getByTestId("prefs-cards-approvals")).toBeInTheDocument();
    expect(screen.queryByText("Onayımı bekleyen yeni oda talepleri")).toBeNull();
    expect(screen.queryByText("Sorumlu olduğum odaya rezervasyon yapıldı")).toBeNull();
    // the switches sit in 44 px label rows: the label is the row's tap target
    const row = screen.getByTestId("pref-approval.approved-email").closest("li")!;
    expect(row).toHaveClass("min-h-11");
    expect(within(row).getByText("E-posta").closest("label")).toHaveClass("min-h-11");
  });

  it("an approver keeps the approver and room-owner rows", async () => {
    stubFetch(APPROVER);
    wrap(<NotificationPreferencesPanel />);
    expect(await screen.findByText("Onayımı bekleyen yeni oda talepleri")).toBeInTheDocument();
    // the bookings group is closed on a phone: the row is in the tree, inside its <details>
    expect(screen.getByText("Sorumlu olduğum odaya rezervasyon yapıldı")).toBeInTheDocument();
  });
});

describe("Profil › Bildirimler from md up", () => {
  it("keeps the matrix", async () => {
    mockMedia([]);
    stubFetch(APPROVER);
    wrap(<NotificationPreferencesPanel />);
    expect(await screen.findByTestId("prefs-matrix-approvals")).toBeInTheDocument();
    expect(screen.queryByTestId("prefs-cards-approvals")).toBeNull();
  });
});

describe("the bell below md (T-R1-04)", () => {
  it("opens a bottom sheet whose rows are at least 44 px, with the badge at 11 px", async () => {
    mockMedia(["(max-width: 767.98px)", "(pointer: coarse)"]);
    stubFetch(TEACHER);
    wrap(<NotificationBell />);
    const bell = screen.getByTestId("notification-bell");
    await waitFor(() => expect(screen.getByTestId("notification-count")).toHaveTextContent("1"));
    expect(screen.getByTestId("notification-count")).toHaveClass("text-[11px]");
    await userEvent.click(bell);
    const panel = await screen.findByTestId("notification-panel");
    expect(panel).toHaveAttribute("data-variant", "sheet");
    expect(panel).toHaveAttribute("data-side", "bottom");
    expect(panel.closest("[role=dialog]") ?? panel).toHaveAttribute("role", "dialog");
    expect(within(panel).getByRole("heading", { name: "Bildirimler" })).toBeInTheDocument();
    for (const id of [1, 2]) expect(within(panel).getByTestId(`notification-${id}`)).toHaveClass("min-h-11");
    // a full-width phone sheet (inset-x-0 below sm)
    expect(panel).toHaveClass("max-sm:data-[side=bottom]:inset-x-0");
  });

  it("from md up it stays the anchored popover", async () => {
    mockMedia([]);
    stubFetch(TEACHER);
    wrap(<NotificationBell />);
    await userEvent.click(screen.getByTestId("notification-bell"));
    const panel = await screen.findByTestId("notification-panel");
    expect(panel).toHaveAttribute("data-slot", "popover-content");
    expect(within(panel).getByTestId("notification-1")).toHaveClass("min-h-11");
  });
});
