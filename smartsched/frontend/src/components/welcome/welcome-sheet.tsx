"use client";
/**
 * The welcome sheet (spec §4.1, wireframes welcome-sheet-{1440,390}.svg).
 *
 * - Desktop (≥ 640 px): a 640 px dialog, hero, title + lead + audience badge, cards in two columns, footer with
 *   "Kısa turu başlat (1 dk)", "Sonra", "Başlarken listesi" and "Bir daha gösterme", and the restart hint line.
 * - Phone: the same dialog is a bottom sheet (ui/dialog); one card per page with dots and "1 / 4", İleri (50 px,
 *   "Başlayalım" on the last page), Sonra and Turu başlat (44 px, half width each).
 * - Focus: the title first (`tabIndex=-1`, screen readers hear the greeting); Esc / ✕ = Sonra; focus returns to the
 *   element that had it before the sheet opened, or to the page's h1. A card closes the sheet and opens its part.
 */
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { useMediaQuery } from "@/components/ui/use-media-query";
import type { WelcomeState } from "@/lib/api/welcome";
import { springs, tween, useReduce } from "@/lib/motion";
import { cn } from "@/lib/utils";
import type { ResolvedCard, SheetModel } from "./model";
import { SheetHero } from "./sheet-hero";
import { PagerDots } from "./pager-dots";
import { useGuideText } from "./use-guide-text";
import { WelcomeCard } from "./welcome-card";

export type SheetAction = { type: "start" } | { type: "later" } | { type: "never" } | { type: "checklist" } | { type: "card"; card: ResolvedCard };

export const PHONE_SHEET = "(max-width: 639.98px)";

export interface WelcomeSheetProps {
  open: boolean;
  model: SheetModel;
  state: WelcomeState | undefined;
  tourEnabled: boolean;
  checklistEnabled: boolean;
  preview?: boolean;
  onAction: (action: SheetAction) => void;
}

export function WelcomeSheet({ open, model, state, tourEnabled, checklistEnabled, preview, onAction }: WelcomeSheetProps) {
  const text = useGuideText(state);
  const { t } = text;
  const phone = useMediaQuery(PHONE_SHEET);
  const reduce = useReduce();
  const titleRef = useRef<HTMLHeadingElement>(null);
  // the element that had focus before the sheet opened (focus returns there, else the page's h1)
  const opener = useRef<HTMLElement | null>(null);
  const chosen = useRef<SheetAction | null>(null);
  const [page, setPage] = useState(0);
  const [dir, setDir] = useState(1);
  useEffect(() => {
    if (open) {
      const a = document.activeElement;
      opener.current = a instanceof HTMLElement && a !== document.body ? a : null;
      chosen.current = null;
    }
  }, [open]);

  const cards = model.cards;
  const last = Math.max(0, cards.length - 1);
  const title = text.title(model);
  const lead = text.lead(model);
  const badge = [text.audience(model.primary), text.department].filter(Boolean).join(" · ");

  const act = (a: SheetAction) => {
    chosen.current = a;
    onAction(a);
  };
  const finalFocus = () => {
    const a = chosen.current;
    // a card or the tour moves on to its own place (the page heading / the step card); Sonra, ✕, Esc return focus
    if (a && (a.type === "card" || a.type === "start" || a.type === "checklist")) return false;
    const back = opener.current;
    if (back && back.isConnected && back.offsetParent !== null) return back;
    return document.querySelector<HTMLElement>("main h1") ?? document.querySelector<HTMLElement>("#main");
  };

  const reveal = (i: number) =>
    reduce ? {} : { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, transition: { ...springs.smooth, delay: 0.06 + Math.min(i, 4) * 0.03 } };

  const cardEl = (c: ResolvedCard) => <WelcomeCard card={c} title={text.cardTitle(c)} body={text.cardBody(c)} alsoLabel={t("welcome.sheet.also")} onOpen={(card) => act({ type: "card", card })} />;

  const go = (to: number) => {
    setDir(to > page ? 1 : -1);
    setPage(Math.max(0, Math.min(last, to)));
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        // ✕, Esc, an outside press: "Sonra" (snoozed), unless an action already closed it
        if (!next && !chosen.current) act({ type: "later" });
      }}
    >
      <DialogContent
        data-welcome=""
        data-testid="welcome-sheet"
        data-variant={phone ? "pager" : "dialog"}
        initialFocus={titleRef}
        finalFocus={finalFocus}
        className="[--dialog-pad:1.25rem] sm:max-w-[640px] sm:[--dialog-pad:2rem] max-sm:max-h-[min(75dvh,calc(100dvh-3rem))] landscape:max-sm:max-h-[90dvh]"
      >
        <SheetHero audience={model.primary} />
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            {badge ? (
              <Badge variant="secondary" data-testid="welcome-badge">
                {badge}
              </Badge>
            ) : null}
            {model.updated ? <Badge data-testid="welcome-updated">{t("welcome.sheet.updated")}</Badge> : null}
            {preview ? <span className="type-footnote text-label-3">{t("welcome.sheet.preview")}</span> : null}
          </div>
          <DialogTitle ref={titleRef} tabIndex={-1} data-testid="welcome-sheet-title" className="type-title-1 outline-hidden sm:type-large-title">
            {title}
          </DialogTitle>
          <DialogDescription className="type-callout text-label-2 sm:type-body">{lead}</DialogDescription>
        </div>

        {phone ? (
          <div className="flex flex-col gap-3">
            <div role="group" aria-roledescription={t("welcome.sheet.slide")} aria-label={t("welcome.sheet.page", { n: page + 1, total: cards.length })} className="relative min-h-[120px] overflow-hidden">
              <AnimatePresence mode="popLayout" initial={false} custom={dir}>
                <motion.div
                  key={page}
                  custom={dir}
                  initial={reduce ? { opacity: 0 } : { opacity: 0, x: 24 * dir }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={reduce ? { opacity: 0, transition: tween.reduced } : { opacity: 0, x: -24 * dir, transition: tween.exit }}
                  transition={reduce ? tween.reduced : springs.smooth}
                >
                  {cards[page] ? cardEl(cards[page]) : null}
                </motion.div>
              </AnimatePresence>
            </div>
            <div className="flex items-center justify-between gap-2">
              <PagerDots count={cards.length} index={page} />
              <span className="type-footnote text-label-3 tabular-nums" data-testid="welcome-page">
                {t("welcome.sheet.page", { n: page + 1, total: cards.length })}
              </span>
            </div>
            <Button
              className="h-[50px] w-full type-body"
              data-testid="welcome-next"
              onClick={() => {
                if (page < last) go(page + 1);
                else act({ type: "card", card: cards[page]! });
              }}
            >
              {page < last ? t("welcome.sheet.next") : t("welcome.sheet.letsGo")}
            </Button>
            <div className="grid grid-cols-2 gap-2">
              <Button variant="secondary" className="min-h-11" data-testid="welcome-later" onClick={() => act({ type: "later" })}>
                {t("welcome.sheet.later")}
              </Button>
              {tourEnabled ? (
                <Button variant="outline" className="min-h-11" data-testid="welcome-start-tour" onClick={() => act({ type: "start" })}>
                  {t("welcome.sheet.startShort")}
                </Button>
              ) : null}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
              {checklistEnabled ? (
                <Button variant="link" className="min-h-11" data-testid="welcome-open-checklist" onClick={() => act({ type: "checklist" })}>
                  {t("welcome.sheet.checklist")}
                </Button>
              ) : null}
              <Button variant="link" className="min-h-11 text-label-2" data-testid="welcome-never" onClick={() => act({ type: "never" })}>
                {t("welcome.sheet.never")}
              </Button>
            </div>
          </div>
        ) : (
          <>
            <ul className="grid grid-cols-2 gap-3" data-testid="welcome-cards">
              {cards.map((c, i) => (
                <motion.li key={`${c.audience}-${c.key}`} {...reveal(i)} className={cn(cards.length % 2 === 1 && i === cards.length - 1 && "col-span-2")}>
                  {cardEl(c)}
                </motion.li>
              ))}
            </ul>
            <div className="flex flex-col gap-3 pt-1">
              <div className="flex flex-wrap items-center gap-2">
                {tourEnabled ? (
                  <Button data-testid="welcome-start-tour" onClick={() => act({ type: "start" })}>
                    {t("welcome.sheet.start")}
                  </Button>
                ) : null}
                <Button variant="secondary" data-testid="welcome-later" onClick={() => act({ type: "later" })}>
                  {t("welcome.sheet.later")}
                </Button>
                {checklistEnabled ? (
                  <Button variant="link" className="ml-2" data-testid="welcome-open-checklist" onClick={() => act({ type: "checklist" })}>
                    {t("welcome.sheet.checklist")}
                  </Button>
                ) : null}
                <Button variant="link" className="ml-auto text-label-2" data-testid="welcome-never" onClick={() => act({ type: "never" })}>
                  {t("welcome.sheet.never")}
                </Button>
              </div>
              <p className="type-footnote text-label-3">{t("welcome.sheet.restartHint")}</p>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
