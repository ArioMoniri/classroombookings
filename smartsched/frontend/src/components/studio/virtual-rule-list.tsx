"use client";

/**
 * Rule lists above 40 cards render only the cards near the viewport (Studio backlog; motion_designer §4: long
 * lists animate only rows in view). The page scrolls the window, so this is a window virtualiser whose
 * `scrollMargin` is the list's own offset; cards have variable height, measured as they mount.
 * A card that is not rendered can still be revealed: `revealRule(domId)` scrolls its index into view.
 */
import { useWindowVirtualizer } from "@tanstack/react-virtual";
import { useEffect, useRef, useState, type ReactNode } from "react";

export const VIRTUAL_MIN = 40;
const REVEAL = "studio:reveal-rule";

/** Ask a virtual list to bring `domId` into view; resolves to the element once it is rendered. */
export function revealRule(domId: string): void {
  window.dispatchEvent(new CustomEvent<string>(REVEAL, { detail: domId }));
}

export function VirtualRuleList<T>({ items, domIdOf, estimate = 112, children }: { items: readonly T[]; domIdOf: (item: T) => string; estimate?: number; children: (item: T) => ReactNode }) {
  const ref = useRef<HTMLUListElement>(null);
  const [margin, setMargin] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // the list moves when content above it changes (tray, filters): re-read its document offset then
    const ro = new ResizeObserver(() => setMargin(el.getBoundingClientRect().top + window.scrollY));
    ro.observe(el);
    ro.observe(document.body);
    return () => ro.disconnect();
  }, []);
  const v = useWindowVirtualizer({ count: items.length, estimateSize: () => estimate, overscan: 6, scrollMargin: margin, getItemKey: (i) => domIdOf(items[i] as T) });
  useEffect(() => {
    const onReveal = (e: Event) => {
      const id = (e as CustomEvent<string>).detail;
      const index = items.findIndex((x) => domIdOf(x) === id);
      if (index < 0) return;
      v.scrollToIndex(index, { align: "center" });
    };
    window.addEventListener(REVEAL, onReveal);
    return () => window.removeEventListener(REVEAL, onReveal);
  }, [items, domIdOf, v]);
  return (
    <ul ref={ref} className="relative" style={{ height: v.getTotalSize() }} data-virtual="" data-count={items.length}>
      {v.getVirtualItems().map((vi) => (
        <li key={vi.key} data-index={vi.index} ref={v.measureElement} className="absolute top-0 left-0 w-full pb-2" style={{ transform: `translateY(${vi.start - v.options.scrollMargin}px)` }}>
          {children(items[vi.index] as T)}
        </li>
      ))}
    </ul>
  );
}
