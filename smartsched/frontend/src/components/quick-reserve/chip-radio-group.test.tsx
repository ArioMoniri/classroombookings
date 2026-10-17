/** W3-SLOT quick reserve: the chip radiogroup is keyboard and screen-reader complete (quick-reserve.md §11). */
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { ChipRadioGroup } from "./chip-radio-group";

function Harness({ onCommit }: { onCommit?: (v: string) => void }) {
  const [v, setV] = useState<string>("b");
  return (
    <ChipRadioGroup<string>
      label="Gün"
      value={v}
      onChange={setV}
      onCommit={onCommit}
      items={[
        { value: "a", label: "Bugün" },
        { value: "b", label: "Yarın" },
        { value: "c", label: "Çar 21", disabled: true, name: "Çar 21, Tatil: Kandil" },
        { value: "d", label: "Per 22" },
      ]}
    />
  );
}

describe("ChipRadioGroup", () => {
  it("one tab stop on the selected chip; arrows move and select, skipping nothing; disabled chips are reachable but never chosen", () => {
    render(<Harness />);
    const radios = screen.getAllByRole("radio");
    expect(screen.getByRole("radiogroup", { name: "Gün" })).toBeTruthy();
    expect(radios.map((r) => r.getAttribute("tabindex"))).toEqual(["-1", "0", "-1", "-1"]);
    radios[1]!.focus();
    fireEvent.keyDown(radios[1]!, { key: "ArrowRight" });
    expect(document.activeElement).toBe(radios[2]);
    expect(radios[2]!.getAttribute("aria-disabled")).toBe("true");
    expect(radios[2]!.getAttribute("aria-label")).toContain("Tatil");
    expect(radios[1]!.getAttribute("aria-checked")).toBe("true");
    fireEvent.keyDown(radios[2]!, { key: "ArrowRight" });
    expect(screen.getAllByRole("radio")[3]!.getAttribute("aria-checked")).toBe("true");
    fireEvent.keyDown(radios[3]!, { key: "Home" });
    expect(screen.getAllByRole("radio")[0]!.getAttribute("aria-checked")).toBe("true");
    fireEvent.click(radios[2]!);
    expect(screen.getAllByRole("radio")[2]!.getAttribute("aria-checked")).toBe("false");
  });

  it("Enter commits the focused chip", () => {
    const onCommit = vi.fn();
    render(<Harness onCommit={onCommit} />);
    const radios = screen.getAllByRole("radio");
    fireEvent.keyDown(radios[3]!, { key: "Enter" });
    expect(onCommit).toHaveBeenCalledWith("d");
    fireEvent.keyDown(radios[2]!, { key: "Enter" });
    expect(onCommit).toHaveBeenCalledTimes(1);
  });
});
