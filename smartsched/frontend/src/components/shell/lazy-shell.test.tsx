/**
 * F-CH-1 (fix-c-2026-10-18): the shell's heavy parts are not in the (app) layout's first load. The command palette
 * (cmdk, the helper's palette groups), the shortcuts sheet and the helper sheet are fetched when the person opens
 * them; the welcome guide and the privacy notice gate are fetched after hydration (next/dynamic, no SSR).
 */
import { act, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import path from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";

const read = (rel: string) => readFileSync(path.resolve(import.meta.dirname, "..", rel), "utf8");
const staticImports = (text: string) => [...text.matchAll(/^import\s+(?!type\b)[^;]*?from\s+"([^"]+)"/gm)].map((m) => m[1]);

describe("shell: lazy parts are not static imports", () => {
  it("app-shell imports the palette, shortcuts, welcome and privacy gate lazily", () => {
    const deps = staticImports(read("shell/app-shell.tsx"));
    expect(deps).not.toContain("./command-palette");
    expect(deps).not.toContain("./shortcuts-sheet");
    expect(deps).not.toContain("@/components/privacy/notice-gate");
    expect(deps).not.toContain("@/components/welcome");
    expect(deps).toContain("./lazy-shell");
  });

  it("the welcome barrel no longer drags the provider and the page slot into every importer", () => {
    const barrel = read("welcome/index.ts");
    expect(barrel).not.toMatch(/WelcomeProvider/);
    expect(barrel).not.toMatch(/WelcomePageSlot/);
  });

  it("the bell and the palette take the run status helpers without the runs page (its data table)", () => {
    expect(staticImports(read("notifications/notification-bell.tsx"))).not.toContain("@/components/runs/runs-list");
    expect(staticImports(read("shell/command-palette.tsx"))).not.toContain("@/components/runs/runs-list");
  });

  it("the helper root loads the sheet and the spotlight on demand", () => {
    const deps = staticImports(read("helper/helper-root.tsx"));
    expect(deps).not.toContain("./helper-sheet");
    expect(deps).not.toContain("./show-me");
  });
});

const loaded = vi.hoisted(() => ({ palette: 0, shortcuts: 0 }));
vi.mock("./command-palette", () => {
  loaded.palette += 1;
  return { CommandPalette: () => <div role="dialog" aria-label="palette" /> };
});
vi.mock("./shortcuts-sheet", () => {
  loaded.shortcuts += 1;
  return { ShortcutsSheet: () => <div role="dialog" aria-label="shortcuts" /> };
});

describe("shell: the palette and the shortcuts sheet load on first open", () => {
  beforeEach(async () => {
    const { useUiStore } = await import("@/stores/ui");
    useUiStore.setState({ paletteOpen: false, shortcutsOpen: false });
  });

  it("nothing is fetched until ⌘K / ? opens them; then they stay mounted", async () => {
    const { LazyCommandPalette, LazyShortcutsSheet } = await import("./lazy-shell");
    const { useUiStore } = await import("@/stores/ui");
    render(
      <>
        <LazyCommandPalette />
        <LazyShortcutsSheet />
      </>,
    );
    await act(async () => undefined);
    expect(loaded.palette).toBe(0);
    expect(loaded.shortcuts).toBe(0);
    act(() => useUiStore.getState().setPaletteOpen(true));
    expect(await screen.findByRole("dialog", { name: "palette" })).toBeInTheDocument();
    expect(loaded.palette).toBe(1);
    expect(loaded.shortcuts).toBe(0);
    act(() => useUiStore.getState().setPaletteOpen(false));
    // kept mounted for its close animation and the next open
    expect(screen.getByRole("dialog", { name: "palette" })).toBeInTheDocument();
    act(() => useUiStore.getState().setShortcutsOpen(true));
    expect(await screen.findByRole("dialog", { name: "shortcuts" })).toBeInTheDocument();
    expect(loaded.shortcuts).toBe(1);
  });
});
