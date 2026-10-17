/** VO-06 error mapping, the TR/EN copy of every code, caret insertion and the on-device-only caption gate. */
import { describe, expect, it, vi } from "vitest";
import en from "../../../messages/en.json";
import tr from "../../../messages/tr.json";
import { HttpError } from "@/lib/api/client";
import { hidesMic, maxSecondsFor, needsConsent, VoiceStatus } from "@/lib/api/voice";
import { insertIntoField, spliceText, trackCaret } from "./insert-text";
import { canCaptionOnDevice, onDeviceRecognition } from "./voice-captions";
import { errorKey, mediaError, permissionHelpKey, serverError, VOICE_ERRORS } from "./voice-errors";

const http = (status: number, detail: unknown) => new HttpError(status, `${status}`, detail);
const lookup = (dict: unknown, key: string) => key.split(".").reduce<unknown>((o, k) => (o as Record<string, unknown> | undefined)?.[k], dict);

describe("copy", () => {
  it("every error code has Turkish and English copy, and the two differ", () => {
    for (const code of [...VOICE_ERRORS, "ai_voice_limit_reached_plain"]) {
      const a = lookup(tr, `voice.error.${code}`);
      const b = lookup(en, `voice.error.${code}`);
      expect(typeof a, code).toBe("string");
      expect(typeof b, code).toBe("string");
      expect(a).not.toBe(b);
    }
    expect(lookup(tr, "voice.error.policy_blocked")).toBe("Bu sitede mikrofon kullanımı kapalı. Yöneticinize bildirin.");
  });
});

describe("mediaError", () => {
  const blockedDoc = { featurePolicy: { allowsFeature: () => false } } as unknown as Document;
  it("maps DOMException names", () => {
    expect(mediaError({ name: "NotAllowedError" })).toEqual({ code: "permission_denied" });
    expect(mediaError({ name: "NotAllowedError" }, blockedDoc)).toEqual({ code: "policy_blocked" });
    expect(mediaError({ name: "NotFoundError" })).toEqual({ code: "no_device" });
    expect(mediaError({ name: "NotReadableError" })).toEqual({ code: "device_busy" });
    expect(mediaError({ name: "Weird" })).toEqual({ code: "provider_error" });
  });
});

describe("serverError", () => {
  it("maps the transcribe endpoint's codes", () => {
    expect(serverError(http(403, { detail: { code: "voice_consent_required" } }), 120)).toEqual({ code: "consent_required" });
    expect(serverError(http(413, { code: "too_long" }), 120)).toEqual({ code: "too_long", params: { n: 120 } });
    expect(serverError(http(429, { code: "ai_voice_limit_reached", used_min: 10, limit_min: 10 }), 120)).toEqual({ code: "ai_voice_limit_reached", params: { used: 10, limit: 10 } });
    expect(errorKey(serverError(http(429, { code: "ai_voice_limit_reached" }), 120))).toBe("voice.error.ai_voice_limit_reached_plain");
    expect(serverError(http(409, { code: "ai_transfer_basis_missing" }), 120)).toEqual({ code: "ai_transfer_basis_missing" });
    expect(serverError(http(409, { code: "voice_disabled" }), 120)).toEqual({ code: "voice_off" });
    expect(serverError(http(502, { code: "whatever" }), 120)).toEqual({ code: "provider_error" });
    expect(serverError(new Error("x"), 120)).toEqual({ code: "provider_error" });
  });
  it("per-browser permission help", () => {
    expect(permissionHelpKey("Mozilla/5.0 Firefox/131.0")).toBe("voice.help.firefox");
    expect(permissionHelpKey("Mozilla/5.0 (Macintosh) Version/18.0 Safari/605.1.15")).toBe("voice.help.safari");
    expect(permissionHelpKey("Mozilla/5.0 Chrome/141.0 Safari/537.36")).toBe("voice.help.chrome");
  });
});

describe("status helpers", () => {
  const st = (o: Record<string, unknown>) => VoiceStatus.parse({ available: true, ...o });
  it("hides the mic for config reasons and without a voice backend, keeps it for consent and the limit", () => {
    expect(hidesMic(undefined, new Error("404"))).toBe(true);
    expect(hidesMic(st({ available: false, reason: "disabled" }), null)).toBe(true);
    expect(hidesMic(st({ available: false, reason: "not_configured" }), null)).toBe(true);
    expect(hidesMic(st({ available: false, reason: "no_permission" }), null)).toBe(true);
    expect(hidesMic(st({ available: false, reason: "consent_required" }), null)).toBe(false);
    expect(hidesMic(st({ available: false, reason: "ai_voice_limit_reached" }), null)).toBe(false);
    expect(hidesMic(st({}), null)).toBe(false);
  });
  it("consent and the per-surface cap", () => {
    expect(needsConsent(st({ consent: false }))).toBe(true);
    expect(needsConsent(st({ consent: "granted" }))).toBe(false);
    expect(needsConsent(st({ consent: false, consent_required: false }))).toBe(false);
    expect(maxSecondsFor(st({ max_seconds: 120, max_seconds_by_target: { booking_nl: 45 } }), "booking_nl")).toBe(45);
    expect(maxSecondsFor(st({ max_seconds: 60 }), "chat")).toBe(60);
  });
});

describe("insert at the caret", () => {
  it("adds spaces where needed and returns the inserted range", () => {
    expect(spliceText("", "merhaba", 0, 0)).toEqual({ value: "merhaba", start: 0, end: 7 });
    expect(spliceText("MAT 101'i taşı", "salı", 10, 10)).toEqual({ value: "MAT 101'i salı taşı", start: 10, end: 14 });
    expect(spliceText("abc", " B-204 ", 3, 3)).toEqual({ value: "abc B-204", start: 4, end: 9 });
    expect(spliceText("x yyy z", "Q", 2, 5)).toEqual({ value: "x Q z", start: 2, end: 3 });
  });
  it("a field never focused gets the text at the end; the words are selected; one input event fires", () => {
    const el = document.createElement("textarea");
    document.body.append(el);
    el.value = "Önce";
    el.setSelectionRange(0, 0);
    const untrack = trackCaret(el);
    const onInput = vi.fn();
    el.addEventListener("input", onInput);
    insertIntoField(el, "B-204 numaralı salon");
    expect(el.value).toBe("Önce B-204 numaralı salon");
    expect(document.activeElement).toBe(el);
    expect([el.selectionStart, el.selectionEnd]).toEqual([5, 25]);
    expect(onInput).toHaveBeenCalledTimes(1);
    untrack();
    el.remove();
  });
});

describe("live captions gate", () => {
  it("no on-device mode → no recognizer (the cloud Web Speech is never used)", async () => {
    const ctor = vi.fn();
    class Cloud {
      constructor() {
        ctor();
      }
    }
    expect(onDeviceRecognition({ webkitSpeechRecognition: Cloud })).toBeNull();
    expect(await canCaptionOnDevice("tr-TR", { webkitSpeechRecognition: Cloud })).toBeNull();
    class NoPack {
      processLocally = false;
      static available = vi.fn(async () => "downloadable");
    }
    Object.defineProperty(NoPack.prototype, "processLocally", { value: false, writable: true });
    expect(await canCaptionOnDevice("tr-TR", { SpeechRecognition: NoPack })).toBeNull();
    expect(NoPack.available).toHaveBeenCalledWith({ langs: ["tr-TR"], processLocally: true });
    expect(ctor).not.toHaveBeenCalled();
  });
  it("on-device tr-TR available → the constructor is offered", async () => {
    class Local {
      processLocally = false;
      static available = async () => "available";
    }
    Object.defineProperty(Local.prototype, "processLocally", { value: false, writable: true });
    expect(await canCaptionOnDevice("tr-TR", { SpeechRecognition: Local })).toBe(Local);
  });
});
