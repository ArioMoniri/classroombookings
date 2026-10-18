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
 * - HX-19 (audit m11): on phones a 44 px grab handle above the header drags the sheet down 1:1; a release past 30 % or a
 *   flick closes it (focus back to the opener), otherwise it springs back. Exits ≤ 200 ms on `dur`/`ease` tokens,
 *   instant under reduced motion (sheet-drag.ts). ✕ and Esc stay the keyboard / screen-reader path.
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
import { useReduce } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";
import { CardHostContext, pickText, type CardHost } from "./cards/context";
import { AttachButton, SheetDropZone, filesFromPaste, useFilePicker } from "./file-drop";
import { dropLiveStages, forgetEntryFiles, useFileRouter } from "./file-router";
import { EntryView } from "./cards/render";
import { GuideMode } from "./guide";
import { PageContextChip, toTurnContext, usePageContext } from "./page-context";
import { RecentActions } from "./recent";
import { clientActionLabel } from "./remember";
import { useHelperStore } from "./helper-store";
import { helperSheetEnter, helperSheetExit, useHelperSheetDrag, type HelperExitKind } from "./sheet-drag";
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

/** HB18-F10: on a phone the log is bottom-anchored (the first entry takes the free space above it), so the newest
 * card of a short thread and its primary sit just above the field, in thumb reach (M-05), not at the sheet's top. */
function Log({ busy, desktop }: { busy: boolean; desktop: boolean }) {
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
      className={cn("flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto overscroll-contain px-4 py-3", !desktop && "[&>:first-child]:mt-auto")}
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

  // focus on open: the composer (AI) or the guide field (index), on the first frame — never while the sheet is
  // leaving (HX-19: the mode can resolve during the exit and would pull the focus back from the opener to <body>)
  useEffect(() => {
    const id = requestAnimationFrame(() => {
      if (!useHelperStore.getState().open) return;
      // HB-23d DS-05 / UX-08: a control of the sheet that already has the focus (a card handed in from /import, the 📎
      // of "Göster") keeps it
      const a = document.activeElement;
      if (a && a !== document.body && a.closest('[data-testid="helper-sheet"]')) return;
      const field = composerRef.current?.querySelector<HTMLTextAreaElement>("textarea:not([disabled])") ?? guideRef.current;
      field?.focus();
    });
    return () => cancelAnimationFrame(id);
  }, [mode.loading]);

  const role = starterRole(can);
  const empty = entries.length === 0 && !turn.busy;
  // HB-23c: 📎 / paste / drop → the file router (no model; works in Rehber modu too)
  const fileRouter = useFileRouter();
  const attach = (list: File[]) => void fileRouter.attach(list);
  const starterPicker = useFilePicker(attach, { testId: "helper-starter-file-input" });
  const fileStarter = role === "admin" || role === "planner";
  // the palette's "Dosya ekle…" row and the empty-state links open the picker once the sheet is here (the person's
  // activation is still fresh: one frame after their Enter / click)
  const pendingPick = useHelperStore((s) => s.pendingPick);
  const openPicker = starterPicker.open;
  useEffect(() => {
    if (pendingPick && useHelperStore.getState().takePick()) openPicker();
  }, [pendingPick, openPicker]);
  const notes = memory.data?.enabled ? memory.data.notes : 0;
  const guide = !mode.ai || mode.blocked;

  return (
    <CardHostContext.Provider value={host}>
      {/* HB-23d DS-08: at 200 % text the row wraps instead of pushing ✕ / ⋯ off the sheet */}
      <header className="flex min-h-14 shrink-0 flex-wrap items-center gap-2 px-2 py-1 edge-hairline-b [&>:not(h2)]:relative [&>:not(h2)]:z-20 [&>button]:shrink-0">
        {!desktop ? <IconButton label={t("helper.close")} onClick={onClose} data-testid="helper-close" className="size-11"><X aria-hidden /></IconButton> : null}
        <h2 id={titleId} className="type-headline min-w-0 flex-1 truncate pl-2 text-label-1">
          {t("helper.title")}
        </h2>
        <StatusChip mode={mode} />
        <DropdownMenu>
          <DropdownMenuTrigger render={<IconButton label={t("helper.menu")} className="size-11" data-testid="helper-menu"><MoreHorizontal aria-hidden /></IconButton>} />
          <DropdownMenuContent align="end" className="min-w-56">
            <DropdownMenuItem
              onClick={() => {
                dropLiveStages();
                forgetEntryFiles();
                useHelperStore.getState().newThread();
              }}
              data-testid="helper-new-thread"
            >{t("helper.newThread")}</DropdownMenuItem>
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
          {mode.ai && !mode.blocked ? (
            <Starters role={role} onPick={(s) => void askHere(s)} first={fileStarter ? { label: t("helper.file.starter"), onPick: starterPicker.open } : undefined} />
          ) : fileStarter ? (
            <Starters role={role} onPick={() => undefined} only={{ label: t("helper.file.starter"), onPick: starterPicker.open }} />
          ) : null}
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
      {starterPicker.input}
      <SheetDropZone onFiles={attach}>
        <Log busy={turn.busy} desktop={desktop} />
      </SheetDropZone>
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
        {guide ? <AttachButton onFiles={attach} withLabel /> : null}
        <p className="sr-only" role="status" data-testid="helper-context-live">
          {contextLive}
        </p>
        {chipOn && page ? <PageContextChip page={page} onRemove={removeContext} /> : null}
        {mode.ai ? (
          <div
            ref={composerRef}
            data-testid="helper-composer"
            onPaste={(e) => {
              const list = filesFromPaste(e);
              if (!list.length) return;
              e.preventDefault();
              attach(list);
            }}
          >
            <PromptComposer
              onSend={(text) => void askHere(text)}
              busy={turn.busy}
              disabled={mode.blocked}
              placeholder={t("helper.composer.placeholder")}
              label={t("helper.composer.label")}
              sendLabel={t("helper.composer.send")}
              stopLabel={t("helper.composer.stop")}
              leading={<AttachButton onFiles={attach} />}
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

  // HX-19: how the sheet was closed picks its exit (AnimatePresence `custom` reaches the exiting sheet)
  const [exitKind, setExitKind] = useState<HelperExitKind>("close");
  const close = useCallback((kind: HelperExitKind = "close") => {
    const opener = useHelperStore.getState().opener;
    setExitKind(kind);
    useHelperStore.getState().closeSheet();
    requestAnimationFrame(() => returnFocus(opener));
  }, []);
  const drag = useHelperSheetDrag(ref, { reduce, onDismiss: close });
  // a new opening starts from the ✕ exit again (closes from the store — "Git", "Göster", a page change — use it too)
  const [wasOpen, setWasOpen] = useState(open);
  if (wasOpen !== open) {
    setWasOpen(open);
    if (open) setExitKind("close");
  }

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

  // HB-23c (§6.3): any close (✕, Esc, ⌘J, a drag, a page change) deletes the live file stages; a handed-over one is
  // the target page's by then
  useEffect(() => {
    if (!open) dropLiveStages();
  }, [open]);

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
  const variants = { exit: (kind: HelperExitKind) => helperSheetExit(kind, { reduce, desktop }) };

  return (
    <AnimatePresence custom={exitKind}>
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
          exit="exit"
          variants={variants}
          custom={exitKind}
          style={desktop ? undefined : { y: drag.y }}
          transition={helperSheetEnter({ reduce, desktop })}
          className={cn(
            "helper-sheet fixed z-40 flex flex-col overflow-hidden text-label-1 outline-hidden",
            desktop
              ? "top-16 right-2 bottom-2 w-[360px] rounded-(--radius-lg) glass-regular shadow-elev-2 xl:w-[400px]"
              : "inset-0 z-50 h-dvh bg-(--mat-thick-solid) pt-[env(safe-area-inset-top)]",
          )}
        >
          {!desktop ? (
            // HX-19: the grab handle (36 × 5 px pill in a 44 px target); not a Tab stop, ✕ and Esc are the keyboard path
            // a 24 px row; the 44 px target reaches into the header's empty middle, the header's controls sit above it
            <div className="relative h-6 shrink-0">
              <Button
                variant="bare"
                tabIndex={-1}
                aria-label={t("helper.handle")}
                data-testid="helper-handle"
                {...drag.handle}
                className="group absolute top-0 left-1/2 z-10 flex h-11 w-24 -translate-x-1/2 cursor-grab touch-none items-start justify-center pt-2 outline-hidden active:cursor-grabbing"
              >
                <span aria-hidden className="h-1 w-9 rounded-full bg-fill-1 group-data-dragging:bg-label-3" />
              </Button>
            </div>
          ) : null}
          <SheetBody titleId={titleId} desktop={desktop} onClose={() => close()} />
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
