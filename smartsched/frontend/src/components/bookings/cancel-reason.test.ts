import { describe, expect, it } from "vitest";
import { cancelReasonText } from "./cancel-reason";

const t = (key: string, v: Record<string, string | number> = {}) => (key === "crbs.cancel.replacedBySeries" ? `Seri #${v.id} ile değiştirildi` : key === "wave1.audit.reasonUndoOf" ? `Geri alma: #${v.id}` : key);

describe("T-R2-17 cancel reason", () => {
  it("renders the coded reasons in the UI language and leaves typed ones alone", () => {
    expect(cancelReasonText("replaced_by_series:7", t)).toBe("Seri #7 ile değiştirildi");
    expect(cancelReasonText("undo_of:164", t)).toBe("Geri alma: #164");
    expect(cancelReasonText("Oda bakımda", t)).toBe("Oda bakımda");
    expect(cancelReasonText(null, t)).toBeNull();
  });
});
