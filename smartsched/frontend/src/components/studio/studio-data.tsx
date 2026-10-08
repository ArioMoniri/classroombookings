"use client";

import { createContext, useContext } from "react";
import type { ClassRow } from "@/lib/api/studio-schemas";
import type { Room, Week } from "@/lib/api/schemas";
import { dayName } from "@/lib/time";
import type { SentenceContext } from "./rule-sentence";

/** Reference data the slot pickers need (rooms, classes, programmes, weeks). Kept separate from the
 * studio context so rule cards render in tests with a plain provider (or the defaults below). */
export interface StudioData {
  rooms: Room[];
  classes: ClassRow[] | undefined;
  termWeeks: Week[];
  sentence: SentenceContext;
  advanced: boolean;
}

export const fallbackSentence: SentenceContext = {
  locale: "en",
  roomCode: (id) => `#${id}`,
  classLabel: (id) => `#${id}`,
  programs: [],
  dayName: (d) => dayName(d, "en"),
  tagLabel: (t) => t,
  words: { allClasses: "all classes", nClasses: (n) => `${n} classes`, year: (y) => `year ${y}`, choose: "choose…", fromWeek: (w) => `week ${w}`, weeks: (w) => `weeks ${w}` },
};

export const StudioDataContext = createContext<StudioData>({ rooms: [], classes: [], termWeeks: [], sentence: fallbackSentence, advanced: false });

export function useStudioData(): StudioData {
  return useContext(StudioDataContext);
}
