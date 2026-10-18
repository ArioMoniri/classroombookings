/** HX-07 (helper.md §3.3): Göster = navigate, wait for the anchor, ring it, one step card; Esc ends on the target. */
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useHelperStore } from "./helper-store";
import { ShowMeHost } from "./show-me";
import { renderHelper, resetHelperStore } from "./test-helpers";

const push = vi.fn();
let pathname = "/bookings";
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), usePathname: () => pathname }));

function media(desktop: boolean) {
  window.matchMedia = ((q: string) => ({ matches: q.includes("min-width: 1024px") ? desktop : q.includes("reduce") ? false : false, media: q, onchange: null, addListener: () => undefined, removeListener: () => undefined, addEventListener: () => undefined, removeEventListener: () => undefined, dispatchEvent: () => false })) as unknown as typeof window.matchMedia;
}

beforeEach(() => {
  resetHelperStore();
  push.mockReset();
  pathname = "/bookings";
  Element.prototype.scrollIntoView = vi.fn();
  // jsdom has no layout: give every element a box so the anchor counts as visible
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({ x: 10, y: 10, left: 10, top: 10, width: 120, height: 40, right: 130, bottom: 50, toJSON: () => ({}) } as DOMRect);
  media(true);
});

describe("Göster", () => {
  it("navigates, rings the control and ends with the focus on it (Esc)", async () => {
    renderHelper(
      <>
        <button type="button" data-tour="admin-holidays-add">Tatil ekle</button>
        <ShowMeHost />
      </>,
    );
    act(() => useHelperStore.getState().startShowMe("admin.holidays", false));
    expect(push).toHaveBeenCalledWith("/admin/holidays");
    expect(await screen.findByTestId("helper-step")).toHaveTextContent("Tatiller");
    expect(await screen.findByTestId("tour-ring")).toBeInTheDocument();
    const target = screen.getByText("Tatil ekle");
    expect(target.getAttribute("aria-describedby")).toBeTruthy();
    expect(target).toBeEnabled();
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(useHelperStore.getState().showMe).toBeNull());
    expect(document.activeElement).toBe(target);
    expect(target).not.toHaveAttribute("aria-describedby");
  });

  it("Yardımcıya dön reopens the sheet with the thread", async () => {
    renderHelper(
      <>
        <button type="button" data-tour="admin-holidays-add">Tatil ekle</button>
        <ShowMeHost />
      </>,
    );
    act(() => {
      useHelperStore.getState().pushUser("Tatil nerede eklenir?");
      useHelperStore.getState().startShowMe("admin.holidays", true);
    });
    fireEvent.click(await screen.findByTestId("helper-step-back"));
    expect(useHelperStore.getState().open).toBe(true);
    expect(useHelperStore.getState().entries).toHaveLength(1);
  });

  it("HX-18 M1: a target under the open desktop sheet moves the sheet aside; Yardımcıya dön brings it back", async () => {
    const rect = (left: number, width: number) => ({ x: left, y: 80, left, top: 80, width, height: 40, right: left + width, bottom: 120, toJSON: () => ({}) }) as DOMRect;
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
      return this.hasAttribute("data-helper-sheet") ? rect(1040, 400) : rect(1300, 100);
    });
    renderHelper(
      <>
        <button type="button" data-tour="admin-holidays-add">Tatil ekle</button>
        <div data-helper-sheet="" />
        <ShowMeHost />
      </>,
    );
    act(() => {
      useHelperStore.getState().openSheet();
      useHelperStore.getState().startShowMe("admin.holidays", false);
    });
    expect(await screen.findByTestId("tour-ring")).toBeInTheDocument();
    expect(useHelperStore.getState().open).toBe(false);
    expect(useHelperStore.getState().showMe?.reopen).toBe(true);
    fireEvent.click(screen.getByTestId("helper-step-back"));
    expect(useHelperStore.getState().open).toBe(true);
  });

  it("HX-18 M1: a target clear of the sheet keeps the sheet open", async () => {
    const rect = (left: number, width: number) => ({ x: left, y: 80, left, top: 80, width, height: 40, right: left + width, bottom: 120, toJSON: () => ({}) }) as DOMRect;
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
      return this.hasAttribute("data-helper-sheet") ? rect(1040, 400) : rect(200, 100);
    });
    renderHelper(
      <>
        <button type="button" data-tour="admin-holidays-add">Tatil ekle</button>
        <div data-helper-sheet="" />
        <ShowMeHost />
      </>,
    );
    act(() => {
      useHelperStore.getState().openSheet();
      useHelperStore.getState().startShowMe("admin.holidays", false);
    });
    expect(await screen.findByTestId("tour-ring")).toBeInTheDocument();
    expect(useHelperStore.getState().open).toBe(true);
  });

  it("HX-18 m12: on a phone the target scrolls to the upper half (block start), not under the docked card", async () => {
    media(false);
    renderHelper(
      <>
        <button type="button" data-tour="admin-holidays-add">Tatil ekle</button>
        <ShowMeHost />
      </>,
    );
    act(() => useHelperStore.getState().startShowMe("admin.holidays", true));
    expect(await screen.findByTestId("tour-ring")).toBeInTheDocument();
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith(expect.objectContaining({ block: "start" }));
    expect(screen.getByText("Tatil ekle").style.scrollMarginTop).not.toBe("");
  });

  it("a missing anchor shows the path and says the button is not on the page", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderHelper(<ShowMeHost />);
    act(() => useHelperStore.getState().startShowMe("admin.users.invite", false));
    await act(async () => {
      vi.advanceTimersByTime(3200);
    });
    expect(await screen.findByTestId("helper-step-missing")).toHaveTextContent("Bu düğme şu an bu sayfada görünmüyor.");
    expect(screen.getByTestId("helper-step")).toHaveTextContent("Kurulum › Kullanıcılar › Davet et");
    expect(screen.queryByTestId("tour-ring")).toBeNull();
    vi.useRealTimers();
  });
});
