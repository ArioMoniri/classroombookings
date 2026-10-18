"use client";
/** HX-04: what every card needs from its host (the sheet): the runner, the reader's rights and the navigation. */
import { createContext, useContext } from "react";
import type { Locale } from "@/lib/i18n";
import type { Runner } from "../use-helper-runner";

export interface CardHost {
  runner: Runner;
  locale: Locale;
  /** the nav's permission check (any-of) */
  can: (perm: string | readonly string[] | undefined) => boolean;
  /** registry actions this person may run (`GET /helper/actions`); null while unknown */
  actions: ReadonlySet<string> | null;
  /** the action's own verb ("Rezerve et") from `GET /helper/actions` */
  actionVerb: (action: string) => string | null;
  /** open an in-app route (closes the phone sheet) */
  go: (href: string) => void;
  /** "Göster": navigate and ring the feature's control */
  showMe: (featureId: string) => void;
  /** "Menüde ara": the palette with this text */
  searchMenu: (q?: string) => void;
  textOnly: boolean;
}

export const CardHostContext = createContext<CardHost | null>(null);

export function useCardHost(): CardHost {
  const host = useContext(CardHostContext);
  if (!host) throw new Error("helper cards need a CardHostContext");
  return host;
}

/** `{tr, en}` → the reader's language (Turkish when the other is missing). */
export function pickText(t: { tr: string; en: string } | null | undefined, locale: Locale): string {
  if (!t) return "";
  return (locale === "en" ? t.en : t.tr) || t.tr || t.en;
}
