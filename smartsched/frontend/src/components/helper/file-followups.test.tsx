/**
 * HB-23c follow-ups (helper-file-router.md §8.3, §8.4, §8.2, §9): the palette's "dosya" / "file" Kısayollar row opens
 * the sheet with the picker; the empty-state link does the same; on phones a column-evidence line shows ≤ 3 labels then
 * "+n" (the full line stays for wider screens and readers); a chooser pick carries its tint into the new card header.
 */
import { act, fireEvent, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Command, CommandList } from "@/components/ui/command";
import { helperApi, type HelperStatus } from "@/lib/api/helper";
import type { FileCard } from "@/lib/api/helper-files";
import { EntryView } from "./cards/render";
import { splitEvidence } from "./cards/file";
import { HelperFileLink } from "./file-link";
import { useHelperStore } from "./helper-store";
import { HelperPaletteBottom } from "./palette-groups";
import { makeHost, renderHelper, resetHelperStore } from "./test-helpers";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/dashboard", useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/api/shell-extra", async (orig) => ({ ...(await orig<typeof import("@/lib/api/shell-extra")>()), usePermissions: () => ({ can: () => true, perms: ["planning.edit"] }) }));
vi.mock("@/lib/api/ai-admin", async (orig) => ({ ...(await orig<typeof import("@/lib/api/ai-admin")>()), useMyAiUsage: () => ({ data: undefined }) }));

const status = (over: Partial<HelperStatus> = {}): HelperStatus => ({ mode: "ai", enabled: true, reason: null, provider_kind: "local", provider_label: null, fallback_active: false, message: null, ...over });

beforeEach(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
  resetHelperStore();
  vi.restoreAllMocks();
  vi.spyOn(helperApi, "status").mockResolvedValue(status());
  vi.spyOn(helperApi, "actions").mockResolvedValue([]);
  vi.spyOn(helperApi, "search").mockResolvedValue({ q: "dosya", question: false, pages: [], where: [], data: {}, skipped: [], timing_ms: 1 } as never);
});

describe("palette 'dosya' row", () => {
  it.each(["dosya", "Dosya ekle", "file", "bu dosya ne"])("'%s' offers 'Dosya ekle ve ne olduğunu öğren' and opens the sheet with the picker", async (q) => {
    renderHelper(
      <Command shouldFilter={false} label="palette">
        <CommandList>
          <HelperPaletteBottom query={q} />
        </CommandList>
      </Command>,
    );
    const row = await screen.findByTestId("palette-shortcut-attach_file");
    expect(row).toHaveTextContent("Dosya ekle ve ne olduğunu öğren");
    vi.useFakeTimers({ toFake: ["requestAnimationFrame"] });
    fireEvent.click(row);
    act(() => vi.advanceTimersByTime(50));
    vi.useRealTimers();
    expect(useHelperStore.getState().open).toBe(true);
    expect(useHelperStore.getState().pendingPick).toBe(true);
  });

  it("an unrelated query has no file row", async () => {
    renderHelper(
      <Command shouldFilter={false} label="palette">
        <CommandList>
          <HelperPaletteBottom query="tatil" />
        </CommandList>
      </Command>,
    );
    await act(async () => undefined);
    expect(screen.queryByTestId("palette-shortcut-attach_file")).toBeNull();
  });
});

describe("empty-state link", () => {
  it("is one link-styled button that opens the picker, and the picked file goes to the helper", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify([]), { status: 200, headers: { "content-type": "application/json" } })));
    renderHelper(<HelperFileLink />);
    const link = screen.getByTestId("helper-file-link");
    expect(link).toHaveTextContent("Elinizde bir dosya mı var? Bırakın, ne olduğunu söyleyelim");
    const input = screen.getByTestId("helper-file-link-input") as HTMLInputElement;
    const click = vi.spyOn(input, "click").mockImplementation(() => undefined);
    fireEvent.click(link);
    expect(click).toHaveBeenCalledTimes(1);
    fireEvent.change(input, { target: { files: [new File(["x"], "a.xlsx")] } });
    expect(useHelperStore.getState().open).toBe(true);
    expect(useHelperStore.getState().entries.some((e) => e.kind === "file")).toBe(true);
    vi.unstubAllGlobals();
  });
});

describe("phone evidence: ≤ 3 labels then +n", () => {
  it("splits a column line and counts a server '+n' too", () => {
    expect(splitEvidence("Sütunlar: Ders Kodu, Şube, Dersin Günü, Başlangıç, Bitiş, 1. Öğretim Elemanı → Planlama listesi")).toBe("Sütunlar: Ders Kodu, Şube, Dersin Günü +3 → Planlama listesi");
    expect(splitEvidence("Columns: a, b, c, d, e, f, +4 → Planning list")).toBe("Columns: a, b, c +7 → Planning list");
    expect(splitEvidence("Sütunlar: Ders Kodu, Şube → Sınav listesi")).toBeNull();
    expect(splitEvidence("19 sayfa, her biri bir hafta")).toBeNull();
  });

  it("renders the short line under 640 px and the full one above (and for readers)", () => {
    const card: FileCard = {
      v: 1,
      id: "a1b2c3d4e5f6",
      type: "file",
      action: "classify_file",
      title: { tr: "Bu bir planlama listesi", en: "This is a planning list" },
      state: "detected",
      kind: "planning_list",
      certainty: "sure",
      format: "xlsx",
      evidence: { tr: ["Sütunlar: Ders Kodu, Şube, Dersin Günü, Başlangıç, Bitiş → Planlama listesi"] },
      warnings: [],
      secondary: [],
      explain: {},
      examples: [],
      ai_sorted: false,
    };
    const key = useHelperStore.getState().pushFile([{ name: "a.xlsx", size: 1 }]);
    useHelperStore.getState().updateFile(key, { phase: "shown", view: { kind: "card", card }, seq: 1 });
    const entry = useHelperStore.getState().entries[0]!;
    renderHelper(<EntryView entry={entry} />, { host: makeHost() });
    const line = screen.getByTestId("helper-file-evidence");
    const short = within(line).getByText("Sütunlar: Ders Kodu, Şube, Dersin Günü +2 → Planlama listesi");
    expect(short.className).toContain("sm:hidden");
    expect(short).toHaveAttribute("aria-hidden", "true");
    expect(within(line).getByText("Sütunlar: Ders Kodu, Şube, Dersin Günü, Başlangıç, Bitiş → Planlama listesi").className).toContain("max-sm:sr-only");
  });
});

describe("chooser pick tint", () => {
  it("the picked row gets the shared tint and the next card's header takes it over", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Promise<Response>(() => undefined)));
    const tok = `${btoa(JSON.stringify({ k: "file", s: "stage9" })).replace(/=+$/, "")}.c2lnbmF0dXJlLXNpZ25hdHVyZQ`;
    const key = useHelperStore.getState().pushFile([{ name: "a.xlsx", size: 1 }]);
    const choice = {
      v: 1 as const,
      id: "c0ffee12",
      type: "choice" as const,
      action: "classify_file",
      arg: "kind",
      question: { tr: "Bu dosya hangisi?", en: "Which one is this file?" },
      options: [
        { value: "planning_list", label: { tr: "Planlama listesi", en: "Planning list" } },
        { value: "exam_list", label: { tr: "Sınav listesi", en: "Exam list" } },
      ],
    };
    useHelperStore.getState().updateFile(key, { phase: "shown", view: { kind: "card", card: choice }, stage: { upload_token: tok, expires_at: new Date(Date.now() + 60_000).toISOString() }, seq: 1 });
    const Live = () => {
      const e = useHelperStore((s) => s.entries[0]!);
      return <EntryView entry={e} />;
    };
    renderHelper(<Live />, { host: makeHost() });
    fireEvent.click(screen.getByTestId("helper-file-choice-exam_list"));
    expect(screen.getByTestId("helper-file-choice-exam_list").querySelector("[data-pick-tint]")).not.toBeNull();
    expect(useHelperStore.getState().entries[0]).toMatchObject({ picked: "exam_list" });
    vi.unstubAllGlobals();
  });
});
