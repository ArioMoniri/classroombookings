import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});

// jsdom lacks these browser APIs used by Radix/base-ui and the grid.
if (typeof window !== "undefined") {
  if (!window.matchMedia) {
    window.matchMedia = (query: string): MediaQueryList => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    });
  }
  if (!window.ResizeObserver) {
    class ResizeObserverStub {
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    }
    window.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
  }
}
