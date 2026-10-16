import { describe, expect, it } from "vitest";
import { HttpError } from "./client";
import { isStaleConflict, refusalCode, serverMessage } from "./error-text";

const e409 = (detail: unknown) => new HttpError(409, "409 Conflict", detail);

describe("API refusal text (round-1 R1-M-02 / R1-S-06)", () => {
  it("only a stale-record 409 is 'someone else changed it'", () => {
    expect(isStaleConflict(e409({ detail: { message: "the draft changed since you loaded it", current: null } }))).toBe(true);
    expect(isStaleConflict(e409({ detail: { code: "stale" } }))).toBe(true);
    expect(isStaleConflict(e409({ detail: { code: "scope_reduction", message: "run 9 covers weeks [6] only" } }))).toBe(false);
    expect(isStaleConflict(e409({ detail: { code: "forced_breaks" } }))).toBe(false);
    expect(isStaleConflict(e409({ detail: { message: "run cannot be published", issues: ["run 11 is ERROR"] } }))).toBe(false);
    expect(isStaleConflict(new HttpError(422, "422", {}))).toBe(false);
  });

  it("reads the server's own sentence in the planner's language", () => {
    const e = e409({ detail: { code: "scope_reduction", message: "run 9 covers weeks [6] only", message_tr: "#9 yalnız 6. haftaları kapsıyor" } });
    expect(refusalCode(e)).toBe("scope_reduction");
    expect(serverMessage(e, "tr")).toBe("#9 yalnız 6. haftaları kapsıyor");
    expect(serverMessage(e, "en")).toBe("run 9 covers weeks [6] only");
    expect(serverMessage(new HttpError(409, "x", { detail: { tr: "Boş plan yayımlanamaz", en: "An empty plan cannot be published" } }), "tr")).toBe("Boş plan yayımlanamaz");
    // the global Turkish toast never shows the backend's English detail
    expect(serverMessage(e409({ detail: { message: "run cannot be published", issues: ["run 11 is ERROR"] } }), "tr", true)).toBeNull();
    expect(serverMessage(new HttpError(422, "x", { detail: { code: "capacity", message_tr: "100 öğrenci 30 kişilik B 201'e sığmaz" } }), "tr", true)).toBe("100 öğrenci 30 kişilik B 201'e sığmaz");
  });
});
