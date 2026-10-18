/**
 * HX-01: the zod card schema is generated from the backend's JSON Schema snapshot and stays in step with it.
 * The fixtures (`__fixtures__/cards.json`) were built and validated with the backend's own pydantic models.
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { generate, OUT_PATH, SCHEMA_PATH } from "../../../scripts/gen-helper-schema.mjs";
import fixtures from "./__fixtures__/cards.json";
import { CARD_TYPES, HELPER_CARD_SCHEMA_ID, HELPER_CARD_SCHEMA_SHA256, HelperCard } from "./schema.gen";

const source = readFileSync(SCHEMA_PATH, "utf8");

describe("helper.card.v1 zod (generated)", () => {
  it("is generated from the current backend snapshot (snapshot test)", () => {
    expect(HELPER_CARD_SCHEMA_SHA256).toBe(createHash("sha256").update(source).digest("hex"));
    expect(readFileSync(OUT_PATH, "utf8")).toBe(generate(JSON.parse(source), source));
    expect(HELPER_CARD_SCHEMA_ID).toBe("helper.card.v1");
  });

  it("covers every wire type of the server", () => {
    const schema = JSON.parse(source) as { discriminator: { mapping: Record<string, string> } };
    expect([...CARD_TYPES].sort()).toEqual(Object.keys(schema.discriminator.mapping).sort());
    expect(CARD_TYPES).toContain("choice");
  });

  it("parses every fixture card the backend models accept", () => {
    for (const [name, card] of Object.entries(fixtures)) {
      const r = HelperCard.safeParse(card);
      expect(r.success, `${name}: ${r.success ? "" : JSON.stringify(r.error.issues[0])}`).toBe(true);
    }
  });

  it("rejects HTML, links and script URLs in any text, like the server", () => {
    const hostile = ["<b>kalın</b>", "https://evil.example/x", "www.evil.example", "javascript:alert(1)", "data:text/html,x"];
    for (const text of hostile) {
      expect(HelperCard.safeParse({ ...fixtures.answer, text }).success, text).toBe(false);
      expect(HelperCard.safeParse({ ...fixtures.confirm, button: { tr: text, en: "Book" } }).success, text).toBe(false);
    }
  });

  it("rejects unknown fields and unknown types (nothing renders from untyped data)", () => {
    expect(HelperCard.safeParse({ ...fixtures.answer, html: "x" }).success).toBe(false);
    expect(HelperCard.safeParse({ ...fixtures.answer, type: "widget" }).success).toBe(false);
    expect(HelperCard.safeParse({ ...fixtures.nav, href: "/admin" }).success).toBe(false);
  });

  it("keeps the confirm token and choice bounds of the contract", () => {
    expect(HelperCard.safeParse({ ...fixtures.confirm, token: "a b" }).success).toBe(false);
    expect(HelperCard.safeParse({ ...fixtures.choice, options: fixtures.choice.options.slice(0, 1) }).success).toBe(false);
  });
});
