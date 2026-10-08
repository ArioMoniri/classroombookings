import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { sampleWarnings } from "@/test/fixtures/parse-warnings";
import { ParseWarningsTable, countBySeverity } from "./parse-warnings-table";

describe("ParseWarningsTable", () => {
  it("counts severities", () => {
    expect(countBySeverity(sampleWarnings())).toEqual({ error: 3, warning: 4, info: 5 });
  });

  it("renders all rows sorted errors-first and filters by severity and search", async () => {
    const user = userEvent.setup();
    render(<ParseWarningsTable warnings={sampleWarnings()} />);
    const table = screen.getByRole("table");
    const rows = () => within(table).getAllByRole("row").slice(1);
    expect(rows()).toHaveLength(12);
    expect(rows()[0]).toHaveAttribute("data-severity", "error");
    expect(rows()[11]).toHaveAttribute("data-severity", "info");

    await user.click(screen.getByRole("button", { name: /Hata|Error/ }));
    expect(rows()).toHaveLength(3);
    expect(rows().every((r) => r.getAttribute("data-severity") === "error")).toBe(true);

    await user.click(screen.getByRole("button", { name: /Tümü|All/ }));
    await user.type(screen.getByRole("textbox"), "ACU 311");
    expect(rows()).toHaveLength(1);
    expect(rows()[0]).toHaveTextContent("Ders Kodu");
  });

  it("shows the clean state when there are no warnings", () => {
    render(<ParseWarningsTable warnings={[]} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});
