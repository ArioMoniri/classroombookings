"use client";
/**
 * HB-23c (helper-file-router.md §8.4, §9, §10; owner decision: every signed-in desktop page): the page's quiet **edge
 * target**. When an OS file drag enters the window and the pointer is not over a local drop zone (the sheet's log, the
 * import / onboarding zones, a file input), the viewport gets an inset 2 px tint outline and a pill at the top centre
 * ("Yardımcıya bırakın: ne olduğunu söyleyeyim"). Dropping opens the helper sheet and classifies the file.
 *
 * - Instant on and off (motion.md §3.8: an OS file is not our element); Esc or leaving the window clears it.
 * - No focus stop and no button: it is only a hint. The 📎 in the helper is the keyboard path (§10).
 * - Fine pointers only (phones have no OS drag). Hidden on kiosk, slot display, `/public/**`, `?embed=1`, `/setup`,
 *   `/login`, `/welcome`, signed out, or when the helper is off for the person.
 * - Solid fill, no blur (the blur budget stays shell bar + sheet).
 * Mounted once in app-shell.tsx. The router (classify, cards) is fetched on the first drop only.
 */
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { useHelperStatus } from "@/lib/api/helper";
import { useMeFull, usePermissions } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";
import { useFinePointer } from "@/lib/motion";
import { useHelperStore } from "./helper-store";

/** routes that never show the edge target (signed-out, public, setup and display surfaces) */
const HIDDEN = /^\/(public|setup|login|welcome|kiosk|display)(\/|$)/;

/** Elements that take a file themselves: the page target steps aside over them. */
export const LOCAL_DROP = "[data-local-drop],[data-helper-sheet],[data-testid=import-dropzone],[data-testid=onboarding-drop],input[type=file]";

const isFileDrag = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");
const overLocal = (e: Event) => e.target instanceof Element && !!e.target.closest(LOCAL_DROP);

export function pageTargetHidden(pathname: string, params: URLSearchParams): boolean {
  return HIDDEN.test(pathname) || params.get("embed") === "1" || params.get("kiosk") === "1";
}

function Target() {
  const { t, locale } = useI18n();
  const pathname = usePathname();
  const params = useSearchParams();
  const me = useMeFull();
  const status = useHelperStatus(!!me.data);
  const { can } = usePermissions();
  const fine = useFinePointer();
  const enabled = !!me.data && status.data?.enabled !== false && fine && !pageTargetHidden(pathname, params);
  const [shown, setShown] = useState(false);
  const depth = useRef(0);
  const canRef = useRef(can);
  const langRef = useRef(locale);
  useEffect(() => {
    canRef.current = can;
    langRef.current = locale;
  });

  useEffect(() => {
    if (!enabled) return;
    const clear = () => {
      depth.current = 0;
      setShown(false);
    };
    const onEnter = (e: DragEvent) => {
      if (!isFileDrag(e)) return;
      depth.current += 1;
      setShown(!overLocal(e) && !e.defaultPrevented);
    };
    const onOver = (e: DragEvent) => {
      if (!isFileDrag(e)) return;
      // a local zone handles its own drop (it prevents the default first)
      if (e.defaultPrevented || overLocal(e)) {
        setShown(false);
        return;
      }
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
      setShown(true);
    };
    const onLeave = (e: DragEvent) => {
      if (!isFileDrag(e)) return;
      depth.current = Math.max(0, depth.current - 1);
      // leaving the window: no related target, or the counter is back to 0
      if (depth.current === 0 || !e.relatedTarget) clear();
    };
    const onDrop = (e: DragEvent) => {
      if (!isFileDrag(e)) return;
      clear();
      if (e.defaultPrevented || overLocal(e)) return;
      // never let the browser navigate to the file
      e.preventDefault();
      const list = Array.from(e.dataTransfer?.files ?? []);
      if (!list.length) return;
      const st = useHelperStore.getState();
      if (!st.open) st.openSheet();
      void import("./file-router").then((m) => m.attachFiles(list, { can: canRef.current, lang: langRef.current }));
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") clear();
    };
    window.addEventListener("dragenter", onEnter);
    window.addEventListener("dragover", onOver);
    window.addEventListener("dragleave", onLeave);
    window.addEventListener("drop", onDrop);
    window.addEventListener("dragend", clear);
    window.addEventListener("keydown", onKey);
    window.addEventListener("blur", clear);
    return () => {
      window.removeEventListener("dragenter", onEnter);
      window.removeEventListener("dragover", onOver);
      window.removeEventListener("dragleave", onLeave);
      window.removeEventListener("drop", onDrop);
      window.removeEventListener("dragend", clear);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("blur", clear);
    };
  }, [enabled]);

  if (!enabled || !shown) return null;
  return (
    <div
      aria-hidden
      data-testid="page-file-target"
      className="pointer-events-none fixed inset-0 z-[45] outline-2 -outline-offset-2 outline-solid outline-tint forced-colors:outline-[Highlight]"
    >
      <p className="absolute top-3 left-1/2 flex h-9 -translate-x-1/2 items-center rounded-full bg-(--mat-thick-solid) px-4 type-callout whitespace-nowrap text-label-1 shadow-elev-2 edge-hairline">
        {t("helper.file.dropPage")}
      </p>
    </div>
  );
}

export function PageFileTarget() {
  return (
    <Suspense fallback={null}>
      <Target />
    </Suspense>
  );
}
