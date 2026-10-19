/**
 * Round-3 R3-M-06: focus `el` once the closing dialog / sheet has given focus back. A closing popup restores focus
 * to its trigger after its exit animation; when that trigger is gone (the publish button disappears once the run is
 * active) the focus lands on <body>, so the target is focused again after the animation if that happened.
 */
export function focusWhenSettled(get: () => HTMLElement | null): void {
  const go = () => {
    const el = get();
    const a = document.activeElement;
    if (el && document.contains(el) && (a === null || a === document.body || a === el || !document.contains(a))) el.focus();
  };
  window.requestAnimationFrame(() => {
    const el = get();
    if (el && document.contains(el)) el.focus();
  });
  for (const ms of [250, 600]) window.setTimeout(go, ms);
}
