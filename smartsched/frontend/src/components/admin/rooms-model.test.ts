import { describe, expect, it } from "vitest";
import { roomCodeLabel, roomTitle } from "./rooms-model";

describe("room admin names (T-R1-34)", () => {
  it("shows the stored code with a space", () => {
    expect(roomCodeLabel("T101")).toBe("T 101");
    expect(roomCodeLabel("A101")).toBe("A 101");
    expect(roomCodeLabel("CZ01")).toBe("C z01");
    expect(roomCodeLabel("T 101")).toBe("T 101");
    expect(roomCodeLabel("LAB")).toBe("LAB");
    expect(roomCodeLabel("")).toBe("");
  });
  it("names a room once: code, then its own name", () => {
    expect(roomTitle({ code: "T101", display_name: "Test dersliği" })).toBe("T 101 · Test dersliği");
    expect(roomTitle({ code: "A101", display_name: "A 101" })).toBe("A 101");
    expect(roomTitle({ code: "A101", display_name: null })).toBe("A 101");
  });
});
