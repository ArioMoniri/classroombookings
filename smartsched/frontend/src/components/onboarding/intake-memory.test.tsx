/** "Hatırlanan kararlar": the intake memory grouped by file signature (GET /council/memory), a group opens to its
 * rows, one row or a whole signature is forgotten after a confirm (DELETE), the undo toast for administrators, and
 * no forget buttons for readers. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

const SIG = "a".repeat(64);
const LEX = "b".repeat(64);
const item = (id: number, signature: string, kind: string, group: string, en: string, tr: string, extra: Record<string, unknown> = {}) => ({
  id, signature, kind, group, attribute: kind === "intake_mapping" ? `col:${id}` : "header", value: "course_code", action: "edit",
  created_at: "2026-10-16T09:00:00", created_by: { id: 1, name: "Ayşe Planlamacı" }, job_id: 3, job_exists: true, term_id: null,
  effective: true, description: { en, tr }, context: {}, ...extra,
});
const db = vi.hoisted(() => ({ calls: [] as { path: string; method: string; query?: unknown }[], perms: ["planning.view", "planning.edit", "planning.admin"], items: [] as unknown[] }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/lib/permissions", () => ({ usePermissions: () => ({ loading: false, can: (p: string) => db.perms.includes(p) }) }));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  request: async (path: string, opts: { method?: string; query?: Record<string, unknown>; schema?: { parse: (v: unknown) => unknown } } = {}) => {
    const method = opts.method ?? "GET";
    db.calls.push({ path, method, query: opts.query });
    const parse = (v: unknown) => (opts.schema ? opts.schema.parse(v) : v);
    if (path === "/council/memory" && method === "GET") {
      const items = db.items as ReturnType<typeof item>[];
      const sigs = [...new Set(items.map((i) => i.signature))];
      const groups = sigs.map((s) => {
        const rows = items.filter((i) => i.signature === s);
        return { signature: s, group: rows[0]!.group, kinds: [...new Set(rows.map((r) => r.kind))], jobs: [3], count: rows.length, last_at: rows[0]!.created_at, label: s === SIG ? { en: "bahar.xlsx › Dersler", tr: "bahar.xlsx › Dersler" } : { en: "Header 'Hoca'", tr: "Başlık 'Hoca'" }, ids: rows.map((r) => r.id) };
      });
      return parse({ items, groups, total: items.length, content: true, truncated: false });
    }
    if (path.startsWith("/council/memory") && method === "DELETE") {
      const before = (db.items as ReturnType<typeof item>[]).length;
      db.items = (db.items as ReturnType<typeof item>[]).filter((i) => (path === "/council/memory" ? i.signature !== (opts.query as { signature: string }).signature : `/council/memory/${i.id}` !== path));
      return parse({ id: 41, forgotten: before - db.items.length, ids: [], undo_until: "2026-11-15T09:00:00", undoable: true, scope: "intake" });
    }
    if (path === "/learning/resets/41/undo") return parse({ id: 41, scope: "intake", value: "#1", created_at: "2026-10-16T09:00:00" });
    throw new Error(`unexpected ${method} ${path}`);
  },
}));

import { IntakeMemoryPanel, sectionGroups } from "./intake-memory";

function wrap(locale: "tr" | "en" = "en") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale={locale}>
        <IntakeMemoryPanel />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  db.calls = [];
  db.perms = ["planning.view", "planning.edit", "planning.admin"];
  db.items = [
    item(1, SIG, "intake_mapping", "layout", "bahar.xlsx › Dersler: column 2 'Hoca' → instructor", "bahar.xlsx › Dersler: 2. sütun 'Hoca' → instructor"),
    item(2, SIG, "intake_mapping", "layout", "bahar.xlsx › Dersler: column 3 'Kod' → course_code", "bahar.xlsx › Dersler: 3. sütun 'Kod' → course_code", { effective: false }),
    item(3, LEX, "intake_lexicon", "lexicon", "Header 'Hoca' → instructor", "'Hoca' başlığı → instructor"),
  ];
  toast.success.mockReset();
});

describe("sectionGroups", () => {
  it("keeps the groups of one section with their rows", () => {
    const g = sectionGroups({ items: db.items as never, groups: [{ signature: SIG, group: "layout", kinds: [], jobs: [3], count: 2, last_at: "2026-10-16", label: { en: "", tr: "" }, ids: [1, 2] }] }, "layout");
    expect(g.map((x) => x.rows.map((r) => r.id))).toEqual([[1, 2]]);
  });
});

describe("IntakeMemoryPanel", () => {
  it("groups by signature, opens a group and forgets one row after a confirm, with an undo toast", async () => {
    const user = userEvent.setup();
    wrap("tr");
    expect(await screen.findByTestId("intake-memory-total")).toHaveTextContent("3 karar, 2 imza.");
    expect(screen.getByTestId("intake-memory-section-layout")).toHaveTextContent("Dosya düzenleri");
    expect(screen.getByTestId("intake-memory-section-lexicon")).toHaveTextContent("Başlık 'Hoca'");
    const group = screen.getAllByTestId("intake-memory-group").find((g) => g.dataset.signature === SIG)!;
    const toggle = within(group).getByTestId("intake-memory-group-toggle");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    const rows = within(group).getAllByTestId("intake-memory-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("bahar.xlsx › Dersler: 2. sütun 'Hoca' → instructor");
    expect(rows[0]).toHaveTextContent("Sütun eşlemesi · Ayşe Planlamacı");
    expect(rows[1]).toHaveTextContent("daha yeni kararla değişti");
    await user.click(within(rows[0]!).getByTestId("intake-memory-forget-row"));
    const dialog = await screen.findByTestId("intake-memory-confirm");
    expect(dialog).toHaveTextContent("Bu karar unutulsun mu?");
    await user.click(within(dialog).getByTestId("intake-memory-confirm-button"));
    await waitFor(() => expect(db.calls).toContainEqual({ path: "/council/memory/1", method: "DELETE", query: undefined }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("1 karar unutuldu", expect.objectContaining({ action: expect.objectContaining({ label: "Geri al" }) })));
    await waitFor(() => expect(screen.getByTestId("intake-memory-total")).toHaveTextContent("2 karar, 2 imza."));
    // undo from the toast: the learning lane's reset undo
    (toast.success.mock.calls[0]![1] as { action: { onClick: () => void } }).action.onClick();
    await waitFor(() => expect(db.calls).toContainEqual({ path: "/learning/resets/41/undo", method: "POST", query: undefined }));
  });

  it("forgets a whole signature", async () => {
    const user = userEvent.setup();
    wrap();
    const group = (await screen.findAllByTestId("intake-memory-group")).find((g) => g.dataset.signature === SIG)!;
    await user.click(within(group).getByTestId("intake-memory-forget-group"));
    const dialog = await screen.findByTestId("intake-memory-confirm");
    expect(dialog).toHaveTextContent("bahar.xlsx › Dersler: 2 decisions are forgotten.");
    await user.click(within(dialog).getByRole("button", { name: "Forget all" }));
    await waitFor(() => expect(db.calls).toContainEqual({ path: "/council/memory", method: "DELETE", query: { signature: SIG } }));
    await waitFor(() => expect(screen.queryByTestId("intake-memory-section-layout")).not.toBeInTheDocument());
  });

  it("lets readers inspect without forgetting, and says when nothing is remembered", async () => {
    db.perms = ["planning.view"];
    const { unmount } = wrap();
    await screen.findByTestId("intake-memory-total");
    expect(screen.queryByTestId("intake-memory-forget-group")).not.toBeInTheDocument();
    unmount();
    db.items = [];
    wrap();
    expect(await screen.findByTestId("intake-memory-empty")).toHaveTextContent("Nothing is remembered yet.");
  });
});
