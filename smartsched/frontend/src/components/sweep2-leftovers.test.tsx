/**
 * Sweeper 2 (sweep2-2026-10-18): unowned leftovers.
 * - W3-AI M-05: /admin/ai Limitler and Modeller "Kaydet" in the phone page-actions capsule.
 * - Mobile B fix 12: /programs/new primary (wizard-start, or "continue the latest draft") and /settings?tab=ai "Kaydet"
 *   in the capsule.
 * - Mobile B fix 15: the slow taps. Studio step 1 → 2 mounted the desktop table first on phones and then swapped it for
 *   the cards (useIsNarrow started false); "Şablondan seç" re-rendered every rule card of the step (the open state
 *   lived in RulesStep).
 * - Audit A5: the data-table virtualiser sizes rows by the density in effect (the table's own choice, else the app's
 *   Görünüm › Yoğunluk), and the table sets its own --row-h instead of inheriting the app's.
 * jsdom has no layout: placement is a source contract (as in mobile-b-phase2.test.tsx); behaviour is rendered.
 */
import { act, render, renderHook, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { useUiStore } from "@/stores/ui";
import { DataTable, type DataColumn } from "./ui/data-table/data-table";
import { ROW_H, tableDensity } from "./ui/data-table/use-column-layout";
import { NARROW_QUERY, useIsNarrow } from "./studio/classes-step";

const ROOT = join(process.cwd(), "src");
const read = (rel: string) => readFileSync(join(ROOT, rel), "utf8");
const CAPSULE = 'data-slot="page-actions" className={';
/** the testid's element opens within `span` characters after a page-actions capsule opened */
const inCapsule = (rel: string, testid: string, span = 500) => {
  const src = read(rel);
  const at = src.indexOf(`data-testid="${testid}"`);
  expect(at, `${testid} in ${rel}`).toBeGreaterThan(0);
  return src.slice(Math.max(0, at - span), at).includes(CAPSULE);
};

describe("W3-AI M-05 · /admin/ai Save buttons sit in the phone capsule", () => {
  it("Modeller 'Kaydet'", () => expect(inCapsule("components/admin/ai/models-tab.tsx", "ai-routes-save")).toBe(true));
  it("Limitler 'Kaydet'", () => expect(inCapsule("components/admin/ai/limits-tab.tsx", "ai-limits-save")).toBe(true));
  it("the hint about fixing routes first stays in the form, not in the floating capsule", () => {
    const src = read("components/admin/ai/models-tab.tsx");
    const capsule = src.indexOf(CAPSULE);
    expect(src.indexOf('t("aiAdmin.models.fixFirst")')).toBeLessThan(capsule);
  });
});

describe("mobile B fix 12 · /programs/new and /settings?tab=ai primaries in the capsule", () => {
  const wiz = "components/program-wizard/program-wizard.tsx";
  it("without drafts, 'Program oluştur' (wizard-start) is the capsule's action", () => {
    const src = read(wiz);
    expect(src).toMatch(/const startButton = <Button [^\n]*data-testid="wizard-start"/);
    expect(src).toContain('{latest ? startButton : <div data-slot="page-actions" className={pageActionsCapsule}>{startButton}</div>}');
  });
  it("with drafts, a phone-only capsule continues the newest draft (the list is newest first)", () => {
    const src = read(wiz);
    expect(src).toContain("const latest = drafts.data?.items[0]");
    const at = src.indexOf('data-testid="draft-resume"');
    expect(at).toBeGreaterThan(0);
    expect(src.slice(at - 600, at)).toMatch(/data-slot="page-actions" className=\{cn\(pageActionsCapsule, "lg:hidden"\)\}/);
    expect(src.slice(at - 600, at + 200)).toContain("draftHref(latest)");
  });
  it("the row buttons and the capsule open the same address", () => {
    const src = read(wiz);
    expect(src).toContain("export function draftHref(");
    expect(src).toMatch(/render=\{<Link href=\{draftHref\(d\)\} \/>\}[^\n]*data-testid="draft-open"/);
  });
  it("/settings?tab=ai: the key 'Kaydet' and the model 'Kaydet' each go to the capsule while they are the task", () => {
    const view = "components/settings/settings-view.tsx";
    expect(inCapsule(view, "save-key", 300)).toBe(true);
    expect(read(view)).toMatch(/typing \? saveModel : <div data-slot="page-actions" className=\{cn\(pageActionsCapsule, "mt-3"\)\}>\{saveModel\}<\/div>/);
  });
  it("Turkish first: the resume label exists in both languages", () => {
    const tr = JSON.parse(read("../messages/tr.json")).programWizard.landing;
    const en = JSON.parse(read("../messages/en.json")).programWizard.landing;
    expect(tr.resumeLatest).toBe("Son taslağa devam et");
    expect(en.resumeLatest).toBe("Continue the latest draft");
    expect(tr.resumeLatestLabel).toContain("{name}");
    expect(en.resumeLatestLabel).toContain("{name}");
  });
});

describe("mobile B fix 15 · Studio step 1 → 2 mounts only the phone cards on a phone", () => {
  const orig = window.matchMedia;
  afterEach(() => {
    window.matchMedia = orig;
  });
  const stub = (matches: boolean) => {
    window.matchMedia = ((query: string) => ({ matches: query === NARROW_QUERY ? matches : false, media: query, onchange: null, addEventListener: () => undefined, removeEventListener: () => undefined, addListener: () => undefined, removeListener: () => undefined, dispatchEvent: () => false })) as typeof window.matchMedia;
  };
  it("the first render already knows the width (was: false, then a second render with the cards)", () => {
    stub(true);
    const seen: boolean[] = [];
    renderHook(() => {
      const n = useIsNarrow();
      seen.push(n);
      return n;
    });
    expect(seen[0]).toBe(true);
    expect(new Set(seen)).toEqual(new Set([true]));
  });
  it("desktop stays the table", () => {
    stub(false);
    const { result } = renderHook(() => useIsNarrow());
    expect(result.current).toBe(false);
  });
});

describe("mobile B fix 15 · 'Şablondan seç' re-renders only its own launcher", () => {
  it("RulesStep holds no gallery open state; the launcher owns it and renders the trigger", () => {
    const src = read("components/studio/rules-step.tsx");
    expect(src).not.toContain("const [gallery, setGallery] = useState(false)");
    expect(src).toContain("<TemplateGalleryLauncher");
    const gal = read("components/studio/template-gallery.tsx");
    expect(gal).toContain("export function TemplateGalleryLauncher(");
    const launcher = gal.slice(gal.indexOf("export function TemplateGalleryLauncher("));
    expect(launcher).toContain("useState(false)");
    expect(launcher).toContain('data-testid="add-template"');
  });
});

describe("audit A5 · the virtualiser follows the density in effect", () => {
  it("the table's own choice wins; otherwise the app's density (Sıkı → compact, Rahat → standard)", () => {
    expect(tableDensity(undefined, "compact")).toBe("compact");
    expect(tableDensity(undefined, "comfortable")).toBe("standard");
    expect(tableDensity("comfortable", "compact")).toBe("comfortable");
    expect(tableDensity("compact", "comfortable")).toBe("compact");
    expect(ROW_H).toEqual({ compact: 32, standard: 44, comfortable: 56 });
  });
  it("globals.css gives the standard density its own --row-h, so a table never inherits the app's 32 / 56", () => {
    expect(read("app/globals.css")).toMatch(/\[data-density="standard"\] \{ --row-h: 44px; --cell-py: 8px; --cell-px: 12px; \}/);
  });

  type R = { id: number; name: string };
  const cols: DataColumn<R>[] = [{ id: "name", header: "Ad", cell: (r) => r.name }];
  const rows: R[] = Array.from({ length: 120 }, (_, i) => ({ id: i, name: `Satır ${i}` }));
  const offsets = () =>
    [...document.querySelectorAll<HTMLElement>('[role="rowgroup"] [role="row"][aria-rowindex]')]
      .map((el) => /translateY\((\d+)px\)/.exec(el.style.transform)?.[1])
      .filter((x): x is string => x !== undefined)
      .map(Number);
  // jsdom has no layout: give the scroller a size so the virtualiser renders its first rows
  const SIZES = [["offsetHeight", 400], ["offsetWidth", 800], ["clientHeight", 400], ["clientWidth", 800]] as const;
  const saved = new Map<string, PropertyDescriptor | undefined>();
  const sized = (on: boolean) => {
    for (const [prop, px] of SIZES) {
      const owner = prop.startsWith("offset") ? HTMLElement.prototype : Element.prototype;
      if (on) {
        saved.set(prop, Object.getOwnPropertyDescriptor(owner, prop));
        Object.defineProperty(owner, prop, { configurable: true, get: () => px });
      } else {
        const d = saved.get(prop);
        if (d) Object.defineProperty(owner, prop, d);
      }
    }
  };
  beforeEach(() => sized(true));
  afterEach(() => sized(false));
  const renderTable = () =>
    render(
      <I18nProvider initialLocale="tr">
        <DataTable tableId="sweep2-a5" label="Satırlar" columns={cols} rows={rows} getRowId={(r) => String(r.id)} />
      </I18nProvider>,
    );

  it("Sıkı görünüm: the table is compact and the virtual rows step by 32 px (was 44)", () => {
    act(() => useUiStore.getState().setDensity("compact"));
    renderTable();
    expect(screen.getByRole("table")).toHaveAttribute("data-density", "compact");
    const ys = offsets();
    expect(ys.length).toBeGreaterThan(1);
    expect(ys[1] - ys[0]).toBe(32);
  });
  it("Rahat (the default): standard rows of 44 px", () => {
    act(() => useUiStore.getState().setDensity("comfortable"));
    renderTable();
    expect(screen.getByRole("table")).toHaveAttribute("data-density", "standard");
    const ys = offsets();
    expect(ys[1] - ys[0]).toBe(44);
  });
});
