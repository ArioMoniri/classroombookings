/**
 * T-R1-36 (round-1 R1-M-33): the exam-period card names the exam weeks with their dates, and the policy's role
 * picker offers only roles a policy can bind (planning administrators are never bound).
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { emptyPolicy } from "@/lib/api/booking-policies";
import { I18nProvider } from "@/lib/i18n/provider";
import { examRanges } from "./policies-admin";
import { PolicyForm } from "./policy-form";

describe("exam ranges", () => {
  it("joins consecutive exam and make-up weeks and ends each range on its last week's Sunday", () => {
    const weeks = [
      { index: 13, kind: "LECTURE" as const, start_date: "2026-05-18" },
      { index: 15, kind: "EXAM" as const, start_date: "2026-06-01" },
      { index: 14, kind: "EXAM" as const, start_date: "2026-05-25" },
      { index: 17, kind: "MAKEUP" as const, start_date: "2026-06-15" },
    ];
    expect(examRanges(weeks)).toEqual([
      { weeks: [14, 15], from: "2026-05-25", to: "2026-06-07" },
      { weeks: [17], from: "2026-06-15", to: "2026-06-21" },
    ]);
    expect(examRanges([])).toEqual([]);
  });
});

describe("policy role picker", () => {
  const ctx = {
    rooms: [],
    groups: [],
    terms: [],
    roles: [
      { code: "ADMIN", name: "Yönetici", bindable: false },
      { code: "PLANNER", name: "Planlamacı", bindable: false },
      { code: "TEACHER", name: "Öğretim elemanı", bindable: true },
    ],
  };

  it("offers only roles a policy binds", () => {
    render(
      <I18nProvider initialLocale="tr">
        <PolicyForm initial={emptyPolicy()} ctx={ctx} busy={false} serverError={null} onSave={vi.fn()} onCancel={vi.fn()} />
      </I18nProvider>,
    );
    expect(screen.getByTestId("policy-role-TEACHER")).toHaveTextContent("Öğretim elemanı");
    expect(screen.queryByTestId("policy-role-ADMIN")).toBeNull();
    expect(screen.queryByTestId("policy-role-PLANNER")).toBeNull();
  });

  it("keeps a role an older policy names so it can be removed", () => {
    render(
      <I18nProvider initialLocale="tr">
        <PolicyForm initial={{ ...emptyPolicy(), role_codes: ["ADMIN"] }} ctx={ctx} busy={false} serverError={null} onSave={vi.fn()} onCancel={vi.fn()} />
      </I18nProvider>,
    );
    expect(screen.getByTestId("policy-role-ADMIN")).toBeInTheDocument();
  });
});
