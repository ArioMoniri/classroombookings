/** HX-18 (docs/testing/audits/2026-10-18-helper-design-audit.md): the audit's static minors (m2, m8, m9, m13). */
import { screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";
import en from "../../../messages/en.json";
import tr from "../../../messages/tr.json";
import { StatusChip, type HelperMode } from "./status-chip";
import { renderHelper } from "./test-helpers";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/api/shell-extra", async (orig) => ({ ...(await orig<typeof import("@/lib/api/shell-extra")>()), usePermissions: () => ({ can: () => false, perms: [] }) }));

type Tree = { [k: string]: string | Tree };
const get = (o: Tree, path: string): string | Tree | undefined => path.split(".").reduce<string | Tree | undefined>((a, k) => (a && typeof a === "object" ? a[k] : undefined), o);

describe("HX-18 static minors", () => {
  it("m2: 'Düşünüyor…' stays visible in forced-colours mode", () => {
    const css = readFileSync(resolve(__dirname, "helper.css"), "utf8");
    const block = css.slice(css.indexOf("@media (forced-colors: active)"));
    expect(block).toMatch(/\.helper-shimmer\s*\{[^}]*-webkit-text-fill-color:\s*CanvasText/);
  });

  it("m8: the unused helper strings are gone (both languages)", () => {
    for (const msgs of [tr, en] as unknown as Tree[]) {
      for (const k of ["helper.where.stepLabel", "helper.palette.showKeys", "helper.notAllowed", "helper.memory.delete"]) expect(get(msgs, k)).toBeUndefined();
      // wired now (M7) or kept for HX-17
      expect(get(msgs, "helper.memory.deleteAll")).toBeTruthy();
      expect(get(msgs, "helper.memory.ask")).toBeTruthy();
    }
  });

  it("m9: no internal 'dizin' word, one punctuation for the limit line, a clear room-day label", () => {
    const t = tr as unknown as Tree;
    const e = en as unknown as Tree;
    expect(get(t, "helper.card.fromIndex")).toBe("Site rehberinden");
    expect(get(t, "helper.status.fallbackBody")).toBe("Asıl model şu an yanıt vermiyor; bu yanıt site rehberinden geldi.");
    expect(get(t, "helper.palette.askBlocked")).toBe("Yardımcı bu ay sınırda; arama ve kısayollar çalışıyor.");
    expect(get(t, "helper.shortcut.roomDay")).toBe("Salonun gün programı: {what}");
    expect(get(e, "helper.card.fromIndex")).toBe("From the site guide");
    expect(get(e, "helper.shortcut.roomDay")).toBe("A room's day plan: {what}");
    expect(String(get(e, "helper.palette.askBlocked"))).not.toContain("—");
  });

  it("m13: the status chip stays 24 px tall on touch and grows only its hit area", () => {
    const mode: HelperMode = { ai: false, state: "off", status: undefined, blocked: false, loading: false };
    renderHelper(<StatusChip mode={mode} />);
    const chip = screen.getByTestId("helper-status");
    expect(chip.className).toMatch(/(^| )h-6( |$)/);
    expect(chip.className).toMatch(/pointer-coarse:min-h-0/);
    expect(chip.className).not.toMatch(/pointer-coarse:min-h-11/);
    expect(chip.className).toMatch(/pointer-coarse:after:absolute/);
  });
});
