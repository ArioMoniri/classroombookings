import { describe, expect, it } from "vitest";
import type { Constraint } from "@/lib/api/schemas";
import { readNotes, unparsedFromIssues } from "./notes-reading";

const rule = (over: Partial<Constraint>): Constraint => ({ id: 1, term_id: 1, run_id: null, kind: "building_preference", params: { event_ids: [42], kinds: ["course"] }, hardness: "soft", weight: 5, source: "FILE", nl_text: "Mümkünse B Blok olmasın", enabled: false, ...over });

const NOTES = "Mümkünse B Blok olmasın. JASP kürsü bilgisayarında kurulu olsun.";

describe("readNotes (A-04: the request's free-text notes in the inspector)", () => {
  it("no notes → nothing to show", () => {
    expect(readNotes(42, null, [], [])).toBeNull();
    expect(readNotes(42, "  ", [], [])).toBeNull();
  });

  it("lists the rules read from this request's notes, with their state", () => {
    const r = readNotes(42, NOTES, [rule({ id: 7 }), rule({ id: 8, nl_text: "A 205", params: { event_ids: [99] } }), rule({ id: 9, source: "ADMIN" })], []);
    expect(r?.rules).toEqual([{ id: 7, text: "Mümkünse B Blok olmasın", kind: "building_preference", state: "pending" }]);
  });

  it("an enabled rule is on; a rule whose wording is not in the notes (request cell) is not listed here", () => {
    const r = readNotes(42, NOTES, [rule({ id: 7, enabled: true }), rule({ id: 10, nl_text: "A veya C blokta" })], []);
    expect(r?.rules.map((x) => [x.id, x.state])).toEqual([[7, "on"]]);
  });

  it("wishes the importer could not read are flagged with their reason", () => {
    const r = readNotes(42, NOTES, [rule({ id: 7 })], [{ text: "JASP kürsü bilgisayarında kurulu olsun", reason: "no room feature for this wish" }]);
    expect(r?.unparsed).toEqual([{ text: "JASP kürsü bilgisayarında kurulu olsun", reason: "no room feature for this wish" }]);
    expect(r?.unread).toBe(false);
  });

  it("fallback (no data-issues report): notes that produced no rule are flagged as unread as a whole", () => {
    expect(readNotes(42, NOTES, [], null)).toMatchObject({ rules: [], unparsed: [], unread: true });
    expect(readNotes(42, NOTES, [rule({ id: 7 })], null)?.unread).toBe(false);
  });

  it("matching is case- and diacritic-insensitive (Turkish İ/ı)", () => {
    const r = readNotes(42, "MÜMKÜNSE B BLOK OLMASIN", [rule({ id: 7 })], []);
    expect(r?.rules).toHaveLength(1);
  });
});

describe("unparsedFromIssues", () => {
  it("takes this request's unparsed_preference items from the data-issues report", () => {
    const groups = [
      { code: "unparsed_preference", items: [{ request_ids: [42], params: { text: "JASP", reason: "no room feature for this wish", column: "Derse Özel Açıklama" } }, { request_ids: [5], params: { text: "x", reason: "y" } }] },
      { code: "preference_review", items: [{ request_ids: [42], params: { text: "B Blok" } }] },
    ];
    expect(unparsedFromIssues(groups, 42)).toEqual([{ text: "JASP", reason: "no room feature for this wish" }]);
    expect(unparsedFromIssues(undefined, 42)).toBeNull();
  });
});
