/** Flow-loop round 2, sweeper 3 (item 5, MOBILE M-05 on /admin/users, /admin/roles, /admin/departments, /admin/audit):
 * the PageTitle actions are a capsule fixed above the tab bar below `lg` (the same pattern as find-room's "Ara" and
 * My bookings' bulk cancel: bottom = --shell-bottom-h + 0.75rem, glass-chrome, z-20), unchanged on desktop; the shell's
 * <main> pads for it (globals.css) so the last card is never covered. jsdom has no layout: this pins the class contract. */
import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { PageTitle } from "./kit";

const css = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");

describe("sweeper 3 / M-05: PageTitle actions capsule", () => {
  it("fixes the actions above the tab bar below lg and keeps the desktop header row", () => {
    render(<PageTitle title="Kullanıcılar" actions={<button type="button">Yeni kullanıcı</button>} />);
    const wrap = screen.getByRole("button", { name: "Yeni kullanıcı" }).parentElement!;
    expect(wrap).toHaveAttribute("data-slot", "page-actions");
    expect(wrap).toHaveClass(
      "flex",
      "max-lg:fixed",
      "max-lg:inset-x-4",
      "max-lg:bottom-[calc(var(--shell-bottom-h)+0.75rem)]",
      "max-lg:z-20",
      "max-lg:justify-end",
      "max-lg:rounded-2xl",
      "max-lg:glass-chrome",
      "max-lg:p-1.5",
      "max-lg:shadow-elev-2",
    );
    expect(wrap.className).not.toMatch(/(^|\s)fixed(\s|$)/);
  });
  it("renders no capsule without actions", () => {
    render(<PageTitle title="Derslikler" subtitle="Lead" />);
    expect(document.querySelector('[data-slot="page-actions"]')).toBeNull();
  });
  it("the shell's main pads for the capsule below lg (globals.css)", () => {
    expect(css).toMatch(/main:has\(\[data-slot="page-actions"\]\)\s*\{[^}]*padding-bottom:\s*calc\(var\(--shell-bottom-h\)/);
  });
});
