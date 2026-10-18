"use client";
/**
 * HX-07 (helper.md §3.3, §11 D): "Göster" — a 1-step tour on the welcome guide's spotlight ring. Navigate to the
 * feature's page, wait ≤ 3 s for its `[data-tour]` anchor, scroll it to the centre, ring it and show one step card
 * ("Anladım" / "Yardımcıya dön"). The target stays interactive (the ring and the card never cover it). On phones
 * the sheet closed first and the card is docked at the bottom. A missing anchor shows the path and "Bu düğme şu an
 * bu sayfada görünmüyor." Esc or "Anladım" ends it with the focus on the target; reduced motion: the ring jumps.
 */
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { useMediaQuery } from "@/components/ui/use-media-query";
import { SpotlightRing } from "@/components/welcome/tour/spotlight-ring";
import { isFocusable, waitForAnchor } from "@/components/welcome/tour/anchors";
import { useI18n } from "@/lib/i18n/provider";
import { useReduce } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { featureById, pathLine } from "./feature-links";
import { useHelperStore } from "./helper-store";
import { DESKTOP_SHEET } from "./helper-sheet";

type Found = { state: "waiting" } | { state: "found"; el: HTMLElement } | { state: "missing" };

export function ShowMeHost() {
  const req = useHelperStore((s) => s.showMe);
  // a new request remounts the step (fresh wait, fresh state)
  return req ? <ShowMe key={req.n} featureId={req.featureId} /> : null;
}

function ShowMe({ featureId }: { featureId: string }) {
  const { t, locale } = useI18n();
  const router = useRouter();
  const pathname = usePathname();
  const reduce = useReduce();
  const desktop = useMediaQuery(DESKTOP_SHEET);
  const entry = featureById(featureId);
  const [found, setFound] = useState<Found>({ state: "waiting" });
  const textId = useId();
  const cardRef = useRef<HTMLDivElement>(null);
  const target = found.state === "found" ? found.el : null;

  // navigate, then wait for the anchor
  useEffect(() => {
    if (!entry) return;
    const [path] = entry.route.split("#");
    if (path && path !== pathname) router.push(entry.route);
    if (!entry.anchor) {
      setFound({ state: "missing" });
      return;
    }
    const ctrl = new AbortController();
    void waitForAnchor(entry.anchor, 3000, ctrl.signal).then((el) => {
      if (ctrl.signal.aborted) return;
      if (!el) return setFound({ state: "missing" });
      el.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
      setFound({ state: "found", el });
    });
    return () => ctrl.abort();
    // the request is fixed for this mount (keyed by the host)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // the target names its step; the global shortcuts pause like during a tour
  useEffect(() => {
    if (!target) return;
    const before = target.getAttribute("aria-describedby");
    target.setAttribute("aria-describedby", [before, textId].filter(Boolean).join(" "));
    return () => {
      if (before) target.setAttribute("aria-describedby", before);
      else target.removeAttribute("aria-describedby");
    };
  }, [target, textId]);

  useEffect(() => {
    if (found.state === "waiting") return;
    cardRef.current?.querySelector<HTMLElement>("[data-step-primary]")?.focus();
  }, [found.state]);

  const end = (back: boolean) => {
    useHelperStore.getState().endShowMe();
    if (back) {
      useHelperStore.getState().openSheet({ opener: target && isFocusable(target) ? target : null });
      return;
    }
    if (target && isFocusable(target)) target.focus();
    else (document.querySelector<HTMLElement>("main h1") ?? document.getElementById("main"))?.focus();
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      end(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (!entry) return null;
  const title = entry.title[locale] ?? entry.title.tr;
  const path = pathLine(entry.path, locale);
  return (
    <>
      {target ? <SpotlightRing target={target} reduceMotion={reduce} /> : null}
      {found.state !== "waiting" ? (
        <div
          ref={cardRef}
          role="dialog"
          aria-modal={false}
          aria-labelledby={`${textId}-t`}
          aria-describedby={textId}
          data-testid="helper-step"
          className={cn(
            "helper-step fixed z-[10003] flex flex-col gap-3 rounded-(--radius-lg) bg-(--mat-thick-solid) p-4 text-label-1 shadow-elev-2 edge-hairline",
            desktop ? "bottom-6 left-1/2 w-[min(22rem,calc(100vw-2rem))] -translate-x-1/2" : "inset-x-2 bottom-[max(0.5rem,env(safe-area-inset-bottom))] min-h-[200px]",
          )}
        >
          <p id={`${textId}-t`} className="type-headline">
            {title}
          </p>
          <div id={textId} className="flex flex-col gap-1 type-callout text-label-2">
            {path ? <p>{path}</p> : null}
            {found.state === "missing" ? <p data-testid="helper-step-missing">{t("helper.where.missing")}</p> : null}
          </div>
          <div className="mt-auto flex flex-wrap gap-2 max-sm:flex-col max-sm:items-stretch">
            <Button size="md" className="max-sm:h-12" data-step-primary="" onClick={() => end(false)} data-testid="helper-step-done">
              {t("helper.where.gotIt")}
            </Button>
            <Button size="md" variant="secondary" className="max-sm:h-12" onClick={() => end(true)} data-testid="helper-step-back">
              {t("helper.where.back")}
            </Button>
          </div>
        </div>
      ) : null}
    </>
  );
}
