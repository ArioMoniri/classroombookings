/**
 * Focus after confirm-and-remove (motion audit 2026-10-15 T4, motion_designer §8 "focus never lost"):
 * when the control that triggered a removal (a card's menu, "Remove pin") disappears with its card, focus
 * moves to the neighbouring card, or to the list heading when the list is empty. Pick the successor before
 * the removal and focus it after the next render.
 */

const CARD = "[data-focus-card]";

/** The card to focus once the card containing `el` is gone: the next one, else the previous one. */
export function successorOf(el: Element | null): HTMLElement | null {
  const card = el?.closest(CARD);
  if (!card) return null;
  const item = card.closest("li") ?? card;
  const pick = (sib: Element | null): HTMLElement | null => (sib ? ((sib.matches(CARD) ? sib : sib.querySelector(CARD)) as HTMLElement | null) : null);
  return pick(item.nextElementSibling) ?? pick(item.previousElementSibling);
}

/**
 * Focus `target` after two frames (the removal's re-render and layout), or `fallbackId` if it left the DOM.
 * Moves focus only when it is lost: on <body>, on a node that left the DOM, or still inside `from` (the card
 * being removed, whose menu trigger gets focus back first). A user who moved on elsewhere keeps their place.
 */
export function focusSoon(target: HTMLElement | null, fallbackId?: string, from?: Element | null): void {
  requestAnimationFrame(() =>
    requestAnimationFrame(() => {
      const now = document.activeElement;
      const lost = !now || now === document.body || !now.isConnected || (from ? from.contains(now) : false);
      if (!lost) return;
      const el = target?.isConnected ? target : fallbackId ? document.getElementById(fallbackId) : null;
      el?.focus();
    }),
  );
}
