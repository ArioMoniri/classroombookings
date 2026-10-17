"use client";
/**
 * Runs a guided tour (spec §4.2). Loaded with next/dynamic only when a tour starts (with the Joyride adapter in the
 * same chunk), so neither is in the first-load JS of any page.
 *
 * Per step: go to its `route` if needed (router.push), wait for the `[data-tour]` anchor (≤ 3 s), scroll it to the
 * centre, then draw the card and the ring. A missing anchor skips the step with a console warning. Events: `started`,
 * `step`, `completed` ("Bitir"), `dismissed` with the step (Esc / "Turu bitir"); none in an admin preview.
 * While it runs, html[data-tour-running] pauses the global shortcuts and ⌘K. Afterwards focus goes to the step's
 * target (Esc, when focusable) or the page's h1, never to <body>.
 */
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useMediaQuery } from "@/components/ui/use-media-query";
import { useWelcomeEvent } from "@/lib/api/welcome";
import { useI18n } from "@/lib/i18n/provider";
import { useReduce } from "@/lib/motion";
import { useUiStore } from "@/stores/ui";
import { focusPageHeading, useWelcomeStore, type TourRequest } from "../welcome-store";
import { TOUR_RUNNING_ATTR, isFocusable, waitForAnchor } from "./anchors";
import type { EngineStep } from "./engine";
import JoyrideAdapter from "./joyride-adapter";
import { SpotlightRing } from "./spotlight-ring";
import { HEADING_FALLBACK, samePath, stepCopy } from "./steps";

const DOCKED = "(max-width: 639.98px)";
const SIDEBAR = "(min-width: 1024px)";

export function TourRunner({ request }: { request: TourRequest }) {
  const { steps, preview } = request;
  const { t } = useI18n();
  const router = useRouter();
  const pathname = usePathname();
  const reduce = useReduce();
  const docked = useMediaQuery(DOCKED);
  const sidebar = useMediaQuery(SIDEBAR);
  const endTour = useWelcomeStore((s) => s.endTour);
  const event = useWelcomeEvent();
  const [index, setIndex] = useState(0);
  const [active, setActive] = useState<{ index: number; step: EngineStep } | null>(null);
  const [live, setLive] = useState("");
  const dir = useRef(1);
  const finished = useRef(false);
  const latest = useRef({ active, index, pathname });
  useEffect(() => {
    latest.current = { active, index, pathname };
  });

  const post = useCallback((e: Parameters<typeof event.mutate>[0]) => {
    if (!preview) event.mutate(e);
  }, [preview, event]);

  const finish = useCallback(
    (reason: "completed" | "dismissed") => {
      if (finished.current) return;
      finished.current = true;
      const { active: a, index: i } = latest.current;
      post(reason === "completed" ? { guide_key: "tour", event: "completed" } : { guide_key: "tour", event: "dismissed", step: i });
      const target = a?.step.target ?? null;
      endTour();
      toast(reason === "completed" ? t(sidebar ? "welcome.tour.done" : "welcome.tour.donePhone") : t("welcome.tour.ended"));
      // after the engine's own cleanup (its focus trap restores the element focused when the step opened)
      window.setTimeout(() => {
        if (reason === "dismissed" && isFocusable(target) && target.offsetParent !== null) target.focus();
        else focusPageHeading();
      }, 60);
    },
    [endTour, post, sidebar, t],
  );

  // pause the shortcuts and ⌘K, close the palette and the phone drawer
  useEffect(() => {
    document.documentElement.setAttribute(TOUR_RUNNING_ATTR, "");
    useUiStore.getState().setPaletteOpen(false);
    useUiStore.getState().setDrawerOpen(false);
    post({ guide_key: "tour", event: "started" });
    return () => document.documentElement.removeAttribute(TOUR_RUNNING_ATTR);
    // once per tour
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // resolve the current step: route, anchor (≤ 3 s), scroll, then show
  useEffect(() => {
    const step = steps[index];
    if (!step) {
      finish("completed");
      return;
    }
    const ctrl = new AbortController();
    void (async () => {
      if (step.route && !samePath(window.location.pathname, step.route)) router.push(step.route);
      let target = await waitForAnchor(step.anchor, 3000, ctrl.signal);
      let empty = false;
      if (ctrl.signal.aborted) return;
      if (!target && HEADING_FALLBACK.has(step.anchor)) {
        target = document.querySelector<HTMLElement>("main h1");
        empty = !!target;
      }
      if (!target) {
        console.warn(`[welcome] tour step skipped: no [data-tour="${step.anchor}"] on ${window.location.pathname}`);
        const next = index + dir.current;
        if (next < 0 || next >= steps.length) finish(next < 0 ? "dismissed" : "completed");
        else setIndex(next);
        return;
      }
      target.scrollIntoView({ block: "center", inline: "nearest", behavior: reduce ? "auto" : "smooth" });
      const copy = stepCopy(step, t, { empty });
      setActive({ index, step: { id: step.anchor, target, title: copy.title, body: copy.body, interactive: step.interactive } });
      setLive(t("welcome.tour.live", { n: index + 1, total: steps.length, title: copy.title }));
      post({ guide_key: "tour", event: "step", step: index });
    })();
    return () => ctrl.abort();
    // a step resolves once per index
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index]);

  // the target is described by the step body while the step is active
  useEffect(() => {
    if (!active) return;
    const el = active.step.target;
    const before = el.getAttribute("aria-describedby");
    const id = document.querySelector('[data-testid="tour-card"] p[id]')?.id;
    if (id) el.setAttribute("aria-describedby", before ? `${before} ${id}` : id);
    return () => {
      if (before === null) el.removeAttribute("aria-describedby");
      else el.setAttribute("aria-describedby", before);
    };
  }, [active]);

  // Esc = "Turu bitir" (before any other handler: the card's dialog role must not let it reach the page)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      e.stopPropagation();
      finish("dismissed");
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [finish]);

  const controls = {
    index,
    total: steps.length,
    next: () => {
      if (index + 1 >= steps.length) finish("completed");
      else {
        dir.current = 1;
        setIndex(index + 1);
      }
    },
    back: () => {
      if (index === 0) return;
      dir.current = -1;
      setIndex(index - 1);
    },
    end: () => finish("dismissed"),
  };

  return (
    <>
      <p className="sr-only" aria-live="polite" data-testid="tour-live">
        {live}
      </p>
      {active && active.index === index ? (
        <>
          <SpotlightRing target={active.step.target} reduceMotion={reduce} />
          <JoyrideAdapter step={active.step} controls={controls} docked={docked} reduceMotion={reduce} />
        </>
      ) : null}
    </>
  );
}

export default TourRunner;
