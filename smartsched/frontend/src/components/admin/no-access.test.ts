import { describe, expect, it } from "vitest";
import { translate } from "@/lib/i18n";

// T-R1-38: the shared no-access page (admin-gate.tsx, app-shell's route guard) is shown on every screen a role
// cannot open (/timetable for an academician), so it must not call the page a setup screen
describe("no-access page text", () => {
  it("is generic in Turkish and English", () => {
    const tr = translate("tr", "crbs.admin.noAccessBody");
    expect(tr).toContain("Bu sayfa için izniniz yok");
    expect(tr).not.toMatch(/kurulum/i);
    expect(translate("en", "crbs.admin.noAccessBody")).not.toMatch(/setup/i);
  });
});
