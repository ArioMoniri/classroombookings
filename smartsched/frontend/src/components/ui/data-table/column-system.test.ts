import { describe, expect, it } from "vitest";

import { autoWidth, layoutColumns, resizeStep, type ColumnSpec } from "./column-system";

type R = { code: string; name: string; seats: number };
const rows: R[] = [
  { code: "A 101", name: "Amfi", seats: 58 },
  { code: "B 207", name: "Bilgisayar laboratuvarı ve proje odası", seats: 40 },
];
const specs: ColumnSpec<R>[] = [
  { id: "code", header: "Kod", pin: "left", priority: 1, text: (r) => r.code, minSize: 72 },
  { id: "name", header: "Ad", grow: 1, priority: 2, text: (r) => r.name, minSize: 120, maxSize: 600 },
  { id: "seats", header: "Koltuk", align: "end", priority: 4, text: (r) => String(r.seats), minSize: 64 },
  { id: "tags", header: "Etiketler", priority: 5, minSize: 120 },
];

describe("column system", () => {
  it("auto width = the widest of header and rows (+ padding), clamped to [min, max]", () => {
    const w = autoWidth(specs[1], rows);
    expect(w).toBeGreaterThan(autoWidth(specs[1], [rows[0]]));
    expect(w).toBeLessThanOrEqual(600);
    expect(autoWidth(specs[0], [])).toBeGreaterThanOrEqual(72);
  });

  it("gives the slack to grow columns and never to user-sized ones", () => {
    const base = { code: 80, name: 200, seats: 70, tags: 120 };
    const wide = layoutColumns(specs, base, { container: 800 });
    expect(wide.total).toBe(800);
    expect(wide.widths.name).toBe(800 - 80 - 70 - 120);
    // max size caps the growth
    expect(layoutColumns(specs, base, { container: 2000 }).widths.name).toBe(600);
    const fixed = layoutColumns(specs, base, { container: 800, userSized: new Set(["name"]) });
    expect(fixed.widths.name).toBe(200);
    expect(fixed.template).toBe("80px 200px 70px 120px");
  });

  it("hides by priority (5 first) when the minimums do not fit, never pinned or priority 1", () => {
    const base = { code: 80, name: 200, seats: 70, tags: 120 };
    const narrow = layoutColumns(specs, base, { container: 250 });
    expect(narrow.squeezed).toEqual(["tags", "seats"]);
    expect(narrow.ids).toEqual(["code", "name"]);
    const tiny = layoutColumns(specs, base, { container: 100 });
    expect(tiny.ids).toContain("code");
  });

  it("pins left columns first with sticky offsets, honours the user's order and hidden set", () => {
    const base = { code: 80, name: 200, seats: 70, tags: 120 };
    const l = layoutColumns(specs, base, { container: 0, order: ["seats", "name", "code"], hidden: new Set(["tags"]) });
    expect(l.ids).toEqual(["code", "seats", "name"]);
    expect(l.pinLeft).toEqual({ code: 0 });
    expect(l.lastPinned).toBe("code");
  });

  it("keyboard resize steps: 8 px, Shift 32 px", () => {
    expect(resizeStep("ArrowRight", false)).toBe(8);
    expect(resizeStep("ArrowLeft", true)).toBe(-32);
    expect(resizeStep("a", false)).toBe(0);
  });
});
