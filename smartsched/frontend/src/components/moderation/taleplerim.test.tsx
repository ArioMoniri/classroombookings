/**
 * T-R1-11 Taleplerim: the theory and the lab of one class carry a session label; the short own table lets the
 * asked → assigned pair wrap (never truncated) and makes every row a Tab stop. Real Güz rows of PSY 277 (Mon P3–P5
 * "Derslik" and Mon P7–P8 "Bilgisayar Laboratuvarı (JASP)", tag PC) and PSI 213.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// jsdom has no layout: render every row (the real virtualiser measures them in the browser)
vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: ({ count }: { count: number }) => ({
    getVirtualItems: () => Array.from({ length: count }, (_, i) => ({ index: i, start: i * 36, key: i })),
    getTotalSize: () => count * 36,
    scrollToIndex: () => undefined,
    measureElement: () => undefined,
  }),
}));
import { Matching } from "@/lib/api/moderation";
import { ModTable } from "./mod-table";
import { sessionTags } from "./moderation-model";

const row = (request_id: number, label: string, room_text: string, tags: string[] = []): Matching =>
  Matching.parse({
    request_id,
    section_id: request_id + 1000,
    term_id: 2,
    label,
    requested: { day: 1, start_period: 3, end_period: 5, room_text, tags },
    definitive: { rooms: [] },
    verdict: "satisfied",
    verdict_text: { tr: "Karşılandı", en: "Satisfied" },
    priority: { value: 0, source: "default" },
  });

describe("Taleplerim", () => {
  it("labels the theory and the lab of the same class, numbers equal sessions, leaves unique rows alone", () => {
    const rows = [row(1, "PSY 277", "Derslik"), row(2, "PSY 277", "Bilgisayar Laboratuvarı (JASP)", ["PC"]), row(3, "PSI 213", "Derslik"), row(4, "PSY 213", "Derslik"), row(5, "PSY 213", "Derslik")];
    const tags = sessionTags(rows);
    expect(tags.get(1)).toEqual({ kind: "theory", n: null });
    expect(tags.get(2)).toEqual({ kind: "lab", n: null });
    expect(tags.has(3)).toBe(false);
    expect(tags.get(4)).toEqual({ kind: "theory", n: 1 });
    expect(tags.get(5)).toEqual({ kind: "theory", n: 2 });
  });

  it("wrapping columns are not truncated and every row is a Tab stop with tabRows", () => {
    const rows = [row(1, "PSY 277", "Derslik"), row(2, "PSY 277", "Lab", ["PC"]), row(3, "PSI 213", "Derslik")];
    render(
      <ModTable
        rows={rows}
        autoRows
        tabRows
        getId={(m) => m.request_id}
        caption="3 talep"
        columns={[
          { id: "course", header: "Ders", width: "8rem", cell: (m) => m.label },
          { id: "pair", header: "İstenen → Atanan", width: "minmax(16rem,3fr)", wrap: true, cell: () => "Çar P7–P9 · Derslik → Çar P7–P9 13:30–15:50 · A 308" },
        ]}
        testId="mine-table"
      />,
    );
    const table = screen.getByTestId("mine-table");
    const cells = table.querySelectorAll('[role="gridcell"]');
    expect([...cells].filter((c) => c.textContent?.includes("A 308")).every((c) => !c.className.includes("truncate"))).toBe(true);
    const rowsEls = table.querySelectorAll('[data-testid="mod-row"]');
    expect(rowsEls.length).toBeGreaterThan(0);
    expect([...rowsEls].every((r) => r.getAttribute("tabindex") === "0")).toBe(true);
    expect(table.innerHTML).not.toContain("min-w-max");
  });
});
