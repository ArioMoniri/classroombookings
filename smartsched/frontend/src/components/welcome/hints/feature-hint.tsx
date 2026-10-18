"use client";
/**
 * The desktop hint on a nav entry (spec §4.5, wireframe welcome-hints-help.svg A): a small non-modal popover
 * (`role="dialog"`, `aria-modal="false"`) next to the entry. It keeps focus where it is; Esc or an outside press count
 * as "Anladım". Only the one hint the server picked for this session (`show.kind === "hint"`) auto-shows, and never
 * while a sheet, the tour or another dialog is open. Opaque `--surface-raised` (no extra blur, spec §8.3).
 */
import { computePosition, flip, offset, shift, autoUpdate } from "@floating-ui/dom";
import { motion } from "motion/react";
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Button } from "@/components/ui/button";
import { useMediaQuery } from "@/components/ui/use-media-query";
import { useI18n } from "@/lib/i18n/provider";
import { useReduce } from "@/lib/motion";
import { hintKey } from "../content";
import { welcomeMotion } from "../motion";
import { findAnchor } from "../tour/anchors";
import { otherDialogOpen, useWelcomeStore } from "../welcome-store";
import { useEligibleHints, useHintActions, useHintText } from "./registry";

export function FeatureHintPopover() {
  const { t } = useI18n();
  const reduce = useReduce();
  const desktop = useMediaQuery("(min-width: 1024px)");
  const autoHint = useWelcomeStore((s) => s.autoHint);
  const busy = useWelcomeStore((s) => !!s.sheet || !!s.tour);
  const hints = useEligibleHints();
  const text = useHintText();
  const actions = useHintActions();
  const hint = autoHint ? hints.find((h) => h.def.key === hintKey(autoHint) && h.def.nav) : undefined;
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useEffect(() => {
    if (!hint || !desktop || busy) return;
    let tries = 0;
    const id = window.setInterval(() => {
      const el = findAnchor(hint.def.nav!);
      if (el && !otherDialogOpen()) {
        window.clearInterval(id);
        setAnchor(el);
      } else if (++tries > 30) window.clearInterval(id);
    }, 200);
    return () => window.clearInterval(id);
  }, [hint, desktop, busy]);

  useEffect(() => {
    const floating = ref.current;
    if (!anchor || !floating) return;
    return autoUpdate(anchor, floating, () => {
      void computePosition(anchor, floating, { strategy: "fixed", placement: "right", middleware: [offset(12), flip(), shift({ padding: 8 })] }).then(({ x, y }) => setPos({ x, y }));
    });
  }, [anchor]);

  useEffect(() => {
    if (!anchor || !hint) return;
    const key = hint.def.key;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") actions.seen(key);
    };
    const onDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) actions.seen(key);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown);
    };
  }, [anchor, hint, actions]);

  if (!hint || !anchor || !desktop || busy) return null;
  const key = hint.def.key;
  return createPortal(
    <motion.div
      ref={ref}
      role="dialog"
      aria-modal="false"
      aria-labelledby={titleId}
      data-welcome=""
      data-testid={`hint-${key}`}
      initial={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.98 }}
      animate={{ opacity: pos ? 1 : 0, scale: 1 }}
      transition={reduce ? welcomeMotion.reduced : welcomeMotion.popover}
      style={{ position: "fixed", left: pos?.x ?? 0, top: pos?.y ?? 0, transformOrigin: "left center" }}
      className="z-50 w-80 rounded-2xl bg-(--mat-thick-solid) p-4 text-label-1 shadow-elev-2"
    >
      <p id={titleId} className="type-headline">
        {text.title(hint)}
      </p>
      <p className="mt-1 type-callout text-label-2">{text.body(hint)}</p>
      <div className="mt-3 flex items-center gap-2">
        <Button size="sm" onClick={() => actions.tryIt(hint.def)} data-testid={`hint-try-${key}`}>
          {t("welcome.hints.try")}
        </Button>
        <Button size="sm" variant="secondary" onClick={() => actions.seen(key)} data-testid={`hint-dismiss-${key}`}>
          {t("welcome.hints.dismiss")}
        </Button>
        <Button size="sm" variant="link" className="ml-auto" onClick={() => actions.allNews(hint.def)}>
          {t("welcome.hints.allNews")}
        </Button>
      </div>
    </motion.div>,
    document.body,
  );
}
