"use client";
/**
 * The helper's one shell mount (helper.md §13): the sheet, the "Göster" spotlight and ⌘J / Ctrl+J. Nothing renders
 * in kiosk or embed views, while a welcome tour runs (⌘J pauses like ⌘K), or when an administrator switched the
 * helper off for this person (`GET /helper/status` → `enabled: false`). On a run page (`/runs/<id>`) ⌘J stays the
 * run chat's (motion.md §3.6); the helper is still reachable through ⌘K › "Yardımcıya sor".
 */
import dynamic from "next/dynamic";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { useHelperStatus } from "@/lib/api/helper";
import { useMeFull } from "@/lib/api/shell-extra";
import { useHelperStore } from "./helper-store";
import "./helper.css";

// F-CH-1: the sheet (cards, runner, schemas) and the "Göster" spotlight are their own chunks, fetched the first
// time the helper opens or a spotlight starts; they stay mounted afterwards (close animation, conversation)
const HelperSheet = dynamic(() => import("./helper-sheet").then((m) => m.HelperSheet), { ssr: false });
const ShowMeHost = dynamic(() => import("./show-me").then((m) => m.ShowMeHost), { ssr: false });

const RUN_PAGE = /^\/runs\/\d+/;

export function isHelperShortcut(e: KeyboardEvent): boolean {
  return (e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "j";
}

function Root() {
  const pathname = usePathname();
  const params = useSearchParams();
  const me = useMeFull();
  const status = useHelperStatus(!!me.data);
  const hidden = params.get("embed") === "1" || params.get("kiosk") === "1";
  const enabled = !!me.data && status.data?.enabled !== false && !hidden;
  const open = useHelperStore((s) => s.open);
  const spotlight = useHelperStore((s) => s.showMe !== null);
  const [opened, setOpened] = useState(open);
  if (open && !opened) setOpened(true);
  const [shown, setShown] = useState(spotlight);
  if (spotlight && !shown) setShown(true);

  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (!isHelperShortcut(e) || e.defaultPrevented) return;
      if (document.documentElement.hasAttribute("data-tour-running")) return;
      if (RUN_PAGE.test(window.location.pathname)) return;
      e.preventDefault();
      const st = useHelperStore.getState();
      if (st.open) st.closeSheet();
      else st.openSheet();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled]);

  // switched off while open: close
  useEffect(() => {
    if (!enabled && useHelperStore.getState().open) useHelperStore.getState().closeSheet();
  }, [enabled, pathname]);

  if (!enabled) return null;
  return (
    <>
      {opened || open ? <HelperSheet /> : null}
      {shown || spotlight ? <ShowMeHost /> : null}
    </>
  );
}

export function HelperRoot() {
  return (
    <Suspense fallback={null}>
      <Root />
    </Suspense>
  );
}
