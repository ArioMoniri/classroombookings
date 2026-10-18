// FIX-J (round-4 e2e): the import preview names removals ("arşivlenecek") apart from edits, asks for a deliberate
// confirmation when Uygula would archive a large share of an entity (E2EA2-F01), and keeps its counts and change
// list when a row carries a composite id (E2EA-F03).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { importJob } from "@/lib/api/adapters";
import { importDiff } from "@/lib/api/rf-admin";
import { ImportJob } from "@/lib/api/schemas";
import { I18nProvider } from "@/lib/i18n/provider";
import { ImportPreview } from "./import-preview";

const APPLIED = { id: 52, kind: "planning-list", filename: "liste.xlsx", status: "DONE", term_code: "2026-BAHAR", created_at: "2026-10-18T09:00:00", summary: { rows_total: 3, preview_of: 51, warnings: [] }, actor: "user", source: "upload" };
const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
let posts: string[];
beforeEach(() => {
  posts = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") posts.push(String(url).split("?")[0]!);
      return String(url).includes("/apply") ? res(202, APPLIED) : res(200, APPLIED);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function job(diff: unknown) {
  return ImportJob.parse(importJob({ id: 51, kind: "planning-list", filename: "liste.xlsx", status: "DONE", term_code: "2026-BAHAR", created_at: "2026-10-18T09:00:00", summary: { rows_total: 3, dry_run: true, applied_job_id: null, diff, warnings: [] }, actor: "user", source: "upload" }));
}
const wrap = (j: ImportJob, onApplied = vi.fn()) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">
        <ImportPreview job={j} onApplied={onApplied} onCancel={vi.fn()} />
      </I18nProvider>
    </QueryClientProvider>,
  );

const PARTIAL = {
  on_conflict: "keep",
  counts: {
    meeting_requests: { create: 0, update: 0, archive: 1508, unchanged: 6, conflict: 0 },
    sections: { create: 0, update: 2, archive: 1268, unchanged: 4, conflict: 0 },
  },
  rows: [
    { change: "archive", entity: "sections", id: 7, key: "TST 101|x|1", fields: [{ field: "archived", from: false, to: true }] },
    { change: "update", entity: "sections", id: 8, key: "TST 102|x|1", fields: [{ field: "enrolment", from: 30, to: 31 }] },
  ],
  rows_total: 2778,
  conflicts_total: 0,
};

describe("archives are named and a large one needs a confirm (E2EA2-F01)", () => {
  it("says how many records are not in the file and will be archived, apart from the changes", () => {
    wrap(job(PARTIAL));
    const words = screen.getByTestId("import-preview-summary");
    expect(words).toHaveTextContent("2.776 kayıt dosyada yok; arşivlenecek");
    expect(words).toHaveTextContent("2 kayıt değişecek");
    expect(words).not.toHaveTextContent("2.778 kayıt değişecek");
    expect(screen.getByTestId("import-preview-entity-sections")).toHaveTextContent("1.268 arşivlenecek");
    fireEvent.click(screen.getByTestId("import-show-changes"));
    expect(screen.getByText("Arşivlenecek")).toBeInTheDocument();
  });

  it("Uygula opens a confirm when most of an entity would be archived; only 'Yine de uygula' applies", async () => {
    const onApplied = vi.fn();
    wrap(job(PARTIAL), onApplied);
    fireEvent.click(screen.getByTestId("import-apply"));
    const dialog = await screen.findByTestId("import-archive-confirm");
    expect(dialog).toHaveTextContent("Ders talepleri: 1.508 kayıt (%100) dosyada yok ve arşivlenecek");
    expect(posts).toHaveLength(0);
    fireEvent.click(within(dialog).getByTestId("import-archive-confirm-apply"));
    await vi.waitFor(() => expect(onApplied).toHaveBeenCalled());
    expect(posts.filter((p) => p.endsWith("/imports/51/apply"))).toHaveLength(1);
  });

  it("a small archive applies at once", async () => {
    const onApplied = vi.fn();
    const small = { ...PARTIAL, counts: { sections: { create: 0, update: 0, archive: 3, unchanged: 1265, conflict: 0 } }, rows_total: 3 };
    wrap(job(small), onApplied);
    fireEvent.click(screen.getByTestId("import-apply"));
    await vi.waitFor(() => expect(onApplied).toHaveBeenCalled());
    expect(screen.queryByTestId("import-archive-confirm")).toBeNull();
  });
});

describe("a composite id never drops the diff (E2EA-F03)", () => {
  const COMPOSITE = {
    on_conflict: "keep",
    counts: { section_instructors: { create: 288, update: 0, unchanged: 0, conflict: 0 }, sections: { create: 32, update: 0, archive: 0, unchanged: 800, conflict: 0 } },
    rows: [
      { change: "create", entity: "section_instructors", id: [2149, 17], key: null },
      { change: "create", entity: "sections", id: 2149, key: "TST 101|x|1" },
    ],
    rows_total: 320,
    conflicts_total: 0,
  };
  it("parses an array id as one string id", () => {
    const d = importDiff({ summary: { diff: COMPOSITE } } as never);
    expect(d).not.toBeNull();
    expect(d!.rows[0]!.id).toBe("2149:17");
  });
  it("keeps the counts even when a row is unreadable", () => {
    const broken = { ...COMPOSITE, rows: [{ change: "moved", entity: 3 }, COMPOSITE.rows[1]] };
    const d = importDiff({ summary: { diff: broken } } as never);
    expect(d!.counts.sections!.create).toBe(32);
    expect(d!.rows).toHaveLength(1);
  });
  it("the card shows the counts, never the no-diff line", () => {
    wrap(job(COMPOSITE));
    expect(screen.getByTestId("import-preview-summary")).toHaveTextContent("320 yeni kayıt eklenecek");
    expect(screen.queryByText("Bu önizlemede değişiklik listesi yok.")).toBeNull();
  });
});
