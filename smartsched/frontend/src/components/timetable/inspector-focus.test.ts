// E2EB-F11 (FIX-K): a touch tap on a class chip leaves focus on <main>/<body>; the opened inspector's heading takes it.
import { afterEach, describe, expect, it } from "vitest";
import { focusInspectorIfLost } from "./inspector-focus";

afterEach(() => (document.body.innerHTML = ""));

describe("focusInspectorIfLost", () => {
  it("focuses the inspector heading when focus sits on <main>", () => {
    document.body.innerHTML = '<main tabindex="-1"></main><aside data-testid="class-inspector"><h2 tabindex="-1" data-inspector-heading>ACU 1421</h2></aside>';
    document.querySelector<HTMLElement>("main")!.focus();
    expect(focusInspectorIfLost()).toBe(true);
    expect(document.activeElement?.textContent).toBe("ACU 1421");
  });

  it("leaves focus on the chip after a mouse click", () => {
    document.body.innerHTML = '<button data-testid="calendar-event">chip</button><aside data-testid="class-inspector"><h2 tabindex="-1" data-inspector-heading>X</h2></aside>';
    document.querySelector<HTMLElement>("button")!.focus();
    expect(focusInspectorIfLost()).toBe(false);
    expect(document.activeElement?.textContent).toBe("chip");
  });
});
