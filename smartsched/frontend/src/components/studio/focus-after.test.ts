import { afterEach, describe, expect, it } from "vitest";
import { focusSoon, successorOf } from "./focus-after";

function list(n: number) {
  document.body.innerHTML = `<h3 id="heading" tabindex="-1">Rules</h3><ul>${Array.from({ length: n }, (_, i) => `<li><article id="c${i}" tabindex="-1" data-focus-card><button id="b${i}">x</button></article></li>`).join("")}</ul>`;
}
const flush = () => new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())));

describe("focus after confirm-and-remove (motion audit T4)", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("the successor is the next card, else the previous one, else none", () => {
    list(3);
    expect(successorOf(document.getElementById("b1"))?.id).toBe("c2");
    expect(successorOf(document.getElementById("b2"))?.id).toBe("c1");
    list(1);
    expect(successorOf(document.getElementById("b0"))).toBeNull();
  });

  it("focuses the successor after the removal renders, or the fallback when it is gone too", async () => {
    list(3);
    const next = successorOf(document.getElementById("b1"));
    (document.getElementById("b1") as HTMLElement).focus(); // the menu trigger got focus back
    const removed = document.getElementById("c1");
    focusSoon(next, "heading", removed);
    removed?.parentElement?.remove();
    await flush();
    expect(document.activeElement?.id).toBe("c2");

    list(1);
    const none = successorOf(document.getElementById("b0"));
    document.getElementById("c0")?.parentElement?.remove();
    focusSoon(none, "heading");
    await flush();
    expect(document.activeElement?.id).toBe("heading");
  });

  it("a trigger still inside the removed card does not count as a new place; another control does", async () => {
    list(3);
    (document.getElementById("b1") as HTMLElement).focus();
    focusSoon(successorOf(document.getElementById("b1")), "heading", document.getElementById("c1"));
    await flush();
    expect(document.activeElement?.id).toBe("c2"); // card c1 not removed yet, focus was inside it

    const other = document.getElementById("b0") as HTMLElement;
    focusSoon(successorOf(document.getElementById("b1")), "heading", document.getElementById("c1"));
    other.focus();
    await flush();
    expect(document.activeElement).toBe(other);
  });
});
