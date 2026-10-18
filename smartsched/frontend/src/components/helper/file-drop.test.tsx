/**
 * HB-23c (helper-file-router.md §8, §10, §11.2 "file-drop.test.tsx"): the sheet's 📎 (AI mode and Rehber modu),
 * an OS file drag over the log (a text drag does nothing), drop → classify once, a pasted file, the 15 MB pre-check (no
 * request), the stage deleted on close; and the page's edge target (shown for an OS file drag on a signed-in desktop
 * page, not over a local zone, not on /setup or ?embed=1; a drop opens the sheet and classifies).
 */
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { helperApi, type HelperStatus } from "@/lib/api/helper";
import { HelperSheet } from "./helper-sheet";
import { useHelperStore } from "./helper-store";
import { PageFileTarget } from "./page-file-target";
import { useUiStore } from "@/stores/ui";
import { renderHelper, resetHelperStore } from "./test-helpers";

const nav = vi.hoisted(() => ({ pathname: "/dashboard", search: "" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => nav.pathname, useSearchParams: () => new URLSearchParams(nav.search) }));
vi.mock("@/lib/api/shell-extra", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/shell-extra")>()),
  usePermissions: () => ({ can: () => true, perms: [] }),
  useMeFull: () => ({ data: { id: 1, permissions: [] }, isLoading: false }),
}));
vi.mock("@/lib/api/ai-admin", async (orig) => ({ ...(await orig<typeof import("@/lib/api/ai-admin")>()), useMyAiUsage: () => ({ data: undefined }) }));
const fine = vi.hoisted(() => ({ value: true }));
vi.mock("@/lib/motion", async (orig) => ({ ...(await orig<typeof import("@/lib/motion")>()), useFinePointer: () => fine.value }));

function media(desktop: boolean) {
  window.matchMedia = ((q: string) => ({
    matches: q.includes("min-width: 1024px") ? desktop : false,
    media: q,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

const status = (over: Partial<HelperStatus> = {}): HelperStatus => ({ mode: "ai", enabled: true, reason: null, provider_kind: "local", provider_label: null, fallback_active: false, message: null, ...over });
const TOKEN = `${btoa(JSON.stringify({ k: "file", s: "stage77" })).replace(/=+$/, "")}.c2lnbmF0dXJlLXNpZ25hdHVyZQ`;
const CARD = {
  v: 1,
  id: "a1b2c3d4e5f6",
  type: "file",
  action: "classify_file",
  title: { tr: "Bu bir planlama listesi", en: "This is a planning list" },
  state: "detected",
  kind: "planning_list",
  certainty: "sure",
  format: "xlsx",
  evidence: { tr: ["Sütunlar: Ders Kodu, Şube, Dersin Günü → Planlama listesi"], en: ["Columns: Ders Kodu, Şube, Dersin Günü → Planning list"] },
  term: null,
  warnings: [],
  primary: { feature_id: "import", params: { kind: "planning-list" }, label: { tr: "Planlama listesi olarak içe aktar", en: "Import as planning list" }, carries_file: true },
  secondary: [],
  explain: {},
  examples: [],
  ai_sorted: false,
};

const res = (s: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status: s, headers: { "content-type": "application/json" } });
let calls: { key: string; body: BodyInit | null | undefined }[];

beforeEach(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
  resetHelperStore();
  useUiStore.setState({ termId: 11 });
  media(true);
  fine.value = true;
  nav.pathname = "/dashboard";
  nav.search = "";
  vi.restoreAllMocks();
  vi.spyOn(helperApi, "status").mockResolvedValue(status());
  vi.spyOn(helperApi, "actions").mockResolvedValue([]);
  vi.spyOn(helperApi, "memory").mockResolvedValue({ institution_enabled: true, enabled: false, notes: 0, max_notes: 20, max_chars: 200, retention_days: 180, history_days: 30 });
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${String(url).split("?")[0]}`;
      calls.push({ key, body: init?.body });
      if (key === "POST /api/v1/helper/files/classify") return res(200, { card: CARD, stage: { upload_token: TOKEN, expires_at: new Date(Date.now() + 600_000).toISOString(), size: 10, format: "xlsx" } });
      if (key.startsWith("DELETE")) return res(204);
      return res(200, []);
    }),
  );
});

const classifyCalls = () => calls.filter((c) => c.key === "POST /api/v1/helper/files/classify");
const openSheet = async () => {
  act(() => useHelperStore.getState().openSheet());
  renderHelper(<HelperSheet />);
  await screen.findByTestId("helper-sheet");
};
const xlsx = (bytes = 10, name = "Bahar_son.xlsx") => new File([new Uint8Array(bytes)], name, { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

describe("the sheet's ways in", () => {
  it("📎 'Dosya ekle' sits in the composer (44 px) and opens the picker; the input has a label", async () => {
    await openSheet();
    const composer = await screen.findByTestId("helper-composer");
    const attach = within(composer).getByTestId("helper-attach");
    expect(attach).toHaveAccessibleName("Dosya ekle");
    expect(attach.className).toContain("size-11");
    const input = within(composer).getByTestId("helper-file-input") as HTMLInputElement;
    expect(input).toHaveAccessibleName("Dosya ekle");
    expect(input.accept).toContain(".sql");
    const click = vi.spyOn(input, "click").mockImplementation(() => undefined);
    fireEvent.click(attach);
    expect(click).toHaveBeenCalledTimes(1);
  });

  it("Rehber modu (AI off) has the 📎 too, with its words", async () => {
    vi.mocked(helperApi.status).mockResolvedValue(status({ mode: "index", reason: "index_mode" }));
    await openSheet();
    await screen.findByTestId("helper-guide");
    expect(await screen.findByTestId("helper-attach")).toHaveTextContent("Dosya ekle");
  });

  it("admins see 'Elimde bir dosya var, ne yapayım?' as the first starter", async () => {
    await openSheet();
    const starters = await screen.findByTestId("helper-starters");
    expect(starters.querySelector("li")).toHaveTextContent("Elimde bir dosya var, ne yapayım?");
  });

  it("an OS file drag over the log shows the drop target at once; a text drag does not", async () => {
    await openSheet();
    const log = screen.getByTestId("helper-log");
    fireEvent.dragEnter(log, { dataTransfer: { types: ["text/plain"], files: [] } });
    expect(screen.queryByTestId("helper-file-drop")).toBeNull();
    fireEvent.dragEnter(log, { dataTransfer: { types: ["Files"], files: [] } });
    const target = screen.getByTestId("helper-file-drop");
    expect(target).toHaveTextContent("Dosyayı buraya bırakın. Ne olduğunu ve ne yapacağınızı söyleyeyim.");
    expect(target).toHaveTextContent("en çok 15 MB");
    expect(target).toHaveTextContent("Siz onaylayana kadar hiçbir şey kaydedilmez.");
    fireEvent.dragLeave(log, { dataTransfer: { types: ["Files"], files: [] } });
    expect(screen.queryByTestId("helper-file-drop")).toBeNull();
  });

  it("a drop classifies the file once and the card arrives with the focus on its title", async () => {
    await openSheet();
    const log = screen.getByTestId("helper-log");
    fireEvent.dragEnter(log, { dataTransfer: { types: ["Files"], files: [] } });
    fireEvent.drop(log, { dataTransfer: { types: ["Files"], files: [xlsx()] } });
    expect(screen.queryByTestId("helper-file-drop")).toBeNull();
    expect(await screen.findByTestId("helper-card-file-detected")).toBeInTheDocument();
    expect(classifyCalls()).toHaveLength(1);
    const fd = classifyCalls()[0]!.body as FormData;
    expect((fd.get("file") as File).name).toBe("Bahar_son.xlsx");
    expect(fd.get("lang")).toBe("tr");
    // the term switcher's choice goes along, so the card can say "the file says Bahar; Güz is selected"
    expect(fd.get("term_id")).toBe("11");
    await waitFor(() => expect(document.activeElement).toHaveTextContent("Bu bir planlama listesi"));
    // nothing went to the model's turn
    expect(calls.some((c) => c.key.includes("/helper/turn"))).toBe(false);
  });

  it("several files from a planner make one setup-wizard card and no classify call (decision 16)", async () => {
    await openSheet();
    fireEvent.change(screen.getByTestId("helper-file-input"), { target: { files: [xlsx(10, "a.xlsx"), xlsx(20, "b.xlsx")] } });
    expect(await screen.findByTestId("helper-card-file-many")).toHaveTextContent("2 dosya bıraktınız.");
    expect(classifyCalls()).toHaveLength(0);
  });

  it("a pasted file in the composer is attached; a text paste is left alone", async () => {
    await openSheet();
    const composer = await screen.findByTestId("helper-composer");
    const field = composer.querySelector("textarea")!;
    fireEvent.paste(field, { clipboardData: { files: [], types: ["text/plain"], getData: () => "merhaba" } });
    expect(classifyCalls()).toHaveLength(0);
    fireEvent.paste(field, { clipboardData: { files: [xlsx()], types: ["Files"], getData: () => "" } });
    expect(await screen.findByTestId("helper-card-file-detected")).toBeInTheDocument();
    expect(classifyCalls()).toHaveLength(1);
  });

  it("a file over 15 MB makes no request and is refused with the limit", async () => {
    await openSheet();
    const input = screen.getByTestId("helper-file-input");
    fireEvent.change(input, { target: { files: [xlsx(15 * 1024 * 1024 + 1)] } });
    expect(await screen.findByTestId("helper-card-file-refused")).toHaveTextContent("en çok 15 MB");
    expect(classifyCalls()).toHaveLength(0);
  });

  it("closing the sheet with a live card deletes its stage; the card then offers 'Dosyayı yeniden oku'", async () => {
    await openSheet();
    fireEvent.change(screen.getByTestId("helper-file-input"), { target: { files: [xlsx()] } });
    await screen.findByTestId("helper-card-file-detected");
    fireEvent.keyDown(screen.getByTestId("helper-sheet"), { key: "Escape" });
    await waitFor(() => expect(calls.map((c) => c.key)).toContain("DELETE /api/v1/helper/files/stage77"));
    const entry = useHelperStore.getState().entries.find((e) => e.kind === "file");
    expect(entry && entry.kind === "file" && entry.expired).toBe(true);
  });

  it("'Vazgeç' while reading cancels without a card", async () => {
    let release: (r: Response) => void = () => undefined;
    const real = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation((url, init) =>
      String(url).includes("/helper/files/classify") ? new Promise<Response>((r) => (release = r)) : real(url as string, init),
    );
    await openSheet();
    fireEvent.change(screen.getByTestId("helper-file-input"), { target: { files: [xlsx()] } });
    fireEvent.click(await screen.findByTestId("helper-file-cancel"));
    expect(screen.getByTestId("helper-file-cancelled")).toHaveTextContent("Dosya okunmadı.");
    vi.mocked(fetch).mockImplementation(real);
    release(res(200, { card: CARD, stage: { upload_token: TOKEN, expires_at: new Date(Date.now() + 600_000).toISOString() } }));
    await waitFor(() => expect(calls.map((c) => c.key)).toContain("DELETE /api/v1/helper/files/stage77"));
    expect(screen.queryByTestId("helper-card-file-detected")).toBeNull();
  });
});

describe("the page's edge target", () => {
  const drag = (type: "dragEnter" | "dragOver" | "drop", target: EventTarget, files: File[] = [], types = ["Files"]) => fireEvent[type](target as Element, { dataTransfer: { types, files, dropEffect: "none" } });

  it("shows for an OS file drag on a signed-in desktop page and clears on Esc", async () => {
    renderHelper(<PageFileTarget />);
    await waitFor(() => expect(helperApi.status).toHaveBeenCalled());
    await act(async () => undefined);
    act(() => void drag("dragEnter", document.body));
    act(() => void drag("dragOver", document.body));
    const target = screen.getByTestId("page-file-target");
    expect(target).toHaveTextContent("Yardımcıya bırakın: ne olduğunu söyleyeyim");
    expect(target.querySelector("button,[tabindex]")).toBeNull();
    act(() => void fireEvent.keyDown(window, { key: "Escape" }));
    expect(screen.queryByTestId("page-file-target")).toBeNull();
    act(() => void drag("dragEnter", document.body, [], ["text/plain"]));
    expect(screen.queryByTestId("page-file-target")).toBeNull();
  });

  it("steps aside over a local drop zone", async () => {
    const zone = document.createElement("div");
    zone.setAttribute("data-testid", "import-dropzone");
    document.body.appendChild(zone);
    renderHelper(<PageFileTarget />);
    await act(async () => undefined);
    act(() => void drag("dragEnter", zone));
    act(() => void drag("dragOver", zone));
    expect(screen.queryByTestId("page-file-target")).toBeNull();
    zone.remove();
  });

  it.each([
    ["/setup", ""],
    ["/dashboard", "embed=1"],
    ["/dashboard", "kiosk=1"],
  ])("is not shown on %s?%s", async (path, search) => {
    nav.pathname = path;
    nav.search = search;
    renderHelper(<PageFileTarget />);
    await act(async () => undefined);
    act(() => void drag("dragEnter", document.body));
    act(() => void drag("dragOver", document.body));
    expect(screen.queryByTestId("page-file-target")).toBeNull();
  });

  it("is not shown on touch (coarse pointer)", async () => {
    fine.value = false;
    renderHelper(<PageFileTarget />);
    await act(async () => undefined);
    act(() => void drag("dragEnter", document.body));
    expect(screen.queryByTestId("page-file-target")).toBeNull();
  });

  it("a drop opens the helper sheet and classifies the file", async () => {
    renderHelper(<PageFileTarget />);
    await act(async () => undefined);
    act(() => void drag("dragEnter", document.body));
    act(() => void drag("drop", document.body, [xlsx()]));
    expect(screen.queryByTestId("page-file-target")).toBeNull();
    expect(useHelperStore.getState().open).toBe(true);
    await waitFor(() => expect(classifyCalls()).toHaveLength(1));
    await waitFor(() => expect(useHelperStore.getState().entries.some((e) => e.kind === "file" && e.phase === "shown")).toBe(true));
  });
});
