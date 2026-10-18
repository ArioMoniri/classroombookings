// E2EA-F05 (FIX-K): the import history shows the 8 newest jobs and "Daha eski içe aktarmaları göster" reveals the
// older ones (the seed jobs stay reachable); focus moves to the first revealed row, never to <body>.
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ImportJob } from "@/lib/api/schemas";
import { importJob } from "@/lib/api/adapters";
import { I18nProvider } from "@/lib/i18n/provider";
import { ImportHistory } from "./import-history";

const job = (id: number) =>
  ImportJob.parse(importJob({ id, kind: "planning-list", filename: `liste-${id}.xlsx`, status: "DONE", created_at: "2026-10-18T09:00:00", actor: "system", source: id <= 2 ? "seed" : "upload", created_by_name: null, summary: { rows_total: 1, warnings: [] } }));

describe("ImportHistory paging (E2EA-F05)", () => {
  it("reveals older jobs in steps and moves focus to the first revealed row", () => {
    const jobs = Array.from({ length: 12 }, (_, i) => job(12 - i));
    render(
      <I18nProvider initialLocale="tr">
        <ImportHistory jobs={jobs} />
      </I18nProvider>,
    );
    expect(screen.queryByTestId("import-history-1")).toBeNull();
    const more = screen.getByTestId("import-history-more");
    expect(more).toHaveTextContent("Daha eski içe aktarmaları göster (4)");
    fireEvent.click(more);
    expect(screen.getByTestId("import-history-1")).toHaveTextContent("İlk kurulum (sistem)");
    expect(screen.queryByTestId("import-history-more")).toBeNull();
    expect(document.activeElement).toBe(screen.getByTestId("import-history-report-4"));
  });
});
