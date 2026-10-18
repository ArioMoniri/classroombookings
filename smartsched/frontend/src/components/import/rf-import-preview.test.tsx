// RF-06 / RF-08 (rf-f-2026-10-18): every workbook upload is a preview first (dry_run), the diff reads in plain words,
// one "Uygula" applies it (POST /imports/{id}/apply), a second apply shows the server's refusal, keep/take sits
// under "Gelişmiş", and the history says who imported (seed / CLI → system) with the report and a download link.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { importJob } from "@/lib/api/adapters";
import { ImportJob } from "@/lib/api/schemas";
import { I18nProvider } from "@/lib/i18n/provider";

const nav = vi.hoisted(() => ({ search: "kind=exam-list", replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/import",
  useRouter: () => ({ push: vi.fn(), replace: (u: string) => { nav.replace(u); nav.search = u.split("?")[1] ?? ""; }, refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), message: vi.fn() }) }));
const TERM = { id: 3, code: "2026-FINAL", name: "2025-2026 Final", kind: "FINAL", start_date: "2026-06-01", end_date: "2026-06-20", week_count: 3, is_active: true };
vi.mock("@/components/shell/term-switcher", () => ({ useActiveTerm: () => ({ term: TERM, terms: [TERM], isLoading: false }) }));
const up = vi.hoisted(() => ({ fn: vi.fn() }));
vi.mock("@/lib/api/shell-extra", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/shell-extra")>()),
  uploadImportWithProgress: (...a: unknown[]) => up.fn(...a),
}));

import { ImportWizard } from "./import-wizard";

const DIFF = {
  on_conflict: "keep",
  counts: { exam_requests: { create: 0, update: 3, unchanged: 920, conflict: 1 }, rooms: { create: 1, update: 0, unchanged: 60, conflict: 0 } },
  rows: [
    { change: "conflict", entity: "exam_requests", id: 1, key: "EX:2026-FINAL:ACU 1421", fields: [], conflicts: [{ field: "enrolment", planner: 30, file: 28, previous_import: 26, resolution: "kept" }] },
    { change: "update", entity: "exam_requests", id: 4, key: "EX:2026-FINAL:FIZ 101", fields: [{ field: "archived", from: false, to: true }] },
    { change: "create", entity: "rooms", id: 61, key: "C 607" },
  ],
  rows_total: 3,
  conflicts_total: 1,
};
const PREVIEW = { id: 41, kind: "exam-list", filename: "final.xlsx", status: "DONE", term_code: "2026-FINAL", created_at: "2026-10-18T09:00:00", summary: { rows_total: 924, dry_run: true, applied_job_id: null, diff: DIFF, warnings: [] }, actor: "user", source: "upload", created_by_name: "Ayşe Yılmaz" };
const APPLIED = { ...PREVIEW, id: 42, status: "DONE", summary: { rows_total: 924, created: { rooms: 1 }, updated: { exam_requests: 3 }, preview_of: 41, warnings: [] } };

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
let calls: { key: string; body: unknown }[];
let routes: Record<string, (b: unknown) => Response>;
beforeEach(() => {
  nav.search = "kind=exam-list";
  calls = [];
  up.fn.mockReset().mockResolvedValue(adaptJob(PREVIEW));
  routes = {
    "GET /api/v1/imports": () => res(200, []),
    "POST /api/v1/imports/41/apply": () => res(202, APPLIED),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${String(url).split("?")[0]}`;
      const body = init?.body && typeof init.body === "string" ? JSON.parse(init.body) : undefined;
      calls.push({ key, body });
      return routes[key]?.(body) ?? res(200, []);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

/** what the upload helper resolves with: the adapted, schema-checked job */
function adaptJob(raw: unknown) {
  return ImportJob.parse(importJob(raw));
}

const wrap = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">
        <ImportWizard />
      </I18nProvider>
    </QueryClientProvider>,
  );

async function uploadFile() {
  wrap();
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(["x"], "final.xlsx")] } });
  fireEvent.click(screen.getByTestId("import-start"));
  return screen.findByTestId("import-preview");
}

describe("preview first (RF-06)", () => {
  it("uploads as a dry run and the primary button says 'Önizle'", async () => {
    await uploadFile();
    expect(up.fn).toHaveBeenCalledTimes(1);
    expect(up.fn.mock.calls[0]![3]).toMatchObject({ dryRun: true });
  });

  it("reads the diff in plain words: added, changed, kept your edit, per entity", async () => {
    const card = await uploadFile();
    const words = within(card).getByTestId("import-preview-summary");
    expect(words).toHaveTextContent("1 yeni kayıt eklenecek");
    expect(words).toHaveTextContent("3 kayıt değişecek");
    expect(words).toHaveTextContent("1 düzenlemeniz korunacak");
    expect(words).toHaveTextContent("980 kayıt aynı kalacak");
    expect(within(card).getByTestId("import-preview-entity-exam_requests")).toHaveTextContent("Sınav talepleri");
    expect(within(card).getByTestId("import-preview-entity-rooms")).toHaveTextContent("Derslikler");
    const conflict = within(card).getByTestId("import-conflict-0");
    expect(conflict).toHaveTextContent("Öğrenci sayısı");
    expect(conflict).toHaveTextContent("Sizin değeriniz");
    expect(conflict).toHaveTextContent("30");
    expect(conflict).toHaveTextContent("Dosyadaki");
    expect(conflict).toHaveTextContent("28");
    expect(conflict).toHaveTextContent("Önceki içe aktarma");
    expect(conflict).toHaveTextContent("Düzenlemeniz korunacak");
    // no raw keys
    expect(card).not.toHaveTextContent("exam_requests");
    expect(card).not.toHaveTextContent("enrolment");
  });

  it("one 'Uygula' applies the preview once and shows the import's report", async () => {
    await uploadFile();
    fireEvent.click(screen.getByTestId("import-apply"));
    expect(await screen.findByTestId("import-report")).toBeInTheDocument();
    expect(calls.filter((c) => c.key === "POST /api/v1/imports/41/apply")).toHaveLength(1);
    expect(calls.find((c) => c.key === "POST /api/v1/imports/41/apply")!.body).toEqual({ on_conflict: null });
  });

  it("a second apply shows the server's refusal inline, in Turkish", async () => {
    routes["POST /api/v1/imports/41/apply"] = () => res(409, { detail: { code: "preview_already_applied", message: "this preview was applied already", message_en: "this preview was applied already", message_tr: "Bu önizleme zaten uygulandı.", applied_job_id: 42 } });
    await uploadFile();
    fireEvent.click(screen.getByTestId("import-apply"));
    const alert = await screen.findByTestId("import-apply-error");
    expect(alert).toHaveTextContent("Bu önizleme zaten uygulandı.");
    expect(screen.queryByTestId("import-report")).toBeNull();
  });

  it("keep / take sits under 'Gelişmiş'; 'Dosyadakini al' is sent with the apply", async () => {
    const card = await uploadFile();
    expect(within(card).queryByLabelText("Dosyadakini al")).toBeNull();
    fireEvent.click(within(card).getByTestId("import-advanced"));
    const take = within(card).getByLabelText("Dosyadakini al");
    expect(within(card).getByLabelText("Düzenlemelerimi koru")).toBeChecked();
    fireEvent.click(take);
    expect(within(card).getByTestId("import-conflict-0")).toHaveTextContent("Dosyadaki değer yazılacak");
    fireEvent.click(screen.getByTestId("import-apply"));
    await waitFor(() => expect(calls.find((c) => c.key === "POST /api/v1/imports/41/apply")?.body).toEqual({ on_conflict: "take" }));
  });
});

describe("history: who imported, the report and the file (RF-08)", () => {
  const SEED = { id: 5, kind: "planning-list", filename: "bahar.xlsx", status: "DONE", created_at: "2026-10-16T07:00:00", actor: "system", source: "seed", created_by_name: null, summary: { rows_total: 1529, created: { sections: 900 }, updated: {}, rows_skipped: [{ row: 12, reason: "boş ders kodu" }], warnings: [] } };
  const CLI = { id: 6, kind: "exam-list", filename: "final.xlsx", status: "FAILED", error: "dosya okunamadı", created_at: "2026-10-16T07:05:00", actor: "system", source: "cli", created_by_name: null, summary: {} };
  const UP = { id: 7, kind: "exam-list", filename: "final2.xlsx", status: "DONE", created_at: "2026-10-17T07:05:00", actor: "user", source: "upload", created_by_name: "Ayşe Yılmaz", summary: { rows_total: 10, dry_run: true, applied_job_id: 8, diff: DIFF } };

  it("names the importer, opens the report and links the workbook", async () => {
    nav.search = "";
    routes["GET /api/v1/imports"] = () => res(200, [UP, CLI, SEED]);
    wrap();
    const seed = await screen.findByTestId("import-history-5");
    expect(seed).toHaveTextContent("İlk kurulum (sistem)");
    expect(screen.getByTestId("import-history-6")).toHaveTextContent("Sistem (komut satırı)");
    expect(screen.getByTestId("import-history-6")).toHaveTextContent("Başarısız");
    expect(screen.getByTestId("import-history-7")).toHaveTextContent("Yükleyen: Ayşe Yılmaz");
    expect(screen.getByTestId("import-history-7")).toHaveTextContent("Önizleme · uygulandı");
    const link = within(seed).getByRole("link", { name: /İndir/ });
    expect(link).toHaveAttribute("href", "/api/v1/imports/5/file");
    // a failed CLI job has no file
    expect(within(screen.getByTestId("import-history-6")).queryByRole("link", { name: /İndir/ })).toBeNull();
    fireEvent.click(within(seed).getByTestId("import-history-report-5"));
    const report = within(seed).getByTestId("import-history-detail-5");
    expect(report).toHaveTextContent("1.529");
    expect(report).toHaveTextContent("boş ders kodu");
  });
});
