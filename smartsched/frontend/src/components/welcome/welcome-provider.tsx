"use client";
/**
 * WelcomeProvider (spec §6, WG-04): mounted once in the app shell.
 *
 * - Fetches `GET /welcome` for a signed-in user, never on `/setup`, `/login`, `/welcome`, `/reset-password`,
 *   `/public/**`, the slot display or a `?kiosk=1` / `?embed=1` / `?print=1` page (no call at all there).
 * - Renders only what the server's `show` says, at most one automatic surface per session
 *   (`sessionStorage["ss.welcome.auto"]`): the sheet (first sign-in, snooze due, role change "delta", "show again"),
 *   or one hint. The sheet only auto-shows on a home page (a deep link from an e-mail is never interrupted) and
 *   waits while another dialog is open (the privacy notice, a confirm…).
 * - Writes the events (shown / snoozed / dismissed / completed …) and starts the tour, which is loaded lazily.
 * - Posts `item_done` for a view-only checklist item when its page is opened.
 */
import dynamic from "next/dynamic";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useMeFull } from "@/lib/api/shell-extra";
import { useWelcome, useWelcomeEvent } from "@/lib/api/welcome";
import { useHydrated } from "@/lib/use-hydrated";
import { HOME_ROUTES, isExcludedRoute } from "./content";
import { ChecklistSheet } from "./checklist/checklist-sheet";
import { FeatureHintPopover } from "./hints/feature-hint";
import { buildChecklist, buildSheet, buildSteps } from "./model";
import { samePath } from "./tour/steps";
import { WelcomeSheet, type SheetAction } from "./welcome-sheet";
import { autoBudgetFree, focusPageHeading, otherDialogOpen, spendAutoBudget, useWelcomeStore } from "./welcome-store";

/** the tour runner and react-joyride: their own chunk, fetched when a tour starts */
const TourRunner = dynamic(() => import("./tour/tour-runner").then((m) => m.TourRunner), { ssr: false, loading: () => null });

const FIRST_KEY = "ss.welcome.first";
/** the first route of this browser session (sent as `first_route`, so the server can suppress deep links) */
function firstRouteOf(pathname: string): string {
  try {
    const known = window.sessionStorage.getItem(FIRST_KEY);
    if (known) return known;
    window.sessionStorage.setItem(FIRST_KEY, pathname);
  } catch {
    /* private mode */
  }
  return pathname;
}

function WelcomeHost() {
  const pathname = usePathname();
  const search = useSearchParams();
  const router = useRouter();
  const hydrated = useHydrated();
  const me = useMeFull();
  const excluded = isExcludedRoute(pathname, search);
  const firstRoute = useMemo(() => (hydrated ? firstRouteOf(pathname) : pathname), [hydrated, pathname]);
  const q = useWelcome({ enabled: hydrated && !excluded && !!me.data, firstRoute });
  const data = excluded ? undefined : q.data;
  const event = useWelcomeEvent();
  const sheetReq = useWelcomeStore((s) => s.sheet);
  const tourReq = useWelcomeStore((s) => s.tour);
  const openSheet = useWelcomeStore((s) => s.openSheet);
  const closeSheet = useWelcomeStore((s) => s.closeSheet);
  const startTour = useWelcomeStore((s) => s.startTour);
  const setAutoHint = useWelcomeStore((s) => s.setAutoHint);
  const setChecklistOpen = useWelcomeStore((s) => s.setChecklistOpen);
  const localDone = useWelcomeStore((s) => s.localDone);
  const markLocalDone = useWelcomeStore((s) => s.markLocalDone);

  // the one automatic surface of this session
  const show = data?.show;
  const showKey = show ? `${show.kind}:${show.key ?? ""}` : "";
  useEffect(() => {
    if (!data || !show || excluded) return;
    if (!autoBudgetFree()) return;
    const state = useWelcomeStore.getState();
    if (state.sheet || state.tour) return;
    const isSheet = show.kind === "sheet" || show.kind === "delta";
    if (isSheet && (!data.enabled.sheet || !HOME_ROUTES.includes(pathname))) return;
    if (!isSheet && !data.enabled.hints) return;
    let tries = 0;
    const id = window.setInterval(() => {
      if (otherDialogOpen()) {
        if (++tries > 75) window.clearInterval(id); // ~30 s, then give up for this page view
        return;
      }
      window.clearInterval(id);
      if (!autoBudgetFree()) return;
      if (isSheet) {
        spendAutoBudget("sheet");
        openSheet({ mode: "auto", kind: show.kind === "delta" ? "delta" : "sheet", deltaAudiences: show.audiences ?? undefined });
        event.mutate({ guide_key: "sheet", event: "shown" });
      } else if (show.key) {
        spendAutoBudget(`hint:${show.key}`);
        setAutoHint(show.key);
      }
    }, 400);
    return () => window.clearInterval(id);
    // keyed on the decision, not on every refetch
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showKey, pathname, excluded, !!data]);

  // view-only checklist items tick when their page is opened
  const checklist = buildChecklist(data, new Set(localDone));
  useEffect(() => {
    if (!checklist || !data?.enabled.checklist) return;
    for (const item of checklist.items) {
      if (item.manual && !item.done && samePath(item.href, pathname)) {
        markLocalDone(item.key);
        event.mutate({ guide_key: "checklist", event: "item_done", item: item.key });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname, !!checklist]);

  // the last request stays rendered while the dialog plays its exit
  const [lastReq, setLastReq] = useState(sheetReq);
  if (sheetReq && sheetReq !== lastReq) setLastReq(sheetReq);
  const req = sheetReq ?? lastReq;
  const preview = req?.mode === "preview";
  const model = req
    ? req.mode === "preview"
      ? buildSheet(data, { previewAudience: req.audience, previewOverrides: req.overrides })
      : buildSheet(data, { kind: req.kind, deltaAudiences: req.deltaAudiences })
    : null;

  const onAction = (a: SheetAction) => {
    const post = (e: "snoozed" | "dismissed" | "completed") => {
      if (!preview) event.mutate({ guide_key: "sheet", event: e });
    };
    const current = sheetReq;
    closeSheet();
    switch (a.type) {
      case "later":
        post("snoozed");
        return;
      case "never":
        post("dismissed");
        return;
      case "start": {
        post("completed");
        const steps = current?.mode === "preview" ? buildSteps(undefined, { previewAudience: current.audience }) : buildSteps(data);
        // after the sheet's exit (150 ms), so the tour's first card takes focus from a settled page
        if (steps.length) window.setTimeout(() => startTour({ steps, preview }), 200);
        return;
      }
      case "checklist":
        post("completed");
        window.setTimeout(() => setChecklistOpen(true), 200);
        return;
      case "card":
        post("completed");
        if (preview) return;
        router.push(a.card.href);
        focusPageHeading(3000);
        return;
    }
  };

  return (
    <>
      {model ? (
        <WelcomeSheet
          open={!!sheetReq}
          model={model}
          state={data}
          tourEnabled={preview ? true : !!data?.enabled.tour}
          checklistEnabled={preview ? false : !!data?.enabled.checklist}
          preview={preview}
          onAction={onAction}
        />
      ) : null}
      {tourReq ? <TourRunner request={tourReq} /> : null}
      {data ? <ChecklistSheet /> : null}
      {data ? <FeatureHintPopover /> : null}
    </>
  );
}

export function WelcomeProvider() {
  return (
    <Suspense fallback={null}>
      <WelcomeHost />
    </Suspense>
  );
}
