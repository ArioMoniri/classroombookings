import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Button, IconButton } from "@/components/ui/button";
import { formatDateField, parseDateField } from "@/components/ui/date-field";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { LoadingValue } from "@/components/ui/skeleton";

describe("SegmentedControl", () => {
  function Harness({ semantics }: { semantics?: "tablist" | "radiogroup" }) {
    const [v, setV] = useState<"a" | "b" | "c">("a");
    return (
      <SegmentedControl
        aria-label="Horizon"
        semantics={semantics}
        value={v}
        onValueChange={setV}
        options={[
          { value: "a", label: "Bir hafta" },
          { value: "b", label: "Bir ay" },
          { value: "c", label: "Tüm dönem" },
        ]}
      />
    );
  }

  it("is a tablist with roving focus and arrow keys; the CSS thumb sits on the selected segment", async () => {
    const { container } = render(<Harness />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.getAttribute("tabindex"))).toEqual(["0", "-1", "-1"]);
    tabs[0].focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Bir ay" })).toHaveAttribute("aria-selected", "true");
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "Bir ay" }));
    await userEvent.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "Tüm dönem" })).toHaveAttribute("aria-selected", "true");
    const thumb = container.querySelector<HTMLElement>("[data-slot=segmented-thumb]")!;
    expect(thumb.style.transform).toBe("translateX(200%)");
    // no motion layout projection at rest: one static element, transform only
    expect(container.querySelectorAll("[data-slot=segmented-thumb]")).toHaveLength(1);
  });

  it("radiogroup semantics for form values, and a select fallback with the same options", () => {
    render(<Harness semantics="radiogroup" />);
    expect(screen.getByRole("radiogroup", { name: "Horizon" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Bir hafta" })).toHaveAttribute("aria-checked", "true");
    const fallback = screen.getByRole("combobox", { name: "Horizon" }) as HTMLSelectElement;
    expect([...fallback.options].map((o) => o.text)).toEqual(["Bir hafta", "Bir ay", "Tüm dönem"]);
  });

  it("the track never wraps: one grid row with equal columns", () => {
    render(<Harness />);
    const track = screen.getByRole("tablist");
    expect(track.className).toMatch(/grid-flow-col/);
    expect(track.className).toMatch(/auto-cols-fr/);
    expect(track.className).toMatch(/whitespace-nowrap/);
    expect(track.className).toMatch(/min-w-max/);
  });
});

describe("Button / IconButton", () => {
  it("reads the control-height tokens and supports pill and rect shapes", () => {
    render(
      <>
        <Button size="sm" shape="rect">Kaydet</Button>
        <Button>Oluştur</Button>
      </>,
    );
    const sm = screen.getByRole("button", { name: "Kaydet" });
    expect(sm.className).toMatch(/h-\(--control-h-sm\)/);
    expect(sm.className).toMatch(/rounded-lg/);
    const md = screen.getByRole("button", { name: "Oluştur" });
    expect(md.className).toMatch(/h-\(--control-h-md\)/);
    expect(md.className).toMatch(/rounded-full/);
    expect(md.className).not.toMatch(/outline-none/);
  });

  it("IconButton requires a label and exposes it as the accessible name", () => {
    render(
      <IconButton label="Önceki hafta" size="sm">
        <svg />
      </IconButton>,
    );
    expect(screen.getByRole("button", { name: "Önceki hafta" })).toHaveAttribute("title", "Önceki hafta");
  });
});

describe("DateField format", () => {
  it("formats ISO in the Turkish order and parses typed input back", () => {
    expect(formatDateField("2026-10-15", "tr-TR")).toBe("15.10.2026");
    expect(parseDateField("15.10.2026", "tr-TR")).toBe("2026-10-15");
    expect(parseDateField("1.2.26", "tr-TR")).toBe("2026-02-01");
    expect(parseDateField("31.02.2026", "tr-TR")).toBeNull();
  });
  it("uses month/day/year for en-US", () => {
    expect(formatDateField("2026-10-15", "en-US")).toBe("10/15/2026");
    expect(parseDateField("10/15/2026", "en-US")).toBe("2026-10-15");
    expect(parseDateField("2026-10-15", "en-US")).toBe("2026-10-15");
  });
});

describe("LoadingValue", () => {
  it("undefined renders a skeleton, never 0; null renders the empty text", () => {
    const fmt = vi.fn((n: number) => `${n} ders`);
    const { rerender, container } = render(<LoadingValue value={undefined as number | undefined} format={fmt} loadingLabel="Yükleniyor" />);
    expect(container.textContent).toBe("Yükleniyor");
    expect(container.querySelector("[data-loading=true]")).not.toBeNull();
    expect(fmt).not.toHaveBeenCalled();
    rerender(<LoadingValue value={null as number | null} format={fmt} />);
    expect(container.textContent).toBe("—");
    rerender(<LoadingValue value={0} format={fmt} />);
    expect(container.textContent).toBe("0 ders");
  });
});
