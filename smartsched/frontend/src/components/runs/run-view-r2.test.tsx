/**
 * Round-2 lane E, T-R2-26 (R2-M-04 / R1-M-14) and T-R2-30 (R2-M-18): the run report shows one problem count (the
 * truth's broken + accepted exceptions, the headline's number), lists every unplaced class the truth names and
 * reads the broken-rule sentences in Turkish.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { BrokenRules, UnplacedList } from "./run-view";
import { brokenText, problemCount, truthOf } from "./run-truth";

const unplaced = Array.from({ length: 34 }, (_, i) => ({ id: 100 + i, label: `ING ${101 + i} §${(i % 3) + 1}`, request_ids: [100 + i], weeks: i % 5 === 0 ? [3, 4] : null }));
const truth = {
  source: "planner_check",
  verdict: "exceptions",
  placed: 683,
  total: 717,
  unplaced: 34,
  hard_score: 100,
  broken: [{ rule: "room_double_booking", message: "A102 week 3 day 1 P1: PHAR 240 §1, PHAR 474 §1", message_tr: "A102 · 3. hafta Pzt P1: PHAR 240 §1, PHAR 474 §1", request_ids: [1, 2], explained: false, reason: null, by_name: null, at: null }],
  broken_count: 1,
  exceptions: [{ cause: "D2", classes: 398, findings: 199, rule: true, label: { tr: "x", en: "x" } }],
  exceptions_total: 398,
  unplaced_list: unplaced,
  unplaced_count: 34,
  headline: { tr: "683/717 ders yerleşti · kesin kurallar korundu; 398 kabul edilmiş istisna listelendi", en: "..." },
};

describe("T-R2-26: one problem count and the full unplaced list", () => {
  it("parses unplaced_list / unplaced_count and message_tr; the problem count is broken + exceptions", () => {
    const t = truthOf(truth)!;
    expect(t.unplaced_list).toHaveLength(34);
    expect(t.unplaced_count).toBe(34);
    expect(t.unplaced_list[0]).toEqual({ id: 100, label: "ING 101 §1", request_ids: [100], weeks: [3, 4] });
    expect(t.broken[0].message_tr).toContain("3. hafta Pzt");
    expect(problemCount(t)).toBe(399);
    // an older stored truth without the list: nothing to show, no crash
    const old = truthOf({ ...truth, unplaced_list: undefined, unplaced_count: undefined })!;
    expect(old.unplaced_list).toEqual([]);
    expect(old.unplaced_count).toBeNull();
  });

  it("lists every unplaced class (34 of 34) with its missing weeks", () => {
    render(
      <I18nProvider initialLocale="tr">
        <UnplacedList truth={truthOf(truth)!} />
      </I18nProvider>,
    );
    const list = screen.getByTestId("unplaced-list");
    expect(list.querySelectorAll("li")).toHaveLength(34);
    expect(list).toHaveTextContent("ING 101 §1");
    expect(list).toHaveTextContent("3. ve 4. haftalar");
    expect(screen.getByTestId("unplaced-list-count")).toHaveTextContent("34");
  });

  it("the broken-rule sentence is Turkish in TR and English in EN (T-R2-30, R2-M-18)", () => {
    const t = truthOf(truth)!;
    expect(brokenText(t.broken[0], true)).toBe("A102 · 3. hafta Pzt P1: PHAR 240 §1, PHAR 474 §1");
    expect(brokenText(t.broken[0], false)).toBe("A102 week 3 day 1 P1: PHAR 240 §1, PHAR 474 §1");
    render(
      <I18nProvider initialLocale="tr">
        <BrokenRules truth={t} />
      </I18nProvider>,
    );
    const list = screen.getByTestId("verdict-broken");
    expect(list).toHaveTextContent("derslik çakışması: A102 · 3. hafta Pzt P1");
    expect(list.textContent).not.toMatch(/\bweek\b|\bday\b/);
  });
});
