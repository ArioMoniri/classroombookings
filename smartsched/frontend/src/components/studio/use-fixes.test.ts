import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api/endpoints";
import { fixScopeKey } from "./use-fixes";

afterEach(() => vi.unstubAllGlobals());

describe("pre-check fixes (Review follow-ups: version guard, applied.scope)", () => {
  it("sends the draft version the fix was chosen on, so a stale draft answers 409", async () => {
    const bodies: unknown[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
      bodies.push(JSON.parse(String(init?.body ?? "{}")));
      return new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } });
    }));
    await api.studio.applyFix(3, "COURSE", "item-1", "exclude", { version: 17 }).catch(() => undefined);
    expect(bodies[0]).toEqual({ item_id: "item-1", option: "exclude", version: 17, write_through: false, confirm: false });
  });

  it("names where the fix landed: this draft or the term's data", () => {
    expect(fixScopeKey({ scope: "draft" })).toBe("studio.check.scopeDraft");
    expect(fixScopeKey({ scope: "term" })).toBe("studio.check.scopeTerm");
    expect(fixScopeKey({})).toBe("studio.check.scopeDraft");
  });
});
