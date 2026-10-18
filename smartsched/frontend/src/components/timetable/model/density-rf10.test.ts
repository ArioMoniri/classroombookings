/**
 * RF-10 (audit 2026-10-17 A5): Ayarlar › Görünüm › Yoğunluk ("Sıkı") changed only data-table rows; the timetable
 * kept its own density. The personal setting is now the timetable's default density; the toolbar and a
 * `density=` link still override it for one view, and links stay short (the default is not written).
 */
import { describe, expect, it } from "vitest";
import { densityFromPersonal, parseViewState, serializeViewState } from "./view-state";

describe("RF-10: the personal density is the timetable default", () => {
  it("Sıkı → compact, Rahat → the timetable's standard default", () => {
    expect(densityFromPersonal("compact")).toBe("compact");
    expect(densityFromPersonal("comfortable")).toBe("standard");
  });

  it("no density in the URL takes the personal default; a link still overrides it", () => {
    const personal = densityFromPersonal("compact");
    expect(parseViewState(new URLSearchParams("week=3"), { density: personal }).density).toBe("compact");
    expect(parseViewState(new URLSearchParams("week=3&density=comfortable"), { density: personal }).density).toBe("comfortable");
  });

  it("the URL leaves out the personal default and keeps an explicit choice, so a reload keeps it", () => {
    const personal = densityFromPersonal("compact");
    const base = parseViewState(new URLSearchParams("week=3"), { density: personal });
    expect(serializeViewState(base, undefined, { density: personal }).has("density")).toBe(false);
    const standard = serializeViewState({ ...base, density: "standard" }, undefined, { density: personal });
    expect(standard.get("density")).toBe("standard");
    expect(parseViewState(standard, { density: personal }).density).toBe("standard");
  });

  it("without a personal default the old links are unchanged", () => {
    const s = parseViewState(new URLSearchParams("week=3"));
    expect(s.density).toBe("standard");
    expect(serializeViewState(s).has("density")).toBe(false);
    expect(serializeViewState({ ...s, density: "compact" }).get("density")).toBe("compact");
  });
});
