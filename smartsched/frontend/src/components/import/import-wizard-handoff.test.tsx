// HB-23c (helper-file-router.md §6.5, §10, §11.2): a file handed over by the helper's card. /import reads `term` and
// `from=helper`, shows the handed-over file row in place of the empty zone ("Yardımcıdan geldi", ✕ "Dosyayı kaldır"),
// focuses its own primary ("Önizle"), and sends `upload_token` instead of the bytes. ✕ deletes the stage and focuses the
// drop zone's button. An expired / used token (410) brings the zone back with the expiry line.
// The setup wizard's file list (FileDrop) lists the handed-over file as row 1 with the chip and starts with its token.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useFileHandoffStore, type FileHandoff } from "@/components/helper/file-handoff";
import { importJob } from "@/lib/api/adapters";
import { HttpError } from "@/lib/api/client";
import { ImportJob } from "@/lib/api/schemas";
import { I18nProvider } from "@/lib/i18n/provider";

const nav = vi.hoisted(() => ({ search: "kind=planning-list&term=12&from=helper", replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/import",
  useRouter: () => ({ push: vi.fn(), replace: (u: string) => { nav.replace(u); nav.search = u.split("?")[1] ?? ""; }, refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), message: vi.fn() }) }));
const GUZ = { id: 11, code: "2026-FALL", name: "Güz 2026-2027", kind: "REGULAR", start_date: "2026-09-21", end_date: "2027-01-10", week_count: 14, is_active: true };
const BAHAR = { id: 12, code: "2026-SPRING", name: "Bahar 2026", kind: "REGULAR", start_date: "2026-02-16", end_date: "2026-06-05", week_count: 14, is_active: false };
vi.mock("@/components/shell/term-switcher", () => ({ useActiveTerm: () => ({ term: GUZ, terms: [GUZ, BAHAR], isLoading: false }) }));
const up = vi.hoisted(() => ({ fn: vi.fn() }));
vi.mock("@/lib/api/shell-extra", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/shell-extra")>()),
  uploadImportWithProgress: (...a: unknown[]) => up.fn(...a),
}));
vi.mock("@/lib/api/ai-policy", () => ({ useAiPolicy: () => ({ data: { intake_enabled: true } }) }));

import { FileDrop } from "@/components/onboarding/file-drop";
import { ImportWizard } from "./import-wizard";

const TOKEN = "eyJzaWQiOiJzdGFnZTEyMyJ9.c2lnbmF0dXJlLXNpZ25hdHVyZQ";
const PREVIEW = { id: 41, kind: "planning-list", filename: "Bahar_son.xlsx", status: "DONE", term_code: "2026-SPRING", created_at: "2026-10-18T09:00:00", summary: { rows_total: 10, dry_run: true, applied_job_id: null, warnings: [] }, actor: "user", source: "helper" };

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
let calls: string[];

function handoff(over: Partial<FileHandoff> = {}): FileHandoff {
  return {
    featureId: "import",
    kind: "planning_list",
    params: { kind: "planning-list", term_id: 12 },
    items: [{ token: TOKEN, sid: "stage123", name: "Bahar_son.xlsx", size: 1_258_291, format: "xlsx", expiresAt: Date.now() + 9 * 60_000 }],
    at: Date.now(),
    ...over,
  };
}

beforeEach(() => {
  nav.search = "kind=planning-list&term=12&from=helper";
  calls = [];
  window.sessionStorage.clear();
  up.fn.mockReset().mockResolvedValue(ImportJob.parse(importJob(PREVIEW)));
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${String(url).split("?")[0]}`);
      return res(init?.method === "DELETE" ? 204 : 200, init?.method === "DELETE" ? undefined : []);
    }),
  );
  useFileHandoffStore.getState().set(handoff());
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  useFileHandoffStore.getState().clear();
});

const wrap = (ui: ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">{ui}</I18nProvider>
    </QueryClientProvider>,
  );

describe("/import with a file from the helper", () => {
  it("shows the handed-over row instead of the empty zone, presets the file's term and focuses Önizle", async () => {
    wrap(<ImportWizard />);
    const row = screen.getByTestId("import-handed-file");
    expect(row).toHaveTextContent("Bahar_son.xlsx");
    expect(row).toHaveTextContent("Yardımcıdan geldi");
    expect(screen.getByRole("button", { name: "Dosyayı kaldır: Bahar_son.xlsx" })).toBeInTheDocument();
    expect(screen.queryByTestId("import-dropzone")).toBeNull();
    expect((screen.getByLabelText("Hedef dönem") as HTMLSelectElement).value).toBe("12");
    await waitFor(() => expect(document.activeElement).toBe(screen.getByTestId("import-start")));
    expect(screen.getByTestId("import-start")).not.toBeDisabled();
  });

  it("sends upload_token (no bytes), with the term of the address, and forgets the hand-over once used", async () => {
    wrap(<ImportWizard />);
    fireEvent.click(screen.getByTestId("import-start"));
    await screen.findByTestId("import-preview");
    expect(up.fn).toHaveBeenCalledTimes(1);
    const [kind, file, term, opts] = up.fn.mock.calls[0]!;
    expect(kind).toBe("planning-list");
    expect(file).toBeNull();
    expect(term).toMatchObject({ id: 12 });
    expect(opts).toMatchObject({ dryRun: true, uploadToken: TOKEN, filename: "Bahar_son.xlsx" });
    expect(useFileHandoffStore.getState().handoff).toBeNull();
  });

  it("✕ deletes the stage and gives the focus to the drop zone's button", async () => {
    wrap(<ImportWizard />);
    fireEvent.click(screen.getByTestId("import-handed-file-remove"));
    await waitFor(() => expect(calls).toContain("DELETE /api/v1/helper/files/stage123"));
    expect(screen.queryByTestId("import-handed-file")).toBeNull();
    await waitFor(() => expect(screen.getByTestId("import-dropzone").contains(document.activeElement)).toBe(true));
    expect(useFileHandoffStore.getState().handoff).toBeNull();
    expect(window.sessionStorage.getItem("smartsched.helper.fileHandoff")).toBeNull();
  });

  it("an expired token (410 on the upload) shows the expiry line and brings the zone back, kind and term kept", async () => {
    up.fn.mockRejectedValueOnce(new HttpError(410, "gone", { code: "stage_expired" }));
    wrap(<ImportWizard />);
    fireEvent.click(screen.getByTestId("import-start"));
    expect(await screen.findByTestId("import-handed-expired")).toHaveTextContent("Dosyanın süresi doldu (10 dakika). Yeniden seçin.");
    expect(screen.getByTestId("import-dropzone")).toBeInTheDocument();
    expect((screen.getByLabelText("Hedef dönem") as HTMLSelectElement).value).toBe("12");
    await waitFor(() => expect(screen.getByTestId("import-dropzone").contains(document.activeElement)).toBe(true));
  });

  it("the 10 minutes passing on the page give the same expiry line", async () => {
    useFileHandoffStore.getState().set(handoff({ items: [{ ...handoff().items[0]!, expiresAt: Date.now() + 30 }] }));
    wrap(<ImportWizard />);
    expect(screen.getByTestId("import-handed-file")).toBeInTheDocument();
    expect(await screen.findByTestId("import-handed-expired", undefined, { timeout: 2000 })).toBeInTheDocument();
  });

  it("a hand-over for another kind is not shown (the page's own zone stays)", () => {
    nav.search = "kind=exam-list&from=helper";
    wrap(<ImportWizard />);
    expect(screen.queryByTestId("import-handed-file")).toBeNull();
    expect(screen.getByTestId("import-dropzone")).toBeInTheDocument();
  });

  it("without from=helper the address's term is still read (the plain link /import?kind=…&term=…)", () => {
    useFileHandoffStore.getState().clear();
    nav.search = "kind=planning-list&term=12";
    wrap(<ImportWizard />);
    expect((screen.getByLabelText("Hedef dönem") as HTMLSelectElement).value).toBe("12");
  });
});

describe("setup wizard file list with a file from the helper", () => {
  it("lists the staged file as row 1 with the chip and starts with its token", () => {
    useFileHandoffStore.getState().set(handoff({ featureId: "onboarding", kind: "timetable_other", params: {} }));
    const onStart = vi.fn();
    wrap(<FileDrop busy={false} onStart={onStart} />);
    const row = screen.getByTestId("onboarding-handed-file");
    expect(row).toHaveTextContent("Bahar_son.xlsx");
    expect(row).toHaveTextContent("Yardımcıdan geldi");
    expect(screen.getByTestId("onboarding-start")).toHaveTextContent("1");
    fireEvent.click(screen.getByTestId("onboarding-start"));
    expect(onStart).toHaveBeenCalledTimes(1);
    const [files, opts] = onStart.mock.calls[0]!;
    expect(files).toEqual([]);
    expect(opts).toMatchObject({ uploadTokens: [TOKEN] });
    expect(useFileHandoffStore.getState().handoff).toBeNull();
  });

  it("several files from the helper arrive as the browser's File objects (no stage)", () => {
    const a = new File(["a"], "a.xlsx");
    const b = new File(["bb"], "b.ics");
    useFileHandoffStore.getState().set(
      { featureId: "onboarding", kind: null, params: {}, items: [a, b].map((f) => ({ token: null, sid: null, name: f.name, size: f.size, format: null, expiresAt: null })), at: Date.now() },
      [a, b],
    );
    const onStart = vi.fn();
    wrap(<FileDrop busy={false} onStart={onStart} />);
    expect(screen.getAllByTestId("onboarding-handed-file")).toHaveLength(2);
    fireEvent.click(screen.getByTestId("onboarding-start"));
    const [files, opts] = onStart.mock.calls[0]!;
    expect(files).toEqual([a, b]);
    expect(opts.uploadTokens ?? []).toEqual([]);
  });

  it("✕ on the handed row deletes the stage and the row", async () => {
    useFileHandoffStore.getState().set(handoff({ featureId: "onboarding", params: {} }));
    wrap(<FileDrop busy={false} onStart={vi.fn()} />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Dosyayı kaldır: Bahar_son.xlsx" })));
    await waitFor(() => expect(calls).toContain("DELETE /api/v1/helper/files/stage123"));
    expect(screen.queryByTestId("onboarding-handed-file")).toBeNull();
  });
});
