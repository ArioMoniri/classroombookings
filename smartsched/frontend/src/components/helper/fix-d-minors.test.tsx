/**
 * FIX-D minors of docs/testing/round4/2026-10-18-hb18.md:
 * - HB18-F09: "Yardımcıya dön" after Göster reopens Rehber modu with the query the person had typed;
 * - HB18-F14: opening the sheet ends a running Göster (its step card no longer covers the sheet or takes its focus).
 */
import { act, fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { helperApi } from "@/lib/api/helper";
import { GuideMode } from "./guide";
import { useHelperStore } from "./helper-store";
import { makeHost, renderHelper, resetHelperStore } from "./test-helpers";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/reserve" }));

beforeEach(() => {
  resetHelperStore();
  vi.spyOn(helperApi, "search").mockResolvedValue({ pages: [], where: [], data: {} } as never);
});

describe("HB18-F09: the guide keeps its query across Göster", () => {
  it("a remounted guide shows what was typed", () => {
    const first = renderHelper(<GuideMode />, { host: makeHost() });
    fireEvent.change(screen.getByTestId("helper-guide-input"), { target: { value: "davet" } });
    first.unmount();
    renderHelper(<GuideMode />, { host: makeHost() });
    expect(screen.getByTestId("helper-guide-input")).toHaveValue("davet");
  });

  it("a seed from the palette still wins", () => {
    useHelperStore.setState({ guideText: "eski" });
    renderHelper(<GuideMode seed="takvim" />, { host: makeHost() });
    expect(screen.getByTestId("helper-guide-input")).toHaveValue("takvim");
  });
});

describe("HB18-F14: opening the sheet ends Göster", () => {
  it("openSheet() clears a running show-me", () => {
    act(() => useHelperStore.getState().startShowMe("admin.holidays", false));
    expect(useHelperStore.getState().showMe).not.toBeNull();
    act(() => useHelperStore.getState().openSheet());
    expect(useHelperStore.getState().showMe).toBeNull();
    expect(useHelperStore.getState().open).toBe(true);
  });
});
