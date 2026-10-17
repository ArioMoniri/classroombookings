/**
 * Flow loop round 3, lane F follow-up (loop-r3-laneF-2026-10-17): the admin phone residue of R3-M-08 / R2-S-08.
 *
 * - Every small Button in lane F's screens (admin/**, audit/**, settings/** except settings-view.tsx) steps to
 *   44 px on coarse pointers: `size="sm"` carries `pointer-coarse:h-11`, `size="icon-sm"` `pointer-coarse:size-11`
 *   ("webhook-new" 130×36, "Okundu say" 99×36, "Yükle" 81×36, session-edit / -delete 36 px on the phone crawl).
 * - MOBILE.md M-05: /admin/roles keeps "Kaydet" in the page-actions capsule while the editor is open below lg (with
 *   "Yeni rol"), and the rooms Özellikler tab puts "Yeni özellik" in the same capsule as "Yeni derslik".
 * - The English CHANGELOG on Kurum ayarları is not in the DOM until the Turkish summary is opened (the round-3 EN
 *   scan read the text of the closed <details>).
 * jsdom has no layout: source contracts plus one render, like settings-solver-touch.test.tsx.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

const data = vi.hoisted(() => ({
  changelog: { entries: [{ version: "0.9.0", date: "2026-10-01", sections: { Added: ["Roles with permission sets and booking limits."] } }], latest: "0.9.0", viewed_at: null, unread: true },
}));
vi.mock("next/navigation", () => ({ usePathname: () => "/admin/settings", useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }), useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/api/crbs", async (orig) => ({ ...(await orig<typeof import("@/lib/api/crbs")>()), useChangelog: () => ({ data: data.changelog, isLoading: false }) }));

import { WhatsNewPanel } from "./whats-new";

const ROOT = join(process.cwd(), "src/components");
const read = (rel: string) => readFileSync(join(ROOT, rel), "utf8");

/** the JSX opening tags of `<Button …>` (brace-aware: `onClick={() => …}` holds a ">") */
function buttonTags(src: string): { line: number; tag: string }[] {
  const out: { line: number; tag: string }[] = [];
  let i = 0;
  for (;;) {
    i = src.indexOf("<Button", i);
    if (i < 0) return out;
    if (!/[\s>]/.test(src[i + 7] ?? "x")) {
      i += 1;
      continue;
    }
    let depth = 0;
    let j = i;
    for (; j < src.length; j++) {
      const c = src[j];
      if (c === "{") depth++;
      else if (c === "}") depth--;
      else if (c === ">" && depth === 0) break;
    }
    out.push({ line: src.slice(0, i).split("\n").length, tag: src.slice(i, j + 1) });
    i = j;
  }
}

const laneFiles = [
  ...readdirSync(join(ROOT, "admin")).filter((f) => f.endsWith(".tsx") && !f.includes(".test.") && !["kit.tsx", "reset-password.tsx", "profile-view.tsx"].includes(f)).map((f) => `admin/${f}`),
  ...readdirSync(join(ROOT, "audit")).filter((f) => f.endsWith(".tsx") && !f.includes(".test.")).map((f) => `audit/${f}`),
  ...readdirSync(join(ROOT, "settings")).filter((f) => f.endsWith(".tsx") && !f.includes(".test.") && f !== "settings-view.tsx").map((f) => `settings/${f}`),
];

describe("small buttons are 44 px on touch (R3-M-08, R2-S-08)", () => {
  it("the scanner reads multi-line tags with arrow functions", () => {
    const tags = buttonTags(`<Button size="sm" onClick={() => go(a > b)}\n  className="x">Go</Button><ButtonGroup/>`);
    expect(tags).toHaveLength(1);
    expect(tags[0]!.tag).toContain('className="x"');
  });
  it("every size=sm / icon-sm Button in lane F's screens steps up on coarse pointers", () => {
    const bad: string[] = [];
    for (const file of laneFiles) {
      for (const { line, tag } of buttonTags(read(file))) {
        if (/size="sm"/.test(tag) && !/pointer-coarse:(min-)?h-11/.test(tag)) bad.push(`${file}:${line} sm`);
        if (/size="icon-sm"/.test(tag) && !/pointer-coarse:size-(11|\(--control-h-md\))/.test(tag)) bad.push(`${file}:${line} icon-sm`);
      }
    }
    expect(laneFiles.length).toBeGreaterThan(20);
    expect(bad).toEqual([]);
  });
});

describe("primary actions in thumb reach below lg (MOBILE.md M-05)", () => {
  it("/admin/roles: Kaydet sits in the page-actions capsule while the editor is open on compact screens", () => {
    const src = read("admin/roles-admin.tsx");
    expect(src).toContain("useIsCompact");
    // the page header keeps its capsule only when the editor is not showing its own
    expect(src).toMatch(/actions=\{compact \? undefined : newRole\}/);
    // the editor's capsule: "Yeni rol" (outline) then the save button
    expect(src).toMatch(/<div data-slot="page-actions" className=\{pageActionsCapsule\} data-testid="role-actions">\s*\{phoneActions\}\s*\{saveButton\}/);
  });
  it("/admin/rooms Özellikler: Yeni özellik is in the capsule like Yeni derslik", () => {
    const src = read("admin/features-admin.tsx");
    expect(src).toMatch(/<div data-slot="page-actions" className=\{pageActionsCapsule\}>\s*<Button onClick=\{\(\) => setEditing\("new"\)\} data-testid="feature-new">/);
  });
});

describe("Kurum ayarları › Yenilikler (R3 EN scan)", () => {
  it("renders no English changelog text until the summary is opened", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <I18nProvider initialLocale="tr">
          <WhatsNewPanel />
        </I18nProvider>
      </QueryClientProvider>,
    );
    const details = screen.getByTestId("news-english") as HTMLDetailsElement;
    expect(details.textContent).not.toContain("Roles with permission sets");
    expect(details.querySelector('[lang="en"]')).toBeNull();
    details.open = true;
    fireEvent(details, new Event("toggle"));
    expect(details.querySelector('[lang="en"]')).toHaveTextContent("Roles with permission sets");
    // "Okundu say" is a 44 px button on touch
    expect(screen.getByRole("button", { name: "Okundu say" })).toHaveClass("pointer-coarse:h-11");
  });
});
