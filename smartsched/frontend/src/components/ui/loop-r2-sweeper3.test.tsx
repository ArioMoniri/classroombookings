// Flow-loop round 2, sweeper 3 (item 1, MOBILE M-02 on /find-room and the recurring sheet): the DateField's "Takvimi aç"
// trigger is a REAL 44 × 44 box on coarse pointers (the ::after hit area alone is clipped by the recurring date table's
// overflow:auto and measured 32 × 32), inside the 44 px field; fine pointers keep the 28 px glyph button.
import { render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { DateField } from "@/components/ui/date-field";

function Harness() {
  const [v, setV] = useState("2026-10-15");
  return <DateField aria-label="Tarih" value={v} onChange={setV} locale="tr-TR" />;
}

describe("sweeper 3 / M-02: DateField calendar trigger on touch", () => {
  it("is a 44 × 44 box flush with the field's edge on coarse pointers, and the input clears it", () => {
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "Takvimi aç" });
    expect(trigger).toHaveClass("size-(--control-h-xs)", "pointer-coarse:size-11", "pointer-coarse:right-0");
    expect(screen.getByRole("textbox", { name: "Tarih" })).toHaveClass("pr-9", "pointer-coarse:pr-11");
  });
});
