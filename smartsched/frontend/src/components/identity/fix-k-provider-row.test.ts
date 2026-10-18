// E2EB-F14 (FIX-K): the provider list says why a provider is in error in words, not "discovery: metadata_signature".
import { describe, expect, it } from "vitest";
import { checkFailureText } from "./identity-providers-panel";

const checks = [
  { key: "library", ok: true, tr: "SAML kütüphanesi yüklü.", en: "The SAML library is installed." },
  { key: "metadata_signature", ok: false, tr: "Meta veri imzalı değil.", en: "The metadata is not signed.", detail: "unsigned" },
];

describe("checkFailureText", () => {
  it("returns the first failed check's sentence in the reader's language", () => {
    expect(checkFailureText({ discovery: { ok: false, checks } }, "tr")).toBe("Meta veri imzalı değil.");
    expect(checkFailureText({ discovery: { ok: false, checks } }, "en")).toBe("The metadata is not signed.");
  });
  it("returns null without a failed check (the row then shows the generic sentence)", () => {
    expect(checkFailureText({ discovery: { ok: true, checks: checks.slice(0, 1) } }, "tr")).toBeNull();
  });
});
