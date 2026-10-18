"use client";
/**
 * HX-03 (helper.md §2.4, §2.5, §5.3, §8): the helper sheet.
 *
 * - Desktop (≥ 1024 px): a **non-modal** `role="complementary"` side sheet, 360 px (1024–1279) / 400 px, docked right
 *   under the top bar, no scrim, the page stays operable (needed for "Göster"). Esc inside closes it; F6 moves the
 *   focus between the page and the sheet.
 * - Below 1024 px: a full-screen `role="dialog"` with `aria-modal`, a focus trap, a 44 px "Kapat" and a docked composer.
 * - The log is `role="log"` (polite, `aria-busy` while a turn runs); "Düşünüyor…" is `role="status"`.
 * - AI mode: `AiUsageBanner`, `PromptComposer` (16 px), role starters, `AiNotice`. A hard limit disables the composer
 *   with the reason and keeps the shortcuts and "Nerede?" search (Rehber modu under it).
 * - Index mode (`mode: index`, the default): **Rehber modu**, a search field and shortcuts, no composer.
 * - On close, focus returns to the opener, or to the page's h1 / main when the opener is gone (never <body>).
 * - HX-15: the empty thread shows "Son işlemler" (recent.tsx). HX-16: the footer's "Bu sayfa: …" chip (AI mode, above
 *   the composer); while it is on every question carries the page `context`; ✕ removes it for this page, the focus
 *   goes to the composer (page-context.tsx).
 */
import { MoreHorizontal, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { AiNotice } from "@/components/admin/ai/ai-kit";
import { AiUsageBanner } from "@/components/admin/ai/my-ai-usage";
import { Alert } from "@/components/ui/alert";
import { PromptComposer } from "@/components/ui/beautifului/prompt-composer";
import { Button, IconButton } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { trapTabKey } from "@/components/ui/focus-trap";
import { useMediaQuery } from "@/components/ui/use-media-query";
import { useHelperActions, useHelperMemory } from "@/lib/api/helper";
import { usePermissions } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";
import { springs, tween, useReduce } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";
import { CardHostContext, pickText, type CardHost } from "./cards/context";
import { EntryView } from "./cards/render";
import { GuideMode } from "./guide";
import { PageContextChip, toTurnContext, usePageContext } from "./page-context";
import { RecentActions } from "./recent";
import { clientActionLabel } from "./remember";
import { useHelperStore } from "./helper-store";
import { Starters, starterRole } from "./starters";
import { StatusChip, useHelperMode } from "./status-chip";
import { useHelperRunner } from "./use-helper-runner";

export const DESKTOP_SHEET = "(min-width: 1024px)";

/** Where the focus goes when the sheet closes: the opener if it is still on the page, else the page's h1 / main. */
export function returnFocus(opener: HTMLElement | null) {
  const target = opener && opener.isConnected ? opener : (document.querySelector<HTMLElement>("main h1") ?? document.getElementById("main"));
  if (target && target.tabIndex < 0 && !target.matches("a[href],button,input,select,textarea")) target.setAttribute("tabindex", "-1");
  target?.focus();
}

function useCardHostValue(desktop: boolean): CardHost {
  const { locale } = useI18n();
  const router = useRouter();
  const runner = useHelperRunner();
  const { can } = usePermissions();
  const actions = useHelperActions();
  const textOnly = useHelperStore((s) => s.textOnly);
  return useMemo<CardHost>(() => {
    const list = actions.data ?? null;
    return {
      runner,
      locale,
      can,
      actions: list ? new Set(list.map((a) => a.name)) : null,
      actionVerb: (name) => {
        const a = list?.find((x) => x.name === name);
        return a?.summary ? pickText(a.summary, locale) : clientActionLabel(locale)(name);
      },
      go: (href) => {
        if (!desktop) useHelperStore.getState().closeSheet();
        router.push(href);
      },
      showMe: (featureId) => {
        const st = useHelperStore.getState();
        st.startShowMe(featureId, !desktop && st.open);
        if (!desktop) st.closeSheet();
      },
      searchMenu: () => useUiStore.getState().setPaletteOpen(true),
      textOnly,
    };
  }, [actions.data, can, desktop, locale, router, runner, textOnly]);
}

function Log({ busy }: { busy: boolean }) {
  const { t } = useI18n();
  const entries = useHelperStore((s) => s.entries);
  const turn = useHelperStore((s) => s.turn);
  const ref = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  useEffect(() => {
    const el = ref.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [entries.length, turn.busy, turn.draft]);
  return (
    <div
      ref={ref}
      role="log"
      aria-live="polite"
      aria-busy={busy || undefined}
      aria-label={t("helper.log")}
      data-testid="helper-log"
      onScroll={(e) => {
        const el = e.currentTarget;
        stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
      }}
      className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto overscroll-contain px-4 py-3"
    >
      {entries.map((e) => (
        <div key={e.key} data-entry={e.key} tabIndex={-1} className="helper-enter flex flex-col outline-hidden">
          <EntryView entry={e} />
        </div>
      ))}
      {turn.busy ? (
        <div role="status" className="flex flex-col gap-1" data-testid="helper-thinking">
          <p className="helper-shimmer type-callout text-label-2">{t("helper.thinking")}</p>
          {turn.tools.map((x, i) => (
            <p key={i} className="type-footnote text-label-3">
              {t(x.state === "failed" ? "helper.tool.failed" : x.state === "ok" ? "helper.tool.done" : "helper.tool.running")}
            </p>
          ))}
          {turn.draft ? <p className="type-body text-label-1 whitespace-pre-line">{turn.draft}</p> : null}
        </div>
      ) : null}
    </div>
  );
}

function SheetBody({ titleId, desktop, onClose }: { titleId: string; desktop: boolean; onClose: () => void }) {
  const { t, locale } = useI18n();
  const router = useRouter();
  const host = useCardHostValue(desktop);
  const mode = useHelperMode();
  const { can } = usePermissions();
  const entries = useHelperStore((s) => s.entries);
  const turn = useHelperStore((s) => s.turn);
  const textOnly = useHelperStore((s) => s.textOnly);
  const memory = useHelperMemory(mode.ai);
  const composerRef = useRef<HTMLDivElement>(null);
  const guideRef = useRef<HTMLInputElement>(null);
  const lastAsk = [...entries].reverse().find((e) => e.kind === "user");
  const guideSeed = useHelperStore((s) => s.guideSeed);
  const pendingAsk = useHelperStore((s) => s.pendingAsk);
  const pendingAction = useHelperStore((s) => s.pendingAction);
  const { runner } = host;

  // HX-16: "Bu sayfa: …" — on for the current page until its ✕ is tapped (a new page brings it back)
  const page = usePageContext();
  const [contextOff, setContextOff] = useState<string | null>(null);
  const [contextLive, setContextLive] = useState("");
  const chipOn = !!page && mode.ai && !mode.blocked && contextOff !== page.route;
  const wire = chipOn && page ? toTurnContext(page) : null;
  const wireKey = wire ? JSON.stringify(wire) : "";
  const context = useMemo(() => (wireKey ? (JSON.parse(wireKey) as NonNullable<typeof wire>) : null), [wireKey]);
  const askHere = useCallback((text: string) => runner.ask(text, { context }), [runner, context]);
  const removeContext = () => {
    if (!page) return;
    setContextOff(page.route);
    setContextLive(t("helper.context.removed"));
    // the ✕ goes away with the chip: the composer takes the focus (never <body>)
    requestAnimationFrame(() => composerRef.current?.querySelector<HTMLTextAreaElement>("textarea:not([disabled])")?.focus());
  };

  // the palette's "Yardımcıya sor" text and the Kısayollar action run once the mode is known (also while open)
  useEffect(() => {
    if (mode.loading || (!pendingAsk && !pendingAction)) return;
    const st = useHelperStore.getState();
    const { ask, action } = st.takePending();
    if (action) void runner.runAction(action.action, action.args, { hints: action.hints });
    else if (ask && mode.ai && !mode.blocked) void askHere(ask);
    else if (ask) st.setGuideSeed(ask);
  }, [pendingAsk, pendingAction, mode.loading, mode.ai, mode.blocked, runner, askHere]);

  // focus on open: the composer (AI) or the guide field (index), on the first frame
  useEffect(() => {
    const id = requestAnimationFrame(() => {
      const field = composerRef.current?.querySelector<HTMLTextAreaElement>("textarea:not([disabled])") ?? guideRef.current;
      field?.focus();
    });
    return () => cancelAnimationFrame(id);
  }, [mode.loading]);

  const role = starterRole(can);
  const empty = entries.length === 0 && !turn.busy;
  const notes = memory.data?.enabled ? memory.data.notes : 0;
  const guide = !mode.ai || mode.blocked;

  return (
    <CardHostContext.Provider value={host}>
      <header className="flex h-14 shrink-0 items-center gap-2 px-2 edge-hairline-b">
        {!desktop ? <IconButton label={t("helper.close")} onClick={onClose} data-testid="helper-close" className="size-11"><X aria-hidden /></IconButton> : null}
        <h2 id={titleId} className="type-headline min-w-0 flex-1 truncate pl-2 text-label-1">
          {t("helper.title")}
        </h2>
        <StatusChip mode={mode} />
        <DropdownMenu>
          <DropdownMenuTrigger render={<IconButton label={t("helper.menu")} className="size-11" data-testid="helper-menu"><MoreHorizontal aria-hidden /></IconButton>} />
          <DropdownMenuContent align="end" className="min-w-56">
            <DropdownMenuItem onClick={() => useHelperStore.getState().newThread()} data-testid="helper-new-thread">{t("helper.newThread")}</DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => {
                if (!desktop) onClose();
                router.push("/profile#helper");
              }}
            >
              {t("helper.memory.title")}
            </DropdownMenuItem>
            <DropdownMenuCheckboxItem checked={textOnly} onCheckedChange={(v) => useHelperStore.getState().setTextOnly(!!v)} data-testid="helper-text-only">
              {t("helper.textOnly")}
            </DropdownMenuCheckboxItem>
          </DropdownMenuContent>
        </DropdownMenu>
        {desktop ? <IconButton label={t("helper.close")} onClick={onClose} data-testid="helper-close"><X aria-hidden /></IconButton> : null}
      </header>
      {empty ? (
        <div className="flex flex-col gap-3 px-4 pt-4" data-testid="helper-empty">
          <p className="type-body text-label-1">{mode.ai ? t("helper.empty") : t("helper.guide.title")}</p>
          {mode.ai && !mode.blocked ? <Starters role={role} onPick={(s) => void askHere(s)} /> : null}
          <RecentActions />
          {notes > 0 ? (
            <p className="type-footnote text-label-2" data-testid="helper-memory-used">
              {t("helper.memory.usingNotes", { n: notes })}{" "}
              <Button variant="link" size="sm" className="h-auto min-h-0 p-0" onClick={() => host.go("/profile#helper")}>
                {t("helper.memory.manage")}
              </Button>
            </p>
          ) : null}
        </div>
      ) : null}
      <Log busy={turn.busy} />
      <footer className="flex shrink-0 flex-col gap-2 px-4 pt-2 pb-[max(0.75rem,env(safe-area-inset-bottom))] edge-hairline-t">
        {turn.error ? (
          <Alert
            tone="error"
            data-testid="helper-error"
            action={
              lastAsk && lastAsk.kind === "user" && mode.ai ? (
                <Button size="sm" variant="secondary" onClick={() => void askHere(lastAsk.text)}>
                  {t("helper.retry")}
                </Button>
              ) : undefined
            }
          >
            {pickText(turn.error, locale)}
          </Alert>
        ) : null}
        {mode.ai ? <AiUsageBanner /> : null}
        {mode.ai && mode.blocked ? <p className="type-callout text-label-2" data-testid="helper-blocked">{t("helper.limitReason")}</p> : null}
        {guide ? <GuideMode inputRef={guideRef} seed={guideSeed} showLead={!mode.ai} /> : null}
        <p className="sr-only" role="status" data-testid="helper-context-live">
          {contextLive}
        </p>
        {chipOn && page ? <PageContextChip page={page} onRemove={removeContext} /> : null}
        {mode.ai ? (
          <div ref={composerRef} data-testid="helper-composer">
            <PromptComposer
              onSend={(text) => void askHere(text)}
              busy={turn.busy}
              disabled={mode.blocked}
              placeholder={t("helper.composer.placeholder")}
              label={t("helper.composer.label")}
              sendLabel={t("helper.composer.send")}
              stopLabel={t("helper.composer.stop")}
              className="[&_textarea]:text-base [&_button]:pointer-coarse:size-11"
            />
          </div>
        ) : null}
        {mode.ai ? <AiNotice /> : null}
      </footer>
    </CardHostContext.Provider>
  );
}

export function HelperSheet() {
  const { t } = useI18n();
  const open = useHelperStore((s) => s.open);
  const desktop = useMediaQuery(DESKTOP_SHEET);
  const reduce = useReduce();
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);
  const pathname = usePathname();

  const close = useCallback(() => {
    const opener = useHelperStore.getState().opener;
    useHelperStore.getState().closeSheet();
    requestAnimationFrame(() => returnFocus(opener));
  }, []);

  // F6 cycles page ↔ sheet on desktop (the sheet is non-modal)
  useEffect(() => {
    if (!open || !desktop) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "F6") return;
      const sheet = ref.current;
      if (!sheet) return;
      e.preventDefault();
      if (sheet.contains(document.activeElement)) document.getElementById("main")?.focus();
      else (sheet.querySelector<HTMLElement>("textarea:not([disabled])") ?? sheet.querySelector<HTMLElement>("[data-testid=helper-guide-input]") ?? sheet.querySelector<HTMLElement>("[data-testid=helper-close]") ?? sheet).focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, desktop]);

  // a page change on a phone ends the full-screen sheet (it was a hand-over)
  const lastPath = useRef(pathname);
  useEffect(() => {
    if (lastPath.current !== pathname && !desktop && useHelperStore.getState().open) useHelperStore.getState().closeSheet();
    lastPath.current = pathname;
  }, [pathname, desktop]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape" && !e.defaultPrevented) {
      // a menu or popover inside handles its own Esc first
      if ((e.target as HTMLElement).closest("[role=menu],[role=dialog]:not([data-helper-sheet])")) return;
      e.stopPropagation();
      close();
      return;
    }
    if (!desktop) trapTabKey(e, ref.current);
  };

  const enter = reduce ? { opacity: 0 } : desktop ? { opacity: 0, x: 24 } : { y: "100%" };
  const shown = reduce ? { opacity: 1 } : desktop ? { opacity: 1, x: 0 } : { y: 0 };
  const exit = reduce ? { opacity: 0, transition: tween.reduced } : desktop ? { opacity: 0, x: 24, transition: { duration: 0.12 } } : { y: "100%", transition: { duration: 0.18 } };

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          key="helper-sheet"
          ref={ref}
          data-helper-sheet=""
          data-testid="helper-sheet"
          role={desktop ? "complementary" : "dialog"}
          aria-modal={desktop ? undefined : true}
          aria-label={desktop ? t("helper.title") : undefined}
          aria-labelledby={desktop ? undefined : titleId}
          tabIndex={-1}
          onKeyDown={onKeyDown}
          initial={enter}
          animate={shown}
          exit={exit}
          transition={reduce ? tween.reduced : springs.sheet}
          className={cn(
            "helper-sheet fixed z-40 flex flex-col overflow-hidden text-label-1 outline-hidden",
            desktop
              ? "top-16 right-2 bottom-2 w-[360px] rounded-(--radius-lg) glass-regular shadow-elev-2 xl:w-[400px]"
              : "inset-0 z-50 h-dvh bg-(--mat-thick-solid) pt-[env(safe-area-inset-top)]",
          )}
        >
          <SheetBody titleId={titleId} desktop={desktop} onClose={close} />
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
