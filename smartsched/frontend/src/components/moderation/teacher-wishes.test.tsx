/**
 * P19-T2: Tercihlerim (status, the coordinator's reason, withdraw while pending, 409 once decided) and the
 * coordinator's Akademisyen tercihleri (pending first with counts, accept, reject only with a written reason and
 * an optional code, `with_submission` for a submission stored as several rules, accepted = soft rule after the
 * department's room). Real Bahar rows: PTL 102 §1 / PTL 152 §1 asked C 601; the wish is C 301.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "@/lib/api/client";
import { I18nProvider } from "@/lib/i18n/provider";

const state = vi.hoisted(() => ({ items: [] as Record<string, unknown>[], calls: [] as { method: string; path: string; body?: unknown }[], withdraw: null as null | (() => unknown) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  request: async (path: string, opts: { method?: string; body?: unknown } = {}) => {
    const method = opts.method ?? "GET";
    state.calls.push({ method, path, body: opts.body });
    const counts = { pending: 0, accepted: 0, rejected: 0 } as Record<string, number>;
    for (const i of state.items) counts[String(i.status)]! += 1;
    if (path === "/moderation/me/preferences" && method === "GET") return { linked: true, instructor_id: 266, term_id: 1, counts, total: state.items.length, items: state.items };
    if (path === "/terms/1/moderation/teacher-preferences") return { term_id: 1, counts, total: state.items.length, items: state.items };
    const del = /^\/moderation\/me\/preferences\/(\d+)$/.exec(path);
    if (del && method === "DELETE") return state.withdraw ? state.withdraw() : undefined;
    const dec = /^\/moderation\/preferences\/(\d+)\/decide$/.exec(path);
    if (dec && method === "POST") {
      const b = opts.body as { decision: string };
      return { decision: b.decision, status: b.decision === "accept" ? "accepted" : "rejected", decided_ids: [Number(dec[1])], notified: true, items: [], effective: null };
    }
    throw new Error(`unexpected ${method} ${path}`);
  },
}));

import { MyWishes } from "./my-wishes";
import { TeacherWishesReview } from "./teacher-wishes-review";

const item = (id: number, over: Record<string, unknown> = {}) => ({
  id,
  constraint_id: id,
  term_id: 1,
  status: "pending",
  enabled: false,
  kind: "room_preference",
  kind_label: { tr: "Oda tercihi", en: "Room preference" },
  submission: `s${id}`,
  request_ids: [590],
  labels: ["PTL 102 §1"],
  instructor: { id: 266, name: "Doç. Dr. D. Ş." },
  wish: { room_ids: [32], rooms: ["C 301"] },
  department: { room_ids: [50], rooms: ["C 601"] },
  rank: "below_department",
  text: { tr: "PTL 102 §1: oda tercihi C 301", en: "PTL 102 §1: room preference C 301" },
  note: "deney düzeneği bu binada",
  hardness: "soft",
  weight: 1,
  submitted_at: "2026-10-16T04:31:58+00:00",
  decided_at: null,
  decided_by: null,
  reason: null,
  reason_code: null,
  ...over,
});

function wrap(ui: React.ReactNode, locale: "tr" | "en" = "tr") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale={locale}>{ui}</I18nProvider>
    </QueryClientProvider>,
  );
}

describe("Tercihlerim", () => {
  beforeEach(() => {
    state.calls = [];
    state.withdraw = null;
    state.items = [
      item(40),
      item(41, { status: "rejected", decided_at: "2026-10-16T06:00:00+00:00", reason: "C 301 bu saatlerde lisans laboratuvarına ayrılmış", reason_code: "room_unavailable", labels: ["PTL 152 §1"], text: { tr: "PTL 152 §1: oda tercihi C 301", en: "PTL 152 §1: room preference C 301" } }),
      item(42, { status: "accepted", enabled: true, labels: ["PTL 184 §1"] }),
    ];
  });

  it("lists pending first with the counts, the reason on a rejection and the soft-rule note on an acceptance", async () => {
    wrap(<MyWishes termId={1} />);
    expect(await screen.findByTestId("my-wishes-counts")).toHaveTextContent("1 bekliyor · 1 kabul · 1 ret");
    const cards = screen.getAllByTestId("my-wish");
    expect(cards.map((c) => c.dataset.status)).toEqual(["pending", "rejected", "accepted"]);
    expect(within(cards[1]!).getByTestId("my-wish-reason")).toHaveTextContent("Gerekçe: Oda uygun değil: C 301 bu saatlerde lisans laboratuvarına ayrılmış");
    expect(cards[2]).toHaveTextContent("bölüm talebinden sonra gelen bir tercih");
    expect(within(cards[0]!).getByTestId("wish-status")).toHaveTextContent("Bekliyor");
    expect(within(cards[1]!).queryByTestId("wish-withdraw")).toBeNull();
  });

  it("withdraws a pending wish after asking, and explains a 409 once it was decided", async () => {
    const user = userEvent.setup();
    wrap(<MyWishes termId={1} />);
    await user.click(await screen.findByTestId("wish-withdraw"));
    expect(await screen.findByTestId("wish-withdraw-dialog")).toHaveTextContent("PTL 102 §1 için gönderdiğiniz tercih silinir");
    state.withdraw = () => {
      throw new HttpError(409, "decided", { detail: { code: "decided", message: "the preference was already accepted", message_tr: "Tercih için karar verilmiş; geri çekilemez" } });
    };
    await user.click(screen.getByTestId("wish-withdraw-confirm"));
    expect(await screen.findByText("Bu tercih için zaten karar verildi; liste yenilendi.")).toBeInTheDocument();
    state.withdraw = null;
    await user.click(screen.getByTestId("wish-withdraw-confirm"));
    await waitFor(() => expect(state.calls.filter((c) => c.method === "DELETE").map((c) => c.path)).toEqual(["/moderation/me/preferences/40", "/moderation/me/preferences/40"]));
  });
});

describe("Akademisyen tercihleri (coordinator)", () => {
  beforeEach(() => {
    state.calls = [];
    state.items = [
      // one submission over two classes with different department asks = two rules
      item(50, { submission: "two", labels: ["PTL 102 §1"] }),
      item(51, { submission: "two", labels: ["PTL 152 §1"], request_ids: [574], department: { room_ids: [7], rooms: ["A 306"] } }),
      item(52, { status: "accepted", enabled: true, labels: ["PTL 184 §1"], request_ids: [801] }),
    ];
  });

  it("shows the pending submission first with the counts, the department's ask and the note", async () => {
    wrap(<TeacherWishesReview termId={1} canEdit />);
    const card = await screen.findByTestId("wish-card");
    expect(screen.getByTestId("wish-filter-pending")).toHaveTextContent("Bekleyen 1");
    expect(screen.getByTestId("wish-filter-accepted")).toHaveTextContent("Kabul edilen 1");
    expect(card).toHaveTextContent("PTL 102 §1, PTL 152 §1");
    expect(card).toHaveTextContent("Bölümün istediği önce: C 601");
    expect(card).toHaveTextContent("Bu başvuru 2 kural olarak saklandı");
    expect(card).toHaveTextContent("Akademisyenin notu: “deney düzeneği bu binada”");
    await userEvent.setup().click(screen.getByTestId("wish-filter-accepted"));
    expect(await screen.findByTestId("wish-soft-rule")).toHaveTextContent("Yumuşak kural · bölüm odasından sonra");
  });

  it("refuses a rejection without a written reason, then sends the reason, the code and the whole submission", async () => {
    const user = userEvent.setup();
    wrap(<TeacherWishesReview termId={1} canEdit />);
    await user.click(await screen.findByTestId("wish-reject"));
    const dialog = await screen.findByTestId("wish-reject-dialog");
    await user.type(within(dialog).getByTestId("wish-reject-reason"), "ok");
    await user.click(within(dialog).getByTestId("wish-reject-confirm"));
    expect(within(dialog).getByText("Gerekçe en az 3 karakter olmalı.")).toBeInTheDocument();
    expect(state.calls.some((c) => c.path.endsWith("/decide"))).toBe(false);
    await user.type(within(dialog).getByTestId("wish-reject-reason"), " değil: C 301 lisans laboratuvarına ayrılmış");
    await user.selectOptions(within(dialog).getByTestId("wish-reject-code"), "room_unavailable");
    await user.click(within(dialog).getByTestId("wish-reject-confirm"));
    await waitFor(() => expect(state.calls.find((c) => c.path.endsWith("/decide"))).toBeTruthy());
    expect(state.calls.find((c) => c.path.endsWith("/decide"))).toEqual({
      method: "POST",
      path: "/moderation/preferences/50/decide",
      body: { decision: "reject", reason: "ok değil: C 301 lisans laboratuvarına ayrılmış", reason_code: "room_unavailable", with_submission: true },
    });
  });

  it("accepts only one rule of the submission when narrowed", async () => {
    const user = userEvent.setup();
    wrap(<TeacherWishesReview termId={1} canEdit />, "en");
    await user.click(await screen.findByTestId("decide-scope-one"));
    await user.click(screen.getByTestId("wish-accept"));
    await waitFor(() => expect(state.calls.find((c) => c.path.endsWith("/decide"))?.body).toEqual({ decision: "accept", with_submission: false }));
  });

  it("is read-only without planning.edit", async () => {
    wrap(<TeacherWishesReview termId={1} canEdit={false} />);
    await screen.findByTestId("wish-card");
    expect(screen.queryByTestId("wish-accept")).toBeNull();
    expect(screen.queryByTestId("wish-reject")).toBeNull();
  });
});
