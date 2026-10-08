import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MappingColumns, MappingProposals } from "@/lib/api/studio-schemas";
import { I18nProvider } from "@/lib/i18n/provider";
import { MappingStep, invertMapping, toSpec } from "./mapping-step";

const columns = MappingColumns.parse({
  mode: "columns",
  filename: "talepler.xlsx",
  sheets: ["Sayfa1"],
  sheet: "Sayfa1",
  header_row: 1,
  row_count: 3,
  columns: [
    { index: 0, header: "Ders Kodu", samples: ["ECZ 101", "HEM 334"] },
    { index: 1, header: "Program", samples: ["Eczacılık"] },
    { index: 2, header: "Derslik Talebi", samples: ["A 206"] },
    { index: 3, header: "Açıklama", samples: ["not"] },
  ],
  suggested_mapping: { columns: { program: 1, room: 2 }, room_rule: "prefer", hardness: "soft", weight: 5 },
  roles: {},
});
const result = MappingProposals.parse({ mode: "proposals", filename: "talepler.xlsx", proposals: [], section_edits: [], unparsed: [], counts: { ready: 0, needs_look: 0, couldnt_read: 0 } });

function setup() {
  const load = vi.fn().mockResolvedValue(columns);
  const submit = vi.fn().mockResolvedValue(result);
  const onDone = vi.fn();
  const onCancel = vi.fn();
  render(
    <I18nProvider initialLocale="en">
      <MappingStep filename="talepler.xlsx" load={load} submit={submit} onDone={onDone} onCancel={onCancel} />
    </I18nProvider>,
  );
  return { load, submit, onDone, onCancel };
}

describe("MappingStep (upload without an AI key)", () => {
  it("loads the columns once and pre-fills the suggested mapping", async () => {
    const { load } = setup();
    expect(await screen.findByTestId("mapping-role-1")).toHaveValue("program");
    expect(screen.getByTestId("mapping-role-2")).toHaveValue("room");
    expect(screen.getByTestId("mapping-role-0")).toHaveValue("");
    expect(screen.getAllByTestId("mapping-row")).toHaveLength(4);
    expect(screen.getByText("3 rows found (sheet Sayfa1)")).toBeInTheDocument();
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("sends the chosen mapping (one column per role) and the room rule", async () => {
    const { submit, onDone } = setup();
    await screen.findByTestId("mapping-role-0");
    await userEvent.selectOptions(screen.getByTestId("mapping-role-0"), "course");
    await userEvent.selectOptions(screen.getByTestId("mapping-role-3"), "room"); // moves "room" from column 2 to 3
    expect(screen.getByTestId("mapping-role-2")).toHaveValue("");
    await userEvent.click(screen.getByRole("radio", { name: "Always this room" }));
    await userEvent.click(screen.getByTestId("mapping-read"));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith(result));
    expect(submit).toHaveBeenCalledWith({ columns: { course: 0, program: 1, room: 3 }, room_rule: "pin", hardness: "hard", weight: 5, header_row: 1, sheet: "Sayfa1" });
  });

  it("needs the course or programme column before it can read rows", async () => {
    setup();
    await screen.findByTestId("mapping-role-1");
    await userEvent.selectOptions(screen.getByTestId("mapping-role-1"), "");
    expect(screen.getByTestId("mapping-read")).toBeDisabled();
    expect(screen.getByText("Pick the course (or programme) column first.")).toBeInTheDocument();
  });

  it("shows the server error and lets the planner cancel", async () => {
    const load = vi.fn().mockRejectedValue(new Error("the sheet is empty"));
    const onCancel = vi.fn();
    render(
      <I18nProvider initialLocale="en">
        <MappingStep filename="bos.csv" load={load} submit={vi.fn()} onDone={vi.fn()} onCancel={onCancel} />
      </I18nProvider>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("the sheet is empty");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalled();
  });
});

describe("mapping helpers", () => {
  it("inverts role → column and builds the backend spec", () => {
    expect(invertMapping({ course: 0, room: 3, bogus: 9 })).toEqual({ 0: "course", 3: "room" });
    expect(toSpec({ 0: "course", 1: "", 3: "room" }, "prefer", "soft", 5)).toEqual({ columns: { course: 0, room: 3 }, room_rule: "prefer", hardness: "soft", weight: 5, header_row: null, sheet: null });
  });
});
