/**
 * Round-1 R1-M-04 / R1-M-05: the Studio card and the run report read one truth (`stats.truth`, the backend's
 * planner-level check): never "hiçbir kural bozulmadı" next to accepted exceptions or a broken hard rule; a broken
 * rule is listed with the forced move's reason.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { BrokenRules } from "./run-view";
import { runTruth, truthOf } from "./run-truth";
import { verdict } from "@/components/compare/compare-model";
import { planIsEmpty, planStatusKey, planTone } from "@/components/invigilation/invigilation-model";

const exceptions = {
  source: "planner_check",
  verdict: "exceptions",
  placed: 691,
  total: 713,
  unplaced: 22,
  hard_score: 100,
  broken: [],
  broken_count: 0,
  exceptions: [{ cause: "D2", classes: 190, findings: 95, rule: true, label: { tr: "planlama listesinde aynı saate sabitlenmiş iki dersin çakışması", en: "two fixed classes clash" } }],
  exceptions_total: 190,
  headline: { tr: "691/713 ders yerleşti · kesin kurallar korundu; 190 kabul edilmiş istisna listelendi", en: "691 of 713 classes placed · hard rules held; 190 accepted exception(s) listed" },
};
const broken = {
  ...exceptions,
  verdict: "broken",
  hard_score: 99,
  broken: [{ rule: "tags", message: "PHAR 240 §1 placed in the medicine (TIP) room A201", request_ids: [534], explained: true, reason: "Bölüm başkanı onayı", by_name: "F. B.", at: null }],
  broken_count: 1,
  headline: { tr: "691/713 ders yerleşti · 1 kesin kural bozuk (1 gerekçeli zorunlu taşıma)", en: "691 of 713 classes placed · 1 hard rule(s) broken (1 forced with a reason)" },
};

describe("one run truth", () => {
  it("parses the stored and the summary truth, the summary winning", () => {
    expect(truthOf(null)).toBeNull();
    expect(truthOf({ verdict: "nonsense" })).toBeNull();
    const t = truthOf(exceptions)!;
    expect(t.verdict).toBe("exceptions");
    expect(t.headline.tr).not.toContain("hiçbir kural bozulmadı");
    expect(runTruth({ truth: exceptions }, { truth: broken })?.verdict).toBe("broken");
    expect(runTruth({ truth: exceptions }, null)?.verdict).toBe("exceptions");
  });

  it("lists every broken rule with the reason of the forced move that explains it", () => {
    render(
      <I18nProvider initialLocale="tr">
        <BrokenRules truth={truthOf(broken)!} />
      </I18nProvider>,
    );
    const list = screen.getByTestId("verdict-broken");
    expect(list).toHaveTextContent("derslik özelliği");
    expect(list).toHaveTextContent("TIP");
    expect(list).toHaveTextContent("Bölüm başkanı onayı");
    expect(list).toHaveTextContent("F. B.");
  });
});

describe("compare: empty data is never better (R1-M-10)", () => {
  it("a metric marked not comparable reads 'karşılaştırılamaz'", () => {
    expect(verdict({ better: "b", direction: -1, delta: -348, comparable: false })).toBe("incomparable");
    expect(verdict({ better: null, direction: -1, delta: null, comparable: false })).toBe("incomparable");
    expect(verdict({ better: "b", direction: -1, delta: -3 })).toBe("better");
  });
});

describe("invigilation: an empty plan is not 'En iyi' (R1-M-11)", () => {
  const counts = { posts: 0, required: 0, filled: 0, missing: 0, people: 0, eligible_people: 0 };
  it("is named and toned as empty", () => {
    expect(planIsEmpty({ status: "OPTIMAL", counts, empty: true })).toBe(true);
    expect(planIsEmpty({ status: "OPTIMAL", counts })).toBe(true);
    expect(planStatusKey({ status: "OPTIMAL", counts })).toBe("invigilation.status.EMPTY");
    expect(planTone({ status: "OPTIMAL", counts })).toBe("warning");
    expect(planIsEmpty({ status: "RUNNING", counts })).toBe(false);
    expect(planIsEmpty({ status: "OPTIMAL", counts: { ...counts, posts: 600, required: 640, filled: 640 } })).toBe(false);
  });
});
