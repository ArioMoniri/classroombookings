/** AS-17 run header: "Profil: … v2 · ağırlıklar", the weights that did not come from the defaults, peak smoothing. */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { orderGroups } from "./issue-groups";
import { RunProfileLine, runProfileInfo } from "./run-profile";

const stats = {
  profile: { key: "final_pc", version: 2, id: 5, builtin: false, name: { tr: "Final haftası", en: "Final week" }, source: "profile:final_pc@2", peak_threshold_pct: 85 },
  weights_effective: { building_preference: 8, room_preference: 10, peak_smoothing: 3, stability: 1 },
  weights_source: { building_preference: "profile:final_pc@2", room_preference: "default", peak_smoothing: "profile:final_pc@2", stability: "run" },
  horizon_skipped_weeks: [8, 15],
};

describe("runProfileInfo", () => {
  it("keeps only the non-default weights with their source, and nothing for a run from before AS-01", () => {
    const info = runProfileInfo(stats);
    expect(info?.profile).toEqual({ key: "final_pc", version: 2, name: { tr: "Final haftası", en: "Final week" } });
    expect(info?.changed).toEqual([
      { key: "building_preference", value: 8, source: "profile" },
      { key: "peak_smoothing", value: 3, source: "profile" },
      { key: "stability", value: 1, source: "run" },
    ]);
    expect(info?.peakSmoothing).toBe(3);
    expect(runProfileInfo({ placed: 10 })).toBeNull();
    expect(runProfileInfo({ profile: null, weights_effective: { stability: 1 }, weights_source: { stability: "default" } })?.profile).toBeNull();
  });
});

describe("RunProfileLine", () => {
  it("reads 'Profil: Final haftası v2 · ağırlıklar' and opens the weights with their source", () => {
    render(<I18nProvider initialLocale="tr"><RunProfileLine r={{ stats_detail: stats }} /></I18nProvider>);
    const line = screen.getByTestId("run-profile");
    expect(line).toHaveTextContent("Profil: Final haftası v2·ağırlıklar (3 değişik)");
    fireEvent.click(screen.getByText("ağırlıklar (3 değişik)"));
    expect(screen.getByTestId("run-weights")).toHaveTextContent("Talep edilen bina: 8 · profilden");
    expect(screen.getByTestId("run-peak-smoothing")).toHaveTextContent("Yoğun saatleri yayma açık (ağırlık 3)");
    expect(line).toHaveTextContent("Planlanmayan haftalar (sınav / tatil): 8, 15");
    expect(line.textContent).not.toMatch(/_/);
  });

  it("a run without a profile says so with the standard weights", () => {
    render(<I18nProvider initialLocale="tr"><RunProfileLine r={{ stats_detail: { profile: null, weights_effective: { stability: 1 }, weights_source: { stability: "default" } } }} /></I18nProvider>);
    expect(screen.getByTestId("run-profile")).toHaveTextContent("Profil: yok · standart ağırlıklar");
    expect(screen.queryByTestId("run-peak-smoothing")).toBeNull();
  });
});

describe("data issues order", () => {
  it("lists peak_pressure and exam_load after the data problems", () => {
    const g = (code: string, count: number) => ({ code, count, title: { tr: code, en: code }, items: [] }) as never;
    expect(orderGroups([g("peak_pressure", 9), g("missing_capacity", 2), g("locked_room_blocked", 1), g("exam_load", 4)]).map((x: { code: string }) => x.code)).toEqual(["locked_room_blocked", "missing_capacity", "peak_pressure", "exam_load"]);
  });
});
