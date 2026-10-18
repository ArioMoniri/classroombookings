/**
 * HX-01: `feature_id` → route, anchor and permission. The server never sends a URL; the client maps every id it may
 * receive (features.yaml, HB-01) through this table.
 */
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { generate, FEATURES_PATH, OUT_PATH, parseFeatures } from "../../../scripts/gen-helper-features.mjs";
import { ADMIN_NAV_ITEMS, ADMIN_SECTION_NAV_ITEMS } from "@/components/admin/nav-items";
import { NAV_GROUPS } from "@/components/shell/nav-config";
import { FEATURE_INDEX } from "./feature-index.gen";
import { canOpenFeature, dataHitHref, featureById, featureHref, featureTitle, pathLine } from "./feature-links";

const ROOT = resolve(__dirname, "../../..");
const yaml = readFileSync(FEATURES_PATH, "utf8");
const docs = ["../../docs/design/v3/welcome-guide.md", "../../docs/design/v3/helper.md"].map((p) => readFileSync(resolve(ROOT, p), "utf8")).join("\n");

/** `/admin/users#x` → is there an app page for `/admin/users`? (route groups and dynamic segments allowed) */
function pageExists(route: string): boolean {
  const path = route.split(/[?#]/)[0]!.replace(/^\//, "");
  return existsSync(resolve(ROOT, "src/app/(app)", path, "page.tsx")) || existsSync(resolve(ROOT, "src/app", path, "page.tsx"));
}

const asSet = (p: string | string[] | undefined) => [...new Set(p === undefined ? [] : Array.isArray(p) ? p : [p])].sort();

describe("feature links", () => {
  it("are generated from the current features.yaml", () => {
    expect(readFileSync(OUT_PATH, "utf8")).toBe(generate(yaml));
    expect(FEATURE_INDEX.length).toBe((yaml.match(/^- id:/gm) ?? []).length);
    expect(parseFeatures(yaml).find((e: { id: string }) => e.id === "profile.helper_memory")?.title.tr).toBe("Yardımcı neleri hatırlıyor?");
  });

  it("every feature_id maps to an existing route", () => {
    const missing = FEATURE_INDEX.filter((e) => !pageExists(e.route)).map((e) => `${e.id} → ${e.route}`);
    expect(missing).toEqual([]);
    for (const e of FEATURE_INDEX) expect(featureHref(e.id)).toBe(e.route);
  });

  it("every anchor is a welcome-guide §13 or helper §3.4 anchor", () => {
    const unknown = FEATURE_INDEX.filter((e) => e.anchor && !docs.includes(e.anchor)).map((e) => `${e.id}: ${e.anchor}`);
    expect(unknown).toEqual([]);
  });

  it("every nav-config and admin nav href has an index entry with the same permission (nav-index test)", () => {
    const items = [...NAV_GROUPS.flatMap((g) => g.items), ...ADMIN_NAV_ITEMS, ...ADMIN_SECTION_NAV_ITEMS];
    const problems: string[] = [];
    for (const item of items) {
      const path = item.href.split(/[?#]/)[0];
      const entries = FEATURE_INDEX.filter((e) => e.route.split("#")[0] === path && (e.kind === "page" || e.kind === "setting"));
      if (!entries.length) problems.push(`${item.href}: no index entry`);
      else if (!entries.some((e) => JSON.stringify(asSet(e.permission)) === JSON.stringify(asSet(item.permission)))) problems.push(`${item.href}: permission ${asSet(item.permission).join("|")} vs ${entries.map((e) => e.permission.join("|")).join(" / ")}`);
    }
    expect(problems).toEqual([]);
  });

  it("unknown ids map to nothing (no route is guessed)", () => {
    expect(featureById("nope")).toBeUndefined();
    expect(featureHref("nope")).toBeNull();
    expect(featureHref("https://evil.example")).toBeNull();
  });

  it("filters by permission (any-of) and hideWith, like the nav", () => {
    const can = (perms: string[]) => (p: string | readonly string[] | undefined) => !p || (Array.isArray(p) ? p : [p]).some((x) => perms.includes(x as string));
    const invite = featureById("admin.users.invite")!;
    expect(canOpenFeature(invite, can(["book_single.create"]))).toBe(false);
    expect(canOpenFeature(invite, can(["setup.users"]))).toBe(true);
    const mine = featureById("my_requests")!;
    expect(canOpenFeature(mine, can(["book_single.create"]))).toBe(true);
    expect(canOpenFeature(mine, can(["book_single.create", "planning.view"]))).toBe(false);
    expect(canOpenFeature(featureById("profile")!, can([]))).toBe(true);
  });

  it("titles and path lines come from the index in the reader's language", () => {
    expect(featureTitle("admin.holidays", "tr")).toBe("Tatiller");
    expect(featureTitle("admin.holidays", "en")).toBe("Holidays");
    expect(pathLine({ tr: ["Yönetim", "Kullanıcılar"], en: ["Admin", "Users"] }, "tr")).toBe("Yönetim › Kullanıcılar");
  });

  it("data hits open the same places as the palette", () => {
    expect(dataHitHref({ kind: "room", id: 12, label: "A 204" })).toBe("/bookings?display=room&room=12");
    expect(dataHitHref({ kind: "course", id: 3, label: "PHAR 240" })).toBe("/requests?q=PHAR%20240");
    expect(dataHitHref({ kind: "instructor", id: 9, label: "A. T." })).toBe("/timetable?subject=instructor:9");
    expect(dataHitHref({ kind: "program", id: 4, label: "Eczacılık" })).toBe("/requests?program_id=4");
    expect(dataHitHref({ kind: "weird", id: 1, label: "x" })).toBeNull();
  });
});
