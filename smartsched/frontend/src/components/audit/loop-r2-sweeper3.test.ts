/** Flow-loop round 2, sweeper 3 (item 4): the audit log reads the cancel-reason *codes* the backend writes
 * (`replaced_by_series:<id>` next to `undo_of:<id>`) in the UI language, with the wording of
 * components/bookings/cancel-reason.ts. */
import { describe, expect, it } from "vitest";
import { auditReason } from "./audit-model";
import { translate, type MessageKey } from "@/lib/i18n";

describe("sweeper 3: auditReason codes", () => {
  const tr = (key: MessageKey, vars?: Record<string, string | number>) => translate("tr", key, vars);
  const en = (key: MessageKey, vars?: Record<string, string | number>) => translate("en", key, vars);
  it("decodes replaced_by_series:<id> like undo_of:<id>", () => {
    expect(auditReason("replaced_by_series:8", tr)).toBe("Seri #8 ile değiştirildi");
    expect(auditReason("replaced_by_series:8", en)).toBe("Replaced by series #8");
    expect(auditReason("undo_of:41", tr)).toBe("Geri alma: #41");
    expect(auditReason("undo_of:41", en)).toBe("Undo of #41");
  });
  it("leaves a person's words and malformed codes as typed", () => {
    expect(auditReason("replaced_by_series:x", tr)).toBe("replaced_by_series:x");
    expect(auditReason("Toplantı iptal", tr)).toBe("Toplantı iptal");
    expect(auditReason(null, tr)).toBeNull();
  });
});
