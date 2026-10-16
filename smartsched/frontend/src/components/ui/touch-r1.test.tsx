// Flow-loop round 1, lane A (T-R1-01 / T-R1-04): the real phone touch offenders that lane G's T-R1-45 verdict
// confirmed, fixed in the primitives. jsdom has no layout or media queries, so these assert the class / CSS
// contract; scripts/record/lib/touch.mjs measured the real boxes on a stack.sh build (ROADMAP ledger).
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { LocaleToggle } from "@/components/shell/locale-toggle";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { fieldSize } from "@/components/ui/field-styles";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Select, SelectTrigger, SelectValue } from "@/components/ui/select";
import { I18nProvider } from "@/lib/i18n/provider";

describe("small fields are 44 px tall on touch (a native field has no ::after hit area)", () => {
  it("fieldSize.sm keeps 28/36 on the control scale but steps to the md height on coarse pointers", () => {
    expect(fieldSize.sm.split(" ")).toEqual(expect.arrayContaining(["h-(--control-h-sm)", "pointer-coarse:h-(--control-h-md)"]));
  });

  it("Input sm, NativeSelect sm and the Select trigger sm carry it", () => {
    render(
      <>
        <Input fieldSize="sm" aria-label="Ara" />
        <NativeSelect size="sm" aria-label="Grup">
          <option>A</option>
        </NativeSelect>
        <Select>
          <SelectTrigger size="sm" aria-label="Görünüm">
            <SelectValue />
          </SelectTrigger>
        </Select>
      </>,
    );
    expect(screen.getByRole("textbox", { name: "Ara" })).toHaveClass("pointer-coarse:h-(--control-h-md)");
    expect(screen.getByRole("combobox", { name: "Grup" })).toHaveClass("pointer-coarse:h-(--control-h-md)", "max-md:pointer-coarse:text-base");
    expect(screen.getByRole("combobox", { name: "Görünüm" })).toHaveClass("data-[size=sm]:pointer-coarse:h-(--control-h-md)");
  });
});

describe("menu rows", () => {
  it("dropdown items are at least 44 px tall on touch (user menu rows were 216 × 28)", async () => {
    render(
      <DropdownMenu>
        <DropdownMenuTrigger>Hesap</DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem>Profil</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Hesap" }));
    expect(await screen.findByRole("menuitem", { name: "Profil" })).toHaveClass("pointer-coarse:min-h-11");
  });
});

describe("language toggle", () => {
  it("each option is 44 px wide on touch, so the two hit areas do not overlap (kiosk locale buttons were 36 × 30)", () => {
    render(
      <I18nProvider initialLocale="tr">
        <LocaleToggle />
      </I18nProvider>,
    );
    for (const l of ["tr", "en"]) expect(screen.getByTestId(`locale-option-${l}`)).toHaveClass("pointer-coarse:min-w-11");
  });
});

describe("globals.css", () => {
  const css = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");
  it("native checkboxes and radios get the 44 × 44 ::after on coarse pointers, in the base layer", () => {
    const base = css.slice(css.indexOf("@layer base {"), css.indexOf("@layer utilities {"));
    expect(base).toContain('input:is([type="checkbox"], [type="radio"])::after');
    expect(base).toContain("inset: min(0px, calc(50% - 22px));");
  });
  it("a label row that wraps a native checkbox or radio is 44 px tall on touch (stacked move-scope radios)", () => {
    expect(css).toContain('label:has(> [data-slot="switch"], > [data-slot="checkbox"], > input[type="checkbox"], > input[type="radio"]) { min-height: 2.75rem; }');
  });
});
