"use client";
/**
 * Optional live captions while recording, **on the device only** (research §2.4; owner decision 2026-10-18).
 * The browser's `SpeechRecognition` sends audio to a cloud service by default (Chrome: Google), which is never
 * allowed here. It is used only when all of these hold:
 * - the admin setting `live_captions` is `on_device`;
 * - the browser has the on-device mode (`processLocally` on the prototype and the static `available()`);
 * - `available({langs: [lang], processLocally: true})` answers `"available"` (the language pack is installed; we
 *   never call `install()`, which would download it).
 * Then `processLocally = true` is set before `start()`. Anything else: no recognizer is ever constructed and the
 * strip only says the text comes when the recording ends. The captions are interim only; the transcript that
 * lands in the box always comes from the server's speech route.
 */
import { useEffect, useState } from "react";
import { useI18n } from "@/lib/i18n/provider";

interface RecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  processLocally: boolean;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: (() => void) | null;
  start(): void;
  abort(): void;
}
interface RecognitionCtor {
  new (): RecognitionLike;
  prototype: object;
  available?: (o: { langs: string[]; processLocally: boolean }) => Promise<string>;
}

/** The recognizer constructor, only when it can run on the device; otherwise null. */
export function onDeviceRecognition(win: unknown = typeof window === "undefined" ? undefined : window): RecognitionCtor | null {
  if (!win) return null;
  const w = win as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  if (!Ctor || typeof Ctor.available !== "function" || !("processLocally" in Ctor.prototype)) return null;
  return Ctor;
}

export async function canCaptionOnDevice(lang: string, win?: unknown): Promise<RecognitionCtor | null> {
  const Ctor = onDeviceRecognition(win);
  if (!Ctor?.available) return null;
  try {
    return (await Ctor.available({ langs: [lang], processLocally: true })) === "available" ? Ctor : null;
  } catch {
    return null;
  }
}

export function VoiceCaptions({ active, enabled, lang }: { active: boolean; enabled: boolean; lang: string }) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const [onDevice, setOnDevice] = useState(false);
  useEffect(() => {
    if (!active || !enabled) return;
    let rec: RecognitionLike | null = null;
    let gone = false;
    void canCaptionOnDevice(lang).then((Ctor) => {
      if (gone || !Ctor) return;
      const r = new Ctor();
      r.processLocally = true;
      if (r.processLocally !== true) return; // never fall back to the cloud recognizer
      r.lang = lang;
      r.interimResults = true;
      r.continuous = true;
      r.onresult = (e) => setText(Array.from(e.results, (x) => x[0]?.transcript ?? "").join(" "));
      r.onerror = () => setOnDevice(false);
      rec = r;
      setOnDevice(true);
      try {
        r.start();
      } catch {
        setOnDevice(false);
      }
    });
    return () => {
      gone = true;
      rec?.abort();
      setText("");
      setOnDevice(false);
    };
  }, [active, enabled, lang]);
  if (!active) return null;
  return (
    <span role="status" aria-live="polite" aria-label={t("voice.captions.label")} className="min-w-0 max-w-48 truncate type-footnote text-label-2" data-testid="voice-captions" data-on-device={onDevice ? "1" : "0"}>
      {onDevice && text ? text : <span className="sr-only">{t("voice.strip.later")}</span>}
    </span>
  );
}
