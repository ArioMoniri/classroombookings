"use client";
/**
 * One microphone clip (research §2.4, §3.2): `getUserMedia` → `MediaRecorder` (Opus in WebM where the browser has
 * it, then Ogg/Opus, then MP4/AAC for Safari), an `AnalyserNode` RMS level for the meter (no worklet / wasm, so the
 * CSP is untouched), and three automatic stops: the `maxSeconds` cap, ~2 s of silence after speech (hands-free mode
 * only), and `cancel()` (Esc). The clip stays in memory and goes to `onClip`; nothing is written anywhere.
 *
 * Phases: idle → starting (waiting for the browser prompt) → recording → idle, or error. A cancel during
 * `starting` releases the microphone as soon as the browser hands it over.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { mediaError, preflightError, type VoiceError } from "./voice-errors";

export type RecorderPhase = "idle" | "starting" | "recording" | "error";

/** Formats in order of preference (the backend accepts webm, ogg, mp4, mpeg and wav). */
export const MIME_PREFERENCE = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"] as const;

export function pickMime(isSupported: (m: string) => boolean = (m) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(m)): string | undefined {
  return MIME_PREFERENCE.find((m) => {
    try {
      return isSupported(m);
    } catch {
      return false;
    }
  });
}

/** RMS of a time-domain frame (bytes centred on 128) → 0…1, scaled so normal speech reads about 0.3–0.8. */
export function rmsLevel(frame: Uint8Array): number {
  if (!frame.length) return 0;
  let sum = 0;
  for (let i = 0; i < frame.length; i++) {
    const v = (frame[i]! - 128) / 128;
    sum += v * v;
  }
  return Math.min(1, Math.sqrt(sum / frame.length) * 4);
}

const TICK_MS = 100;
const SPEECH_LEVEL = 0.08;
const MIN_CLIP_MS = 400;

export interface RecorderOptions {
  maxSeconds: number;
  /** a finished clip (not called after cancel or for a clip shorter than 0.4 s) */
  onClip: (clip: Blob, durationMs: number) => void;
  /** the cap stopped the recording (the clip is still delivered) */
  onCap?: () => void;
  onError?: (e: VoiceError) => void;
  /** the microphone is live (announce it) */
  onStart?: () => void;
  silenceMs?: number;
}

export function useVoiceRecorder({ maxSeconds, onClip, onCap, onError, onStart, silenceMs = 2000 }: RecorderOptions) {
  const [phase, setPhase] = useState<RecorderPhase>("idle");
  const [elapsedMs, setElapsed] = useState(0);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<VoiceError | null>(null);
  const r = useRef({
    rec: null as MediaRecorder | null,
    stream: null as MediaStream | null,
    ctx: null as AudioContext | null,
    analyser: null as AnalyserNode | null,
    timer: 0 as ReturnType<typeof setInterval> | 0,
    t0: 0,
    chunks: [] as Blob[],
    cancelled: false,
    capped: false,
    heard: false,
    quietSince: 0,
    handsFree: false,
    busy: false,
  });
  const cb = useRef({ onClip, onCap, onError, onStart, maxSeconds, silenceMs });
  useEffect(() => {
    cb.current = { onClip, onCap, onError, onStart, maxSeconds, silenceMs };
  });

  const release = useCallback(() => {
    const s = r.current;
    if (s.timer) clearInterval(s.timer);
    s.timer = 0;
    s.stream?.getTracks().forEach((t) => t.stop());
    s.stream = null;
    void s.ctx?.close().catch(() => undefined);
    s.ctx = null;
    s.analyser = null;
    s.rec = null;
    s.busy = false;
    setLevel(0);
  }, []);

  const fail = useCallback(
    (e: VoiceError) => {
      release();
      setError(e);
      setPhase("error");
      cb.current.onError?.(e);
    },
    [release],
  );

  const stop = useCallback(() => {
    const rec = r.current.rec;
    if (rec && rec.state !== "inactive") rec.stop();
    else if (r.current.busy) r.current.cancelled = true; // still waiting for the prompt: drop it when it arrives
  }, []);

  const cancel = useCallback(() => {
    r.current.cancelled = true;
    stop();
    if (!r.current.rec) {
      release();
      setPhase("idle");
    }
  }, [release, stop]);

  /** Hands-free (desktop click or a locked phone recording) also stops after ~2 s of silence after speech. */
  const setHandsFree = useCallback((v: boolean) => {
    r.current.handsFree = v;
    r.current.quietSince = 0;
  }, []);

  const start = useCallback(
    async ({ handsFree = true }: { handsFree?: boolean } = {}) => {
      const s = r.current;
      if (s.busy) return;
      const pre = preflightError();
      if (pre) return fail(pre);
      s.busy = true;
      s.cancelled = false;
      s.capped = false;
      s.heard = false;
      s.quietSince = 0;
      s.handsFree = handsFree;
      s.chunks = [];
      setError(null);
      setElapsed(0);
      setPhase("starting");
      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } });
      } catch (e) {
        s.busy = false;
        if (s.cancelled) return setPhase("idle");
        return fail(mediaError(e, document));
      }
      s.stream = stream;
      if (s.cancelled) {
        release();
        return setPhase("idle");
      }
      const mimeType = pickMime();
      let rec: MediaRecorder;
      try {
        rec = new MediaRecorder(stream, mimeType ? { mimeType, audioBitsPerSecond: 32_000 } : undefined);
      } catch (e) {
        return fail(mediaError(e, document));
      }
      s.rec = rec;
      rec.ondataavailable = (ev: BlobEvent) => {
        if (ev.data && ev.data.size) s.chunks.push(ev.data);
      };
      rec.onstop = () => {
        const duration = Date.now() - s.t0;
        const type = rec.mimeType || mimeType || "audio/webm";
        const cancelled = s.cancelled;
        const capped = s.capped;
        const chunks = s.chunks;
        s.chunks = [];
        release();
        setPhase("idle");
        if (cancelled) return;
        if (capped) cb.current.onCap?.();
        const blob = new Blob(chunks, { type }); // e.g. audio/webm;codecs=opus: the Content-Type of the upload
        if (duration < MIN_CLIP_MS || !blob.size) {
          const e: VoiceError = { code: "empty" };
          setError(e);
          setPhase("error");
          cb.current.onError?.(e);
          return;
        }
        cb.current.onClip(blob, duration);
      };
      try {
        const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
        if (Ctx) {
          const ctx = new Ctx();
          const src = ctx.createMediaStreamSource(stream);
          const analyser = ctx.createAnalyser();
          analyser.fftSize = 1024;
          src.connect(analyser);
          s.ctx = ctx;
          s.analyser = analyser;
        }
      } catch {
        // no meter (old browser): recording still works
      }
      rec.start(1000);
      s.t0 = Date.now();
      setPhase("recording");
      cb.current.onStart?.();
      try {
        navigator.vibrate?.(10);
      } catch {
        // no haptics
      }
      const frame = new Uint8Array(1024);
      s.timer = setInterval(() => {
        const now = Date.now();
        const ms = now - s.t0;
        setElapsed(ms);
        let lv = 0;
        if (s.analyser) {
          s.analyser.getByteTimeDomainData(frame);
          lv = rmsLevel(frame);
          setLevel(lv);
        }
        if (ms >= cb.current.maxSeconds * 1000) {
          s.capped = true;
          stop();
          return;
        }
        if (!s.analyser || !s.handsFree) return;
        if (lv >= SPEECH_LEVEL) {
          s.heard = true;
          s.quietSince = 0;
        } else if (s.heard) {
          if (!s.quietSince) s.quietSince = now;
          else if (now - s.quietSince >= cb.current.silenceMs) stop();
        }
      }, TICK_MS);
    },
    [fail, release, stop],
  );

  // leaving the page (or the surface unmounting) never leaves the microphone on
  useEffect(
    () => () => {
      r.current.cancelled = true;
      const rec = r.current.rec;
      if (rec && rec.state !== "inactive") rec.stop();
      release();
    },
    [release],
  );

  const reset = useCallback(() => {
    setError(null);
    setPhase((p) => (p === "error" ? "idle" : p));
  }, []);

  return { phase, elapsedMs, level, error, start, stop, cancel, reset, setHandsFree };
}
