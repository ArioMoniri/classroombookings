/**
 * HB-23c (helper-file-router.md §5, §7, §10, §11.2 "file-card.test.tsx" + "a11y"): every state shows at most one
 * primary; the certainty is a word; warnings have an icon and their text (`bad` → alert); "Bu dosya nedir?" is folded;
 * the short label under 640 px keeps the full one as the name; the focus goes to the card title; the live line is said
 * once; the primary hands over (audit call, then the page; the token never in the address); the chooser is a radiogroup.
 */
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FileCard } from "@/lib/api/helper-files";
import { EntryView } from "./cards/render";
import { useFileHandoffStore } from "./file-handoff";
import { useHelperStore, type FileEntry } from "./helper-store";
import { makeHost, renderHelper, resetHelperStore } from "./test-helpers";
import { activation } from "./use-helper-runner";

const PERMS = vi.hoisted(() => ({ list: ["planning.edit", "setup.users"] as string[] }));
vi.mock("@/lib/api/shell-extra", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/shell-extra")>()),
  usePermissions: () => ({ perms: PERMS.list, me: undefined, can: (p: string | readonly string[] | undefined) => (!p ? true : Array.isArray(p) ? p.some((x) => PERMS.list.includes(x)) : PERMS.list.includes(p as string)) }),
}));

const TOKEN = `${btoa(JSON.stringify({ sid: "stage42" })).replace(/=+$/, "")}.c2lnbmF0dXJlLXNpZ25hdHVyZQ`;
const STAGE = { upload_token: TOKEN, expires_at: new Date(Date.now() + 600_000).toISOString(), size: 1_258_291, format: "xlsx" };

const tr = (t: string, e = t) => ({ tr: t, en: e });
const DETECTED: FileCard = {
  v: 1,
  id: "a1b2c3d4e5f6",
  type: "file",
  action: "classify_file",
  title: tr("Bu bir haftalık derslik takvimi", "This is a weekly room timetable"),
  state: "detected",
  kind: "weekly_grid",
  kind_label: tr("Haftalık derslik takvimi", "Weekly room timetable"),
  certainty: "sure",
  format: "xlsx",
  evidence: { tr: ['19 sayfa, her biri bir hafta ("1. Hafta"); üstte gün adları, solda ders saatleri, 64 derslik sütunu'], en: ['19 sheets, one per week ("1. Hafta"); day names on top, periods on the left, 64 room columns'] },
  term: { term_id: 12, name: tr("Bahar 2026"), source: "file_name", matches_active: false },
  warnings: [
    { code: "term_mismatch", status: "warn", message: tr("Dosya Bahar 2026 diyor; şu an Güz 2026-2027 seçili. Düğme dosyanın dönemine aktarır.", "The file says Bahar 2026; Güz 2026-2027 is selected now.") },
    { code: "many_sheets", status: "info", message: tr("Dosyada 19 sayfa var; ilk sayfa okundu.", "The file has 19 sheets.") },
  ],
  primary: { feature_id: "import", params: { kind: "weekly-grid", term_id: 12, year: 2026 }, label: tr("Bahar 2026 dönemine haftalık derslik takvimi olarak aktar", "Import into Bahar 2026 as weekly room timetable"), label_short: tr("Bahar 2026'ya aktar", "Import into Bahar 2026"), carries_file: true },
  secondary: [{ feature_id: "onboarding", params: {}, label: tr("Kurulum sihirbazında aç", "Open in the setup wizard"), label_short: null, carries_file: true }],
  explain: { tr: ["Haftalık derslik takvimi, her hafta için bir sayfadır.", "İçe aktarınca önce bir önizleme görürsünüz."], en: ["A weekly room timetable has one sheet per week."] },
  examples: [],
  ai_sorted: false,
};

let fetches: { key: string; body: unknown }[];
let answer: (key: string, body: unknown) => Response;
const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

function Thread() {
  const entries = useHelperStore((s) => s.entries);
  return (
    <div>
      {entries.map((e) => (
        <div key={e.key} data-entry={e.key}>
          <EntryView entry={e} />
        </div>
      ))}
    </div>
  );
}

function seed(view: FileEntry["view"], over: Partial<FileEntry> = {}) {
  const key = useHelperStore.getState().pushFile([{ name: "Bahar_son.xlsx", size: 1_258_291 }]);
  useHelperStore.getState().updateFile(key, { phase: "shown", view, stage: STAGE, seq: 1, ...over });
  return key;
}

let host: ReturnType<typeof makeHost>;
const show = () => renderHelper(<Thread />, { host });

beforeEach(() => {
  resetHelperStore();
  useFileHandoffStore.getState().clear();
  PERMS.list = ["planning.edit", "setup.users"];
  host = makeHost({ can: (p) => (!p ? true : Array.isArray(p) ? p.some((x) => PERMS.list.includes(x)) : PERMS.list.includes(p as string)) });
  vi.spyOn(activation, "trusted").mockReturnValue(true);
  fetches = [];
  answer = () => res(200, { ok: true, href_params: {} });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${String(url).split("?")[0]}`;
      const body = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
      fetches.push({ key, body });
      return answer(key, body);
    }),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("detected", () => {
  it("one primary, the certainty word, evidence, term, warnings with icon + text, folded disclosure", () => {
    seed({ kind: "card", card: DETECTED });
    show();
    const card = screen.getByTestId("helper-card-file-detected");
    expect(card).toHaveAttribute("role", "group");
    expect(within(card).getByText("Bu bir haftalık derslik takvimi")).toHaveAttribute("tabindex", "-1");
    expect(within(card).getByTestId("helper-file-certainty")).toHaveTextContent("Eminim");
    expect(card.textContent).not.toMatch(/\d+ ?%|0[.,]9/);
    expect(within(card).getByTestId("helper-file-term")).toHaveTextContent("Dönem: Bahar 2026 (dosya adından)");
    const warn = within(card).getByTestId("helper-file-warning-term_mismatch");
    expect(warn.querySelector("svg")).not.toBeNull();
    expect(warn).toHaveTextContent("Düğme dosyanın dönemine aktarır.");
    expect(within(card).getAllByTestId("helper-file-primary")).toHaveLength(1);
    expect(within(card).getByTestId("helper-file-other")).toHaveTextContent("Başka bir tür seç");
    expect(within(card).getByTestId("helper-file-onboarding")).toHaveTextContent("Kurulum sihirbazında aç");
    const what = within(card).getByTestId("helper-file-what");
    expect(what).toHaveAttribute("aria-expanded", "false");
    expect(within(card).queryByTestId("helper-file-explain")).toBeNull();
    expect(card).toHaveTextContent("Dosya yalnızca türünü anlamak için okunur ve en çok 10 dakika şifreli tutulur. Açılan sayfada Önizle'ye basana kadar içe aktarma kaydına dönüşmez; veriler yalnızca Uygula ile kayıtlara işlenir.");
    fireEvent.click(what);
    expect(within(card).getByTestId("helper-file-explain")).toHaveTextContent("Haftalık derslik takvimi, her hafta için bir sayfadır.");
  });

  it("a bad warning is an alert; the user bubble shows the file chip (name · size)", () => {
    seed({ kind: "card", card: { ...DETECTED, warnings: [{ code: "too_large_for_target", status: "bad" as const, message: tr("Kullanıcı listesi en çok 5 MB olabilir; dosya 6 MB. Listeyi bölün.") }] } });
    show();
    expect(screen.getByTestId("helper-file-warning-too_large_for_target")).toHaveAttribute("role", "alert");
    expect(screen.getByTestId("helper-file-chip")).toHaveTextContent("Bahar_son.xlsx");
    expect(screen.getByTestId("helper-file-chip")).toHaveTextContent("1,2 MB");
  });

  it("the short label shows under 640 px and the full label stays the accessible name", () => {
    seed({ kind: "card", card: DETECTED });
    show();
    const primary = screen.getByTestId("helper-file-primary");
    expect(primary).toHaveAccessibleName("Bahar 2026 dönemine haftalık derslik takvimi olarak aktar");
    expect(within(primary).getByTestId("helper-file-primary-short")).toHaveTextContent("Bahar 2026'ya aktar");
    expect(within(primary).getByTestId("helper-file-primary-short").className).toContain("sm:hidden");
  });

  it("the focus goes to the card title when the card arrives, and the live line is said once", async () => {
    const key = useHelperStore.getState().pushFile([{ name: "Bahar_son.xlsx", size: 1_258_291 }]);
    show();
    expect(screen.getByTestId("helper-file-reading")).toHaveTextContent("Dosya okunuyor…");
    expect(within(screen.getByTestId("helper-file-reading")).getByRole("status")).toBeInTheDocument();
    act(() => useHelperStore.getState().updateFile(key, { phase: "shown", view: { kind: "card", card: DETECTED }, stage: STAGE, seq: 1 }));
    await waitFor(() => expect(document.activeElement).toHaveTextContent("Bu bir haftalık derslik takvimi"));
    const live = screen.getByTestId("helper-file-live");
    expect(live).toHaveAttribute("role", "status");
    expect(live).toHaveTextContent("Bahar_son.xlsx: Haftalık derslik takvimi, Eminim. Bahar 2026 dönemine haftalık derslik takvimi olarak aktar");
    // an unrelated update (a notice) does not repeat it
    const before = live.textContent;
    act(() => useHelperStore.getState().updateFile(key, { notice: null }));
    expect(screen.getByTestId("helper-file-live").textContent).toBe(before);
  });

  it("the primary writes the hand-over (audit call), fills the slot and opens the page; the token is never in the address", async () => {
    const key = seed({ kind: "card", card: DETECTED });
    show();
    fireEvent.click(screen.getByTestId("helper-file-primary"));
    await waitFor(() => expect(host.go).toHaveBeenCalledWith("/import?kind=weekly-grid&term=12&year=2026&from=helper"));
    const call = fetches.find((f) => f.key === "POST /api/v1/helper/files/handoff");
    expect(call?.body).toEqual({ upload_token: TOKEN, kind: "weekly_grid", feature_id: "import", params: { kind: "weekly-grid", term_id: 12, year: 2026 } });
    expect(String(vi.mocked(host.go).mock.calls[0]![0])).not.toContain(TOKEN);
    const slot = useFileHandoffStore.getState().handoff!;
    expect(slot.items[0]).toMatchObject({ token: TOKEN, sid: "stage42", name: "Bahar_son.xlsx" });
    const entry = useHelperStore.getState().entries.find((e) => e.key === key) as FileEntry;
    expect(entry.phase).toBe("handed");
    expect(entry.stage).toBeNull();
    // the stage now belongs to the page: closing the sheet must not delete it
    expect(fetches.some((f) => f.key.startsWith("DELETE"))).toBe(false);
  });

  it("a script's click is not the person's consent", () => {
    vi.mocked(activation.trusted).mockReturnValue(false);
    seed({ kind: "card", card: DETECTED });
    show();
    fireEvent.click(screen.getByTestId("helper-file-primary"));
    expect(fetches.filter((f) => f.key.includes("/helper/")).map((f) => f.key)).toEqual([]);
    expect(host.go).not.toHaveBeenCalled();
  });

  it("an expired token on the button (410) turns into the expiry line and 'Dosyayı yeniden oku'", async () => {
    answer = (k) => (k.includes("handoff") ? res(410, { detail: { code: "stage_expired", message_tr: "Süre doldu", message_en: "Expired" } }) : res(200, {}));
    seed({ kind: "card", card: DETECTED });
    show();
    fireEvent.click(screen.getByTestId("helper-file-primary"));
    expect(await screen.findByTestId("helper-file-expired")).toHaveTextContent("Dosyanın süresi doldu (10 dakika). Yeniden okuyun.");
    expect(screen.getByTestId("helper-file-reread")).toHaveTextContent("Dosyayı yeniden oku");
    expect(screen.queryByTestId("helper-file-primary")).toBeNull();
    expect(host.go).not.toHaveBeenCalled();
  });

  it("'Başka bir tür seç' lists the kinds this person may import (not the current one) and picks through /route", async () => {
    answer = (k) => (k.includes("/route") ? res(200, { card: { ...DETECTED, kind: "exam_list", title: tr("Bu bir sınav listesi"), primary: { ...DETECTED.primary!, params: { kind: "exam-list", term_id: 12 }, label: tr("Sınav listesi olarak içe aktar") } } }) : res(200, {}));
    seed({ kind: "card", card: DETECTED });
    show();
    fireEvent.click(screen.getByTestId("helper-file-other"));
    const pick = screen.getByTestId("helper-card-file-pick");
    const group = within(pick).getByRole("radiogroup");
    const radios = within(group).getAllByRole("radio");
    expect(radios.map((r) => r.getAttribute("data-testid"))).toEqual([
      "helper-file-choice-planning_list",
      "helper-file-choice-exam_list",
      "helper-file-choice-room_master",
      "helper-file-choice-users_csv",
      "helper-file-choice-crbs_dump",
    ]);
    fireEvent.click(within(group).getByTestId("helper-file-choice-exam_list"));
    expect(await screen.findByText("Bu bir sınav listesi")).toBeInTheDocument();
    expect(fetches.find((f) => f.key === "POST /api/v1/helper/files/route")?.body).toEqual({ upload_token: TOKEN, kind: "exam_list" });
  });
});

describe("needs_planner / unknown", () => {
  it("an academician's route without the file deletes the stage and opens the page (no import button)", async () => {
    PERMS.list = [];
    const card: FileCard = {
      ...DETECTED,
      state: "needs_planner",
      kind: "planning_list",
      title: tr("Bu dosya bir planlama listesi. Bunu planlama ekibi içe aktarır. Sizin için:"),
      warnings: [],
      certainty: "sure",
      primary: { feature_id: "my_classes", params: {}, label: tr("Derslerim'i aç", "Open My classes"), label_short: null, carries_file: false },
      secondary: [],
    };
    seed({ kind: "card", card });
    show();
    expect(screen.getByTestId("helper-card-file-needs_planner")).not.toHaveTextContent(/içe aktar$/);
    expect(screen.queryByTestId("helper-file-other")).toBeNull();
    expect(screen.queryByTestId("helper-file-certainty")).toBeNull();
    fireEvent.click(screen.getByTestId("helper-file-primary"));
    await waitFor(() => expect(host.go).toHaveBeenCalledWith("/my-classes"));
    expect(fetches.map((f) => f.key)).toContain("DELETE /api/v1/helper/files/stage42");
    expect(fetches.some((f) => f.key.includes("handoff"))).toBe(false);
  });

  it("unknown: what was read, 'Hangi dosyaları tanıyorum?' open, 'Örnek dosyaları gör' lists the templates", () => {
    const card: FileCard = {
      ...DETECTED,
      state: "unknown",
      kind: null,
      kind_label: null,
      certainty: null,
      title: null,
      term: null,
      evidence: {},
      warnings: [],
      primary: null,
      explain: {},
      examples: ["planning_list", "exam_list", "room_master", "users_csv"],
    };
    seed({ kind: "card", card }, { stage: null });
    show();
    const box = screen.getByTestId("helper-card-file-unknown");
    expect(box).toHaveTextContent("Bu dosyayı tanıyamadım. XLSX biçiminde, ama tanıdığım sütunlar yok.");
    expect(within(box).getByTestId("helper-file-what")).toHaveAttribute("aria-expanded", "true");
    expect(within(box).getByTestId("helper-file-explain")).toHaveTextContent("Tanıdığım dosyalar: planlama listesi");
    expect(within(box).getAllByTestId("helper-file-primary")).toHaveLength(1);
    fireEvent.click(within(box).getByTestId("helper-file-primary"));
    const link = within(box).getByTestId("helper-file-example-planning_list");
    expect(link).toHaveAttribute("href", "/api/v1/helper/files/examples/planning_list.xlsx");
    expect(link).toHaveAccessibleName("Planlama listesi örneğini indir");
    expect(within(box).getByTestId("helper-file-example-users_csv")).toHaveAttribute("href", "/api/v1/helper/files/examples/users_csv.csv");
    expect(within(box).getByTestId("helper-file-onboarding")).toBeInTheDocument();
  });
});

describe("ambiguous chooser", () => {
  const CHOICE = {
    v: 1 as const,
    id: "c0ffee12",
    type: "choice" as const,
    action: "classify_file",
    arg: "kind",
    args: { upload_token: TOKEN },
    question: tr("Bu dosya hangisi?", "Which one is this file?"),
    options: [
      { value: "planning_list", label: tr("Planlama listesi"), hint: tr("Derslerin gün, saat ve derslik talepleri dönemin planına eklenir") },
      { value: "exam_list", label: tr("Sınav listesi"), hint: tr("Sınav tarihleri ve salon talepleri sınav dönemine eklenir") },
      { value: "onboarding", label: tr("Kurulum sihirbazında aç"), hint: tr("Sihirbaz dosyayı okur ve ne bulduğunu size sorar") },
    ],
  };

  it("is a radiogroup with hints (↑ ↓ move, Enter picks), no primary, the wizard as the secondary", async () => {
    answer = (k, b) => (k.includes("/route") ? res(200, { card: { ...DETECTED, kind: (b as { kind: string }).kind, title: tr("Bu bir sınav listesi") } }) : res(200, {}));
    seed({ kind: "card", card: CHOICE });
    show();
    const card = screen.getByTestId("helper-card-file-ambiguous");
    expect(within(card).queryByTestId("helper-file-primary")).toBeNull();
    const group = within(card).getByRole("radiogroup", { name: "Bu dosya hangisi?" });
    const [first, second] = within(group).getAllByRole("radio");
    expect(within(group).getAllByRole("radio")).toHaveLength(2);
    expect(first).toHaveTextContent("Derslerin gün, saat ve derslik talepleri");
    expect(first).toHaveAttribute("tabindex", "0");
    expect(second).toHaveAttribute("tabindex", "-1");
    first!.focus();
    fireEvent.keyDown(first!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(second);
    fireEvent.keyDown(second!, { key: "Enter" });
    expect(await screen.findByText("Bu bir sınav listesi")).toBeInTheDocument();
    expect(fetches.find((f) => f.key.includes("/route"))?.body).toEqual({ upload_token: TOKEN, kind: "exam_list" });
    await waitFor(() => expect(document.activeElement).toHaveTextContent("Bu bir sınav listesi"));
  });
});

describe("refused / error / several files", () => {
  it("refused: the server's message and 'Başka dosya seç' as the only action", () => {
    seed({ kind: "card", card: { v: 1, id: "deadbeef", type: "refusal", code: "file_type_unsupported", message: tr("Bu tür dosyayı okuyamıyorum (.exe).", "I can't read this type of file (.exe).") } }, { stage: null });
    show();
    const box = screen.getByTestId("helper-card-file-refused");
    expect(box).toHaveTextContent("Bu tür dosyayı okuyamıyorum (.exe).");
    expect(within(box).getAllByRole("button").map((b) => b.textContent)).toEqual(["Başka dosya seç"]);
    expect(box.textContent).not.toMatch(/shake/);
  });

  it("error: 'Tekrar dene' first, 'Başka dosya seç' second", () => {
    seed({ kind: "local", code: "file_read_failed" }, { stage: null });
    show();
    const box = screen.getByTestId("helper-card-file-error");
    expect(within(box).getAllByRole("button").map((b) => b.textContent)).toEqual(["Tekrar dene", "Başka dosya seç"]);
  });

  it("a file over 15 MB is refused with the size and the limit", () => {
    seed({ kind: "local", code: "file_too_large", size: 16 * 1024 * 1024 }, { stage: null });
    show();
    expect(screen.getByTestId("helper-card-file-refused")).toHaveTextContent("Dosya 16 MB; en çok 15 MB okuyabilirim.");
  });

  it("several files (decision 16): one client card, one primary; the File objects go to the setup wizard, no token, no request", async () => {
    const a = new File(["a"], "a.xlsx");
    const b = new File(["bb"], "b.ics");
    const key = useHelperStore.getState().pushFile([{ name: a.name, size: a.size }, { name: b.name, size: b.size }]);
    useHelperStore.getState().updateFile(key, { phase: "shown", view: { kind: "many", n: 2 }, seq: 1 });
    const { attachFilesForTest } = await import("./file-router");
    attachFilesForTest(key, [a, b]);
    show();
    const card = screen.getByTestId("helper-card-file-many");
    expect(card).toHaveTextContent("2 dosya bıraktınız. Birden çok dosyayı Kurulum sihirbazı birlikte okur.");
    // KVKK Art. 10: these files are never read or staged by the server
    expect(card).toHaveTextContent("Dosyalar bu cihazda kalır; Kurulum sihirbazında Başlat'a basana kadar hiçbir yere gönderilmez.");
    expect(card).not.toHaveTextContent("10 dakika şifreli");
    expect(within(card).getAllByRole("button")).toHaveLength(1);
    expect(screen.getAllByTestId("helper-file-chip")).toHaveLength(2);
    fireEvent.click(within(card).getByTestId("helper-file-primary"));
    await waitFor(() => expect(host.go).toHaveBeenCalledWith("/onboarding?from=helper"));
    expect(fetches.filter((f) => f.key.includes("/helper/")).map((f) => f.key)).toEqual([]);
    const slot = useFileHandoffStore.getState().handoff!;
    expect(slot.featureId).toBe("onboarding");
    expect(slot.items.map((i) => [i.name, i.token])).toEqual([
      ["a.xlsx", null],
      ["b.ics", null],
    ]);
  });

  it("HELPER_FILE_STAGE=off (resend): the primary hands over the browser's File without a token or an audit call", async () => {
    const f = new File(["x"], "Bahar_son.xlsx");
    const key = seed({ kind: "card", card: DETECTED }, { stage: null, resend: true });
    const { attachFilesForTest } = await import("./file-router");
    attachFilesForTest(key, [f]);
    show();
    fireEvent.click(screen.getByTestId("helper-file-primary"));
    await waitFor(() => expect(host.go).toHaveBeenCalledWith("/import?kind=weekly-grid&term=12&year=2026&from=helper"));
    expect(fetches.filter((f) => f.key.includes("/helper/")).map((f) => f.key)).toEqual([]);
    expect(useFileHandoffStore.getState().handoff?.items[0]).toMatchObject({ token: null, name: "Bahar_son.xlsx" });
  });

  it("a newer file collapses the older live card to one line", () => {
    seed({ kind: "card", card: DETECTED });
    useHelperStore.getState().pushFile([{ name: "ikinci.csv", size: 10 }]);
    show();
    expect(screen.getByTestId("helper-file-collapsed")).toHaveTextContent("Haftalık derslik takvimi · kapandı");
    expect(screen.queryByTestId("helper-card-file-detected")).toBeNull();
  });
});

describe("what happens to the file (KVKK N3 / N4)", () => {
  const READ = "Dosya yalnızca türünü anlamak için okunur ve en çok 10 dakika şifreli tutulur";
  const NOT_KEPT = "Dosya yalnızca türünü anlamak için okundu; tutulmadı.";

  it("a staged file says it is kept encrypted for 10 minutes", () => {
    seed({ kind: "card", card: DETECTED });
    show();
    expect(screen.getByTestId("helper-file-privacy")).toHaveTextContent(READ);
  });

  it("without a stage (needs_planner, HELPER_FILE_STAGE=off) it says the file was only read and not kept", () => {
    seed({ kind: "card", card: { ...DETECTED, state: "needs_planner", primary: { feature_id: "my_classes", params: {}, label: tr("Derslerim'i aç"), carries_file: false } } }, { stage: null });
    show();
    expect(screen.getByTestId("helper-file-privacy")).toHaveTextContent(NOT_KEPT);
  });

  it("the chooser says it too", () => {
    const choice = {
      v: 1 as const,
      id: "c0ffee13",
      type: "choice" as const,
      action: "classify_file",
      arg: "kind",
      args: { upload_token: TOKEN },
      question: tr("Bu dosya hangisi?"),
      options: [
        { value: "planning_list", label: tr("Planlama listesi"), hint: tr("Ders talepleri") },
        { value: "exam_list", label: tr("Sınav listesi"), hint: tr("Sınav talepleri") },
      ],
    };
    seed({ kind: "card", card: choice });
    show();
    expect(within(screen.getByTestId("helper-card-file-ambiguous")).getByTestId("helper-file-privacy")).toHaveTextContent(READ);
  });
});
