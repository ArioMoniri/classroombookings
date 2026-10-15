import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { revealRule, VirtualRuleList } from "./virtual-rule-list";

const items = Array.from({ length: 300 }, (_, i) => ({ id: i + 1 }));

describe("VirtualRuleList (Studio backlog: rule list virtualisation above 40 cards)", () => {
  // jsdom lays nothing out: give every card a real card height so the virtualiser can measure
  beforeEach(() => {
    vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockImplementation(function (this: HTMLElement) {
      return this.tagName === "LI" ? 112 : 0;
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it("renders only a window of the cards, with the full height reserved", () => {
    render(<VirtualRuleList items={items} domIdOf={(r) => `rule-${r.id}`}>{(r) => <article id={`rule-${r.id}`}>Rule {r.id}</article>}</VirtualRuleList>);
    const list = document.querySelector("[data-virtual]") as HTMLElement;
    expect(list.dataset.count).toBe("300");
    expect(screen.queryAllByRole("article").length).toBeLessThan(60);
    expect(parseInt(list.style.height, 10)).toBeGreaterThan(300 * 50);
  });

  it("revealRule scrolls a card that is not rendered into view", () => {
    const scroll = vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
    render(<VirtualRuleList items={items} domIdOf={(r) => `rule-${r.id}`}>{(r) => <article id={`rule-${r.id}`}>Rule {r.id}</article>}</VirtualRuleList>);
    expect(document.getElementById("rule-250")).toBeNull();
    act(() => revealRule("rule-250"));
    expect(scroll).toHaveBeenCalled();
  });
});
