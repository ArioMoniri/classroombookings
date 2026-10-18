/**
 * E2EB-F11 (FIX-K): after a touch tap opens the class inspector, focus is on <main> or <body> (a tap does not focus
 * the chip). Move it to the inspector's heading so a screen reader lands there and Esc has a place to return from.
 * A mouse click keeps focus on the chip, which is left alone.
 */
export function focusInspectorIfLost(root: ParentNode = document): boolean {
  const active = document.activeElement as HTMLElement | null;
  const lost = !active || active === document.body || active.tagName === "MAIN";
  if (!lost) return false;
  const heading = root.querySelector<HTMLElement>('[data-testid="class-inspector"] [data-inspector-heading]');
  if (!heading) return false;
  heading.focus();
  return true;
}
