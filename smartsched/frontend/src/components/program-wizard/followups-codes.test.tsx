/**
 * Programme drafts follow-ups (backend 2026-10-16): `instructor_archived_namesake` gets "Bu kişiyi kullan" that sets
 * the slot to `{id}`; `program_restored` / `instructor_restored` are info lines; a pre-check of a draft with errors
 * answers 422 `{message, message_tr, issues, errors}` and the panel lists the issues with "Düzelt"; the commit's
 * `created.restored` is summarised. Real rows: MBG Tezli YL (R182–R198), MBG 532 Epigenetik §1.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { HttpError } from "@/lib/api/client";
import { CreatedIds, Validation, type DraftIssue } from "@/lib/api/program-drafts";
import { I18nProvider } from "@/lib/i18n/provider";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const state = vi.hoisted(() => ({ precheck: null as null | (() => unknown) }));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  request: async (path: string) => {
    if (path === "/terms/3/instructors/load") return { term_id: 3, limit: 20, items: [] };
    if (path === "/rooms") return [];
    if (path === "/program-drafts/7/precheck") return state.precheck!();
    throw new Error(`unexpected ${path}`);
  },
}));

import { InstructorsStep, PrecheckPanel } from "./steps";
import { namesakeRecord, newCourse, newPayload, newSection, refusedIssues, restoredSummary, type Payload } from "./wizard-model";

const SP = "courses.c1.sections.s1";
const namesake: DraftIssue = {
  step: "instructors",
  level: "error",
  code: "instructor_archived_namesake",
  path: `${SP}.instructors.0`,
  text: { tr: "'A. K.' adıyla arşivlenmiş bir öğretim elemanı var (Moleküler Biyoloji ve Genetik). Aynı kişiyse listeden bu kaydı seçin; değilse adı ayırt edici yazın.", en: "An archived instructor is named 'A. K.' (Moleküler Biyoloji ve Genetik). If it is the same person, pick that record; otherwise write the name distinctly." },
  vars: { id: 412, name: "A. K.", units: ["Moleküler Biyoloji ve Genetik"] },
};

function payload(): Payload {
  const p = newPayload();
  const c = { ...newCourse({ code: "MBG 532", name: "Epigenetik", t: 3 }), key: "c1", sections: [{ ...newSection("1", 12), key: "s1", instructors: [{ name: "A. K." }] }] };
  return { ...p, courses: [c] };
}

function wrap(ui: React.ReactNode, locale: "tr" | "en" = "tr") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale={locale}>{ui}</I18nProvider>
    </QueryClientProvider>,
  );
}

describe("draft issue codes (model)", () => {
  it("reads the archived namesake's record and ignores other codes", () => {
    expect(namesakeRecord(namesake)).toEqual({ id: 412, name: "A. K.", units: ["Moleküler Biyoloji ve Genetik"] });
    expect(namesakeRecord({ code: "instructor_restored", vars: { id: 412 } })).toBeNull();
    expect(namesakeRecord({ code: "instructor_archived_namesake", vars: {} })).toBeNull();
  });

  it("reads the 422 issues of a refused pre-check or commit", () => {
    const e = new HttpError(422, "the draft has errors", { detail: { message: "the draft has errors", message_tr: "Taslakta düzeltilmesi gereken hatalar var", issues: [namesake, { bogus: true }], errors: 1 } });
    const r = refusedIssues(e);
    expect(r?.errors).toBe(1);
    expect(r?.issues.map((i) => i.code)).toEqual(["instructor_archived_namesake"]);
    expect(refusedIssues(new HttpError(409, "x", { detail: "x" }))).toBeNull();
    expect(refusedIssues(new Error("x"))).toBeNull();
  });

  it("summarises the archived records a commit reopened", () => {
    const made = CreatedIds.parse({ program_id: 9, restored: { faculty_id: null, program_id: 9, courses: [1, 2], people: [412] } });
    expect(restoredSummary(made)).toEqual({ program: true, courses: 2, people: 1 });
    expect(restoredSummary(CreatedIds.parse({ restored: { faculty_id: null, program_id: null, courses: [], people: [] } }))).toBeNull();
    expect(restoredSummary(CreatedIds.parse({}))).toBeNull();
  });
});

function Instructors({ issues }: { issues: DraftIssue[] }) {
  const [p, setP] = useState(payload);
  const v = Validation.parse({ draft_id: 7, version: 2, can_commit: false, counts: {}, summary: {}, issues });
  return (
    <>
      <InstructorsStep p={p} update={(fn) => setP(fn)} v={v} termId={3} />
      <output data-testid="slot">{JSON.stringify(p.courses[0]!.sections[0]!.instructors)}</output>
    </>
  );
}

describe("Kişiler step", () => {
  it("offers 'Bu kişiyi kullan' on an archived namesake and sets the slot to that record", async () => {
    const user = userEvent.setup();
    wrap(<Instructors issues={[namesake]} />);
    const row = await screen.findByTestId("instructor-row");
    expect(within(row).getByTestId("field-issues")).toHaveTextContent("arşivlenmiş bir öğretim elemanı var");
    await user.click(within(row).getByRole("button", { name: "Arşivdeki A. K. kaydını kullan" }));
    expect(JSON.parse(screen.getByTestId("slot").textContent ?? "[]")).toEqual([{ id: 412, name: "A. K." }]);
  });

  it("shows instructor_restored as an info line without an action", async () => {
    const restored: DraftIssue = { ...namesake, level: "info", code: "instructor_restored", text: { tr: "'A. K.' → arşivdeki A. K. kaydı yeniden kullanılacak", en: "'A. K.' → the archived record of A. K. will be reused" }, vars: { id: 412 } };
    wrap(<Instructors issues={[restored]} />, "en");
    expect(await screen.findByText(/the archived record of A. K. will be reused/)).toBeInTheDocument();
    expect(screen.queryByTestId("use-archived-person")).toBeNull();
  });
});

describe("pre-check panel", () => {
  it("lists the draft's errors of a 422 with Düzelt to their step", async () => {
    const user = userEvent.setup();
    const onFix = vi.fn();
    state.precheck = () => {
      throw new HttpError(422, "the draft has errors", { detail: { message: "the draft has errors", message_tr: "Taslakta düzeltilmesi gereken hatalar var", issues: [namesake], errors: 1 } });
    };
    wrap(<PrecheckPanel draftId={7} result={null} onResult={() => undefined} onFix={onFix} />);
    await user.click(screen.getByTestId("precheck-run"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Ön kontrol çalışmadı: taslakta 1 hata var.");
    const list = screen.getByTestId("refused-issues");
    expect(list).toHaveTextContent("arşivlenmiş bir öğretim elemanı var");
    await user.click(within(list).getByRole("button", { name: "Düzelt" }));
    expect(onFix).toHaveBeenCalledWith("instructors");
  });
});
