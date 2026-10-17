"use client";
/**
 * The one mic of every AI text box (research §3.7; VO-06). Speech → `POST /ai/voice/transcribe` → the text is
 * put into the box at the caret and selected for correction. It is **never sent**: the user reads it, edits it and
 * presses the box's own send button, so the same guardrails run as for typed text.
 *
 * - Desktop (fine pointer, or any keyboard): click to start, click again to stop; ⌘/Ctrl + Shift + M in the box.
 * - Phones (coarse pointer): press and hold to talk, release to stop. Slide up to lock (hands-free), slide left to
 *   cancel. A short tap also locks, so VoiceOver / TalkBack users (whose double tap is a click) can record.
 * - Esc cancels. First use opens the consent sheet. Errors are one plain sentence in the UI language.
 * - Hidden when voice is off or not set up for this user (no model, no permission, no voice backend).
 * - `aria-pressed` while recording; status changes are announced; reduced motion gives a static level bar.
 */
import { useQueryClient } from "@tanstack/react-query";
import { Check, ChevronLeft, ChevronUp, Loader2, Mic, Square, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { Button, IconButton } from "@/components/ui/button";
import { COARSE_POINTER, useMediaQuery } from "@/components/ui/use-media-query";
import { aiKeys } from "@/lib/api/ai-admin";
import { hidesMic, maxSecondsFor, needsConsent, useVoiceStatus, voiceApi, voiceKeys, type VoiceTarget } from "@/lib/api/voice";
import type { MessageKey } from "@/lib/i18n";
import { pairLang } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { useReduce } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { insertIntoField, trackCaret, VOICE_INPUT_FLAG, type VoiceField } from "./insert-text";
import { useVoiceRecorder } from "./use-voice-recorder";
import { VoiceCaptions } from "./voice-captions";
import { VoiceConsentSheet } from "./voice-consent-sheet";
import { errorKey, permissionHelpKey, serverError, type VoiceError } from "./voice-errors";

const LOCK_PX = 56;
const CANCEL_PX = 72;
const TAP_MS = 350;

export interface MicButtonProps {
  /** the AI surface (a meter tag and the per-surface cap) */
  target: VoiceTarget;
  /** the box the text goes into; without it the mic finds the box of its composer (`[data-slot=prompt-composer]`
   *  or the nearest `[data-voice-scope]`) */
  fieldRef?: RefObject<VoiceField | null>;
  /** instead of inserting, hand the text to the caller */
  onTranscript?: (text: string) => void;
  disabled?: boolean;
  className?: string;
}

function findField(from: HTMLElement | null): VoiceField | null {
  const scope = from?.closest<HTMLElement>("[data-voice-scope], [data-slot='prompt-composer']");
  return scope?.querySelector<VoiceField>("textarea, input[type='text'], input:not([type])") ?? null;
}

export function clock(ms: number): string {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function MicButton({ target, fieldRef, onTranscript, disabled, className }: MicButtonProps) {
  const { t, locale } = useI18n();
  const lang = pairLang(locale);
  const qc = useQueryClient();
  const status = useVoiceStatus();
  const coarse = useMediaQuery(COARSE_POINTER);
  const reduce = useReduce();
  const btn = useRef<HTMLButtonElement>(null);
  const [err, setErr] = useState<VoiceError | null>(null);
  const [notice, setNotice] = useState<VoiceError | null>(null);
  const [busy, setBusy] = useState(false);
  const [consentOpen, setConsentOpen] = useState(false);
  const [fromVoice, setFromVoice] = useState(false);
  const [announce, setAnnounce] = useState("");
  const [drag, setDrag] = useState<"none" | "lock" | "cancel">("none");
  const [locked, setLocked] = useState(false);
  const hold = useRef<{ id: number; x: number; y: number; t: number } | null>(null);
  const suppressClick = useRef(false);
  const abort = useRef<AbortController | null>(null);
  const max = maxSecondsFor(status.data, target);

  const field = useCallback(() => fieldRef?.current ?? findField(btn.current), [fieldRef]);

  const deliver = useCallback(
    (text: string) => {
      if (onTranscript) onTranscript(text);
      else {
        const el = field();
        if (el) insertIntoField(el, text);
      }
      setFromVoice(true);
      setAnnounce(t("voice.announce.inserted"));
    },
    [field, onTranscript, t],
  );

  const transcribe = useCallback(
    async (clip: Blob) => {
      setBusy(true);
      setAnnounce(t("voice.strip.transcribing"));
      const ac = new AbortController();
      abort.current = ac;
      try {
        const res = await voiceApi.transcribe(clip, target, lang, ac.signal);
        const text = res.text.trim();
        if (!text) setErr({ code: "empty" });
        else deliver(text);
      } catch (e) {
        if (ac.signal.aborted) return;
        const code = serverError(e, max);
        setErr(code);
        if (code.code === "consent_required" || code.code === "voice_off" || code.code === "not_configured") void qc.invalidateQueries({ queryKey: voiceKeys.status });
      } finally {
        abort.current = null;
        setBusy(false);
        void qc.invalidateQueries({ queryKey: aiKeys.me });
      }
    },
    [deliver, lang, max, qc, t, target],
  );

  const rec = useVoiceRecorder({
    maxSeconds: max,
    onClip: (clip) => void transcribe(clip),
    onCap: () => setNotice({ code: "too_long", params: { n: max } }),
    onError: (e) => setErr(e),
  });
  const recording = rec.phase === "recording" || rec.phase === "starting";

  useEffect(() => {
    if (rec.phase === "recording") setAnnounce(t("voice.announce.started"));
  }, [rec.phase, t]);

  // the field: remember whether its caret is meaningful; ⌘/Ctrl+Shift+M toggles; the chip goes on the user's edit
  const [fieldEl, setFieldEl] = useState<VoiceField | null>(null);
  useEffect(() => {
    setFieldEl(field());
  }, [field, status.data]);
  const toggleRef = useRef<() => void>(() => undefined);
  useEffect(() => {
    if (!fieldEl) return;
    const untrack = trackCaret(fieldEl);
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && (e.key === "M" || e.key === "m")) {
        e.preventDefault();
        toggleRef.current();
      }
    };
    const onInput = (e: Event) => {
      if (!(e as unknown as Record<string, boolean>)[VOICE_INPUT_FLAG]) setFromVoice(false);
    };
    fieldEl.addEventListener("keydown", onKey);
    fieldEl.addEventListener("input", onInput);
    return () => {
      untrack();
      fieldEl.removeEventListener("keydown", onKey);
      fieldEl.removeEventListener("input", onInput);
    };
  }, [fieldEl]);
  // the box was sent or cleared by its owner (no input event): drop the chip
  useEffect(() => {
    if (!fromVoice || !fieldEl) return;
    const id = setInterval(() => {
      if (!fieldEl.value.trim()) setFromVoice(false);
    }, 800);
    return () => clearInterval(id);
  }, [fromVoice, fieldEl]);

  const begin = useCallback(
    (handsFree: boolean) => {
      setErr(null);
      setNotice(null);
      rec.reset();
      if (status.data?.reason === "ai_voice_limit_reached") return setErr({ code: "ai_voice_limit_reached" });
      if (needsConsent(status.data)) return setConsentOpen(true);
      setLocked(handsFree);
      void rec.start({ handsFree });
    },
    [rec, status.data],
  );

  const cancelAll = useCallback(() => {
    abort.current?.abort();
    rec.cancel();
    setLocked(false);
    setDrag("none");
    hold.current = null;
    setAnnounce(t("voice.announce.cancelled"));
    btn.current?.focus();
  }, [rec, t]);

  const toggle = useCallback(() => {
    if (busy) return;
    if (rec.phase === "recording") rec.stop();
    else if (rec.phase === "starting") cancelAll();
    else begin(true);
  }, [begin, busy, cancelAll, rec]);
  toggleRef.current = toggle;

  // Esc cancels a recording (or a transcription) from anywhere on the page
  useEffect(() => {
    if (!recording && !busy) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        cancelAll();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [recording, busy, cancelAll]);

  if (hidesMic(status.data, status.error)) return null;

  const onPointerDown = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (!coarse || e.pointerType === "mouse" || busy || disabled) return;
    if (recording) return; // a locked recording: the tap (click) stops it
    suppressClick.current = true;
    if (needsConsent(status.data) || status.data?.reason === "ai_voice_limit_reached") return begin(false);
    e.preventDefault();
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      // synthetic events in tests
    }
    hold.current = { id: e.pointerId, x: e.clientX, y: e.clientY, t: Date.now() };
    setDrag("none");
    begin(false);
  };
  const onPointerMove = (e: React.PointerEvent<HTMLButtonElement>) => {
    const h = hold.current;
    if (!h || h.id !== e.pointerId) return;
    const dx = e.clientX - h.x;
    const dy = e.clientY - h.y;
    if (dx <= -CANCEL_PX) {
      hold.current = null;
      cancelAll();
    } else if (dy <= -LOCK_PX) {
      hold.current = null;
      setLocked(true);
      rec.setHandsFree(true);
      setDrag("none");
      setAnnounce(t("voice.announce.locked"));
    } else setDrag(dy < -LOCK_PX / 3 ? "lock" : dx < -CANCEL_PX / 3 ? "cancel" : "none");
  };
  const onPointerUp = (e: React.PointerEvent<HTMLButtonElement>) => {
    const h = hold.current;
    if (!h || h.id !== e.pointerId) return;
    hold.current = null;
    setDrag("none");
    if (Date.now() - h.t < TAP_MS) {
      // a tap: keep recording hands-free until Bitti
      setLocked(true);
      rec.setHandsFree(true);
      return;
    }
    rec.stop();
  };
  const onClick = () => {
    if (suppressClick.current) {
      suppressClick.current = false;
      return;
    }
    toggle();
  };

  const shown = err ?? notice;
  const label = recording ? t("voice.mic.stop") : t("voice.mic.start");
  const holdHint = coarse && recording && !locked;
  return (
    <span className={cn("inline-flex min-w-0 flex-wrap items-center gap-1.5", className)} data-testid={`voice-mic-${target}`} data-phase={busy ? "transcribing" : rec.phase}>
      <IconButton
        ref={btn}
        label={label}
        title={coarse ? (recording ? label : t("voice.mic.hold")) : `${label} (${t("voice.mic.shortcut")})`}
        size="sm"
        variant={recording ? "destructive" : "ghost"}
        aria-pressed={recording}
        aria-keyshortcuts="Control+Shift+M Meta+Shift+M"
        disabled={disabled || busy}
        onClick={onClick}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => {
          if (hold.current) cancelAll();
        }}
        onContextMenu={(e) => coarse && e.preventDefault()}
        className="touch-none select-none pointer-coarse:size-11 [-webkit-touch-callout:none]"
        data-testid="voice-mic"
      >
        {busy ? <Loader2 aria-hidden className="animate-spin motion-reduce:animate-none" /> : recording ? <Square aria-hidden className="fill-current" /> : <Mic aria-hidden />}
      </IconButton>

      {recording ? (
        <span className="inline-flex items-center gap-1.5" data-testid="voice-strip">
          <span aria-hidden className="size-2 shrink-0 rounded-full bg-status-infeasible-fg" />
          <span className="type-footnote font-medium tabular-nums text-label-1" data-testid="voice-clock">
            {rec.phase === "starting" ? t("voice.strip.starting") : clock(rec.elapsedMs)}
          </span>
          <LevelBar level={rec.level} reduce={reduce} />
          <VoiceCaptions active={rec.phase === "recording"} enabled={status.data?.live_captions === "on_device"} lang={lang === "tr" ? "tr-TR" : "en-GB"} />
          {holdHint ? (
            <span className={cn("inline-flex items-center gap-2 type-caption text-label-2", drag !== "none" && "text-label-1")} data-testid="voice-hold-hint">
              <span className={cn("inline-flex items-center", drag === "lock" && "font-semibold")}>
                <ChevronUp aria-hidden className="size-3.5" />
                {t("voice.strip.lock")}
              </span>
              <span className={cn("inline-flex items-center", drag === "cancel" && "font-semibold")}>
                <ChevronLeft aria-hidden className="size-3.5" />
                {t("voice.strip.cancel")}
              </span>
            </span>
          ) : (
            <>
              <Button size="xs" variant="secondary" onClick={() => rec.stop()} disabled={rec.phase !== "recording"} data-testid="voice-done">
                <Check aria-hidden />
                {t("voice.strip.done")}
              </Button>
              <IconButton size="xs" label={t("voice.strip.cancel")} onClick={cancelAll} data-testid="voice-cancel">
                <X aria-hidden />
              </IconButton>
            </>
          )}
        </span>
      ) : null}
      {busy ? (
        <span className="inline-flex items-center gap-1.5">
          <span className="type-footnote text-label-2">{t("voice.strip.transcribing")}</span>
          <IconButton size="xs" label={t("voice.strip.cancel")} onClick={cancelAll} data-testid="voice-cancel">
            <X aria-hidden />
          </IconButton>
        </span>
      ) : null}
      {fromVoice && !recording && !busy ? (
        <span className="rounded-full bg-fill-2 px-2 py-0.5 type-caption text-label-2" data-testid="voice-chip">
          {t("voice.chip")}
        </span>
      ) : null}
      {shown && !recording && !busy ? (
        <span role="alert" className={cn("min-w-0 basis-full type-footnote", err ? "text-status-infeasible-fg" : "text-status-warning-fg")} data-testid="voice-error" data-code={shown.code}>
          {t(errorKey(shown) as MessageKey, shown.params)}
          {shown.code === "permission_denied" ? <span className="block text-label-2">{t(permissionHelpKey())}</span> : null}
        </span>
      ) : null}
      <span className="sr-only" role="status" aria-live="polite">
        {announce}
      </span>
      <VoiceConsentSheet open={consentOpen} onOpenChange={setConsentOpen} status={status.data} returnFocus={btn} onAccepted={() => begin(true)} />
    </span>
  );
}

/** The input level: a bar that follows the voice, or a static bar under reduced motion. */
function LevelBar({ level, reduce }: { level: number; reduce: boolean }) {
  const { t } = useI18n();
  const pct = Math.round(Math.min(1, level) * 100);
  return (
    <span className="inline-block h-1.5 w-12 overflow-hidden rounded-full bg-fill-2" role="meter" aria-label={t("voice.level")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} data-testid="voice-level" data-static={reduce ? "1" : "0"}>
      <span className={cn("block h-full origin-left rounded-full bg-status-infeasible-fg", reduce ? "w-full opacity-60" : "w-full transition-transform duration-(--dur-fast)")} style={reduce ? undefined : { transform: `scaleX(${Math.max(0.04, level)})` }} />
    </span>
  );
}
