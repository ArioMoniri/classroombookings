/**
 * Puts a transcript into the text box the user would type in (research §3.7 "Result"): at the caret (replacing a
 * selection), with a space on either side when needed, then selects the inserted words so a wrong one is fixed by
 * typing over it. The value is set through the element's native setter and an `input` event, so a React-controlled
 * field (its `onChange`) sees exactly what a keystroke would give — the mic never needs the field's state setter.
 * Focus stays in the box. Nothing is sent.
 */

export type VoiceField = HTMLTextAreaElement | HTMLInputElement;

/** Marks the `input` event this module dispatches, so the "Sesle girildi" chip can tell it from the user's edits. */
export const VOICE_INPUT_FLAG = "__voiceInsert";

/** Fields the user has placed the caret in at least once; elsewhere the transcript is appended at the end. */
const touched = new WeakSet<VoiceField>();
export function trackCaret(el: VoiceField): () => void {
  const mark = () => touched.add(el);
  if (el.ownerDocument?.activeElement === el) mark();
  el.addEventListener("focus", mark);
  return () => el.removeEventListener("focus", mark);
}

function setNativeValue(el: VoiceField, value: string) {
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  if (setter) setter.call(el, value);
  else el.value = value;
}

export interface Inserted {
  value: string;
  start: number;
  end: number;
}

/** The pure part: the new value and the range of the inserted words. */
export function spliceText(value: string, text: string, selStart: number, selEnd: number): Inserted {
  const start = Math.max(0, Math.min(selStart, value.length));
  const end = Math.max(start, Math.min(selEnd, value.length));
  const before = value.slice(0, start);
  const after = value.slice(end);
  const clean = text.trim();
  const lead = before && !/\s$/.test(before) ? " " : "";
  const trail = after && !/^[\s.,;:!?]/.test(after) ? " " : "";
  const at = before.length + lead.length;
  return { value: `${before}${lead}${clean}${trail}${after}`, start: at, end: at + clean.length };
}

export function insertIntoField(el: VoiceField, text: string): Inserted {
  const known = touched.has(el);
  const selStart = known ? (el.selectionStart ?? el.value.length) : el.value.length;
  const selEnd = known ? (el.selectionEnd ?? selStart) : el.value.length;
  const out = spliceText(el.value, text, selStart, selEnd);
  setNativeValue(el, out.value);
  const ev = new Event("input", { bubbles: true });
  (ev as unknown as Record<string, boolean>)[VOICE_INPUT_FLAG] = true;
  el.dispatchEvent(ev);
  const select = () => {
    el.focus({ preventScroll: false });
    try {
      el.setSelectionRange(out.start, out.end);
    } catch {
      // input types without a selection API
    }
  };
  select();
  // a controlled field re-renders after the event; select again once it has
  if (typeof window !== "undefined") window.requestAnimationFrame(select);
  return out;
}
