import { describe, expect, it } from "vitest";
import { HttpError } from "./client";
import { isStaleConflict, problemDetail, problemText, refusalCode, serverMessage, stripPydanticPrefix, validationIssues } from "./error-text";

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

describe("validation issues (round-1 R1-M-17, T-R1-31)", () => {
  const e422 = (items: unknown[]) => new HttpError(422, "422", { detail: items });
  it("prefers the validator's Turkish sentence and drops pydantic's prefix", () => {
    const e = e422([{ type: "webhook_url_blocked", loc: ["body", "url"], msg: "blocked address: webhook URLs may not point at loopback", ctx: { code: "webhook_url_blocked", message_tr: "Bu adres yerel ağa gidiyor.", message_en: "blocked address: webhook URLs may not point at loopback" } }]);
    expect(validationIssues(e, "tr")).toEqual([{ field: "url", text: "Bu adres yerel ağa gidiyor.", detail: "blocked address: webhook URLs may not point at loopback", code: "webhook_url_blocked" }]);
    expect(problemText(e, "tr")).toBe("Bu adres yerel ağa gidiyor.");
    expect(problemText(e, "en")).toBe("blocked address: webhook URLs may not point at loopback");
    expect(problemDetail(e, "tr")).toBe("blocked address: webhook URLs may not point at loopback");
    expect(problemDetail(e, "en")).toBeNull();
    const plain = e422([{ type: "value_error", loc: ["body", "tenant_id"], msg: "Value error, tenant id 'common' is not allowed", ctx: { error: {} } }]);
    expect(problemText(plain, "en")).toBe("tenant id 'common' is not allowed");
    expect(problemText(plain, "tr")).toBe("Girilen değer kabul edilmedi.");
    expect(problemDetail(plain, "tr")).toBe("tenant id 'common' is not allowed");
    expect(problemText(e422([{ type: "missing", loc: ["body", "events"], msg: "Field required" }]), "tr")).toBe("Bu alan zorunlu.");
    expect(stripPydanticPrefix("Assertion failed, x")).toBe("x");
  });
  it("falls back to the coded refusal body and never says 'Value error'", () => {
    const e = new HttpError(400, "400", { detail: { code: "image_not_image", message: "the file is not a png", message_tr: "Dosya bir görsel değil." } });
    expect(problemText(e, "tr")).toBe("Dosya bir görsel değil.");
    expect(problemDetail(e, "tr")).toBe("the file is not a png");
    expect(problemText(new HttpError(422, "x", { detail: "Value error, URL too long" }), "tr")).toBe("URL too long");
    expect(problemText(new Error("boom"), "tr")).toBeNull();
    expect(validationIssues(new HttpError(409, "x", { detail: { code: "stale" } }), "tr")).toEqual([]);
  });
});
