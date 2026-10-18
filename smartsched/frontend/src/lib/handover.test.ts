/**
 * HX-06 hand-over prefills (helper.md §4.3): the helper opens a page's own sheet or field with values in the
 * address; the page's own button does the write. These readers keep the values plain and bounded.
 */
import { describe, expect, it } from "vitest";
import { chatPrefill, invitePrefill, publishRequested, roleValueFor } from "./handover";

const q = (s: string) => new URLSearchParams(s);

describe("hand-over params", () => {
  it("?publish= opens the publish dialog of that run only", () => {
    expect(publishRequested(q("publish=1"), 42)).toBe(true);
    expect(publishRequested(q("publish=42"), 42)).toBe(true);
    expect(publishRequested(q("publish=41"), 42)).toBe(false);
    expect(publishRequested(q(""), 42)).toBe(false);
    expect(publishRequested(q("publish=yes"), 42)).toBe(false);
  });

  it("?chat= is plain text, trimmed, single-spaced control characters removed, at most 500 characters", () => {
    expect(chatPrefill(q("chat=MAT%20112'yi%20sal%C4%B1ya%20ta%C5%9F%C4%B1"))).toBe("MAT 112'yi salıya taşı");
    expect(chatPrefill(q("chat=%20%20"))).toBeNull();
    expect(chatPrefill(q(""))).toBeNull();
    expect(chatPrefill(q(`chat=${encodeURIComponent("a\u0000b\u202Ec\n\nd")}`))).toBe("abc d");
    expect(chatPrefill(q(`chat=${"x".repeat(900)}`))?.length).toBe(500);
  });

  it("?invite=1&email=&name=&role=&department= gives the invite fields; anything else is dropped", () => {
    expect(invitePrefill(q("invite=1&email=%20Ayse.K@uni.edu.tr%20&name=A.%20K.&role=TEACHER&department=7"))).toEqual({ email: "Ayse.K@uni.edu.tr", name: "A. K.", role: "TEACHER", department: "7" });
    expect(invitePrefill(q("email=a@b.c"))).toBeNull();
    expect(invitePrefill(q("invite=1&email=not-an-email&role=<script>&department=x"))).toEqual({ email: "", name: "", role: "", department: "" });
    expect(invitePrefill(q(`invite=1&name=${"n".repeat(300)}`))?.name.length).toBe(120);
  });

  it("maps a role code or id onto the form's role options", () => {
    const roles = [{ id: 3, code: "TEACHER" }, { id: 4, code: "PLANNER" }, { id: 9, code: null }];
    expect(roleValueFor("teacher", roles)).toBe("id:3");
    expect(roleValueFor("9", roles)).toBe("id:9");
    expect(roleValueFor("id:4", roles)).toBe("id:4");
    expect(roleValueFor("ADMIN", roles)).toBe("");
    // without the role list (no setup.roles): the seeded codes
    expect(roleValueFor("TEACHER", undefined)).toBe("code:TEACHER");
    expect(roleValueFor("7", undefined)).toBe("");
    expect(roleValueFor("", roles)).toBe("");
  });
});
