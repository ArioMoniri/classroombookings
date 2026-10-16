import { describe, expect, it } from "vitest";
import { translate, type MessageKey } from "./index";
import { permissionLabel, permissionList, roleDescription, roleLabel, roleLabelIn } from "./roles";

const tr = (k: MessageKey, v?: Record<string, string | number>) => translate("tr", k, v);
const en = (k: MessageKey, v?: Record<string, string | number>) => translate("en", k, v);

// T-R1-30 (round-1 R1-M-16 / R1-A-10): the stored codes stay, what a person reads is localised
describe("role and permission display names", () => {
  it("built-in roles with their shipped name read in the reader's language", () => {
    expect(roleLabel(tr, { code: "TEACHER", name: "Teacher" })).toBe("Öğretim elemanı");
    expect(roleLabel(tr, { code: "ADMIN", name: "Administrator" })).toBe("Yönetici");
    expect(roleLabel(tr, { code: "PLANNER", name: "Planner" })).toBe("Planlamacı");
    expect(roleLabel(tr, { code: "VIEWER", name: "Viewer" })).toBe("İzleyici");
    // the Turkish name stored by an earlier save reads in English too
    expect(roleLabel(en, { code: "TEACHER", name: "Öğretim elemanı" })).toBe("Teacher");
    expect(roleLabelIn("en", { code: "admin", name: "" })).toBe("Administrator");
  });

  it("renamed built-in roles and custom roles keep their names", () => {
    expect(roleLabel(tr, { code: "TEACHER", name: "Akademisyen" })).toBe("Akademisyen");
    expect(roleLabel(tr, { code: null, name: "Kullanıcı yöneticisi" })).toBe("Kullanıcı yöneticisi");
    expect(roleLabel(tr, { code: "CUSTOM", name: "Laboratuvar sorumlusu" })).toBe("Laboratuvar sorumlusu");
    expect(roleLabel(tr, { code: "NONE", name: null })).toBe("Rolsüz");
    expect(roleLabel(tr, null)).toBe("");
  });

  it("shipped role descriptions are localised, custom ones kept", () => {
    expect(roleDescription(tr, { code: "PLANNER", description: "Planning office: imports, timetables and bookings" })).toMatch(/^Planlama birimi/);
    expect(roleDescription(tr, { code: "TEACHER", description: "Teacher" })).not.toMatch(/Teacher/);
    expect(roleDescription(tr, { code: "TEACHER", description: "Bölüm hocaları" })).toBe("Bölüm hocaları");
    expect(roleDescription(tr, { code: null, description: "kendi metni" })).toBe("kendi metni");
  });

  it("permissions read by their label, never the key or the backend's English", () => {
    expect(permissionLabel(tr, "book_single.edit_other_booking", "Edit other users' single bookings")).toBe("Tek seferlik: başkasınınkini düzenleme");
    expect(permissionLabel(tr, "bookings.skip_approval")).toBe("Onaysız doğrudan rezervasyon");
    expect(permissionLabel(tr, "x.unknown", "fallback")).toBe("fallback");
    const list = permissionList(tr, ["approvals.decide", "audit.view", "book_recur.cancel_other_booking", "setup.users"]);
    expect(list).not.toMatch(/approvals\.decide|audit\.view/);
    expect(list).toMatch(/\+1$/);
  });
});
