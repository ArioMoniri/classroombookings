"use client";

import { useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useStore } from "zustand";
import { useMe, usePrograms, useRooms, useWeeks } from "@/lib/api/hooks";
import { api } from "@/lib/api/endpoints";
import { DraftConflictError } from "@/lib/api/studio-endpoints";
import { sk, useStudioClasses, useStudioDraft, useStudioMeta, useStudioRules, useStudioSummary } from "@/lib/api/studio-hooks";
import type { ClassRow, Precheck, RulesOut, StudioKind, StudioMeta, StudioStep, StudioSummary } from "@/lib/api/studio-schemas";
import { STUDIO_STEPS } from "@/lib/api/studio-schemas";
import type { Room, Term, Week } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { dayName } from "@/lib/time";
import { useHydrated } from "@/lib/use-hydrated";
import type { RowState } from "./class-filters";
import type { SentenceContext } from "./rule-sentence";
import { deriveSummary, isPlacementPin, patchFor, type DraftLocal, type StudioAction, type StudioState, type SummaryView } from "./studio-reducer";
import { StudioDataContext, type StudioData } from "./studio-data";
import { createStudioStore, type StudioStore, type StudioStoreState } from "./studio-store";

export const ADVANCED_KEY = "smartsched.studio.advanced";

interface StudioContextValue {
  termId: number;
  kind: StudioKind;
  term: Term | undefined;
  store: StudioStore;
  state: StudioState;
  local: DraftLocal;
  dispatch: (a: StudioAction) => void;
  /** wait until every local change is saved (pre-check / generate read the server draft) */
  flush: () => Promise<boolean>;
  meta: StudioMeta | undefined;
  summaryData: StudioSummary | undefined;
  summary: SummaryView;
  classes: ClassRow[] | undefined;
  classesLoading: boolean;
  classesError: boolean;
  rules: RulesOut | undefined;
  rooms: Room[];
  termWeeks: Week[];
  rowState: RowState;
  sentence: SentenceContext;
  step: StudioStep;
  /** switch step; `extra` sets/clears other query params (e.g. `{ rule: "12" }` filters the class list) */
  goStep: (s: StudioStep, extra?: Record<string, string | null>) => void;
  advanced: boolean;
  setAdvanced: (v: boolean) => void;
  isAdmin: boolean;
  precheck: Precheck | null;
  checking: boolean;
  precheckError: string | null;
  runPrecheck: () => Promise<Precheck | null>;
  /** refetch rules + summary + classes after a server-side change */
  refresh: (what?: ("rules" | "classes" | "summary")[]) => Promise<void>;
  /** last step edited (for "Adjust and run again") */
  lastEdited: StudioStep;
}

const StudioContext = createContext<StudioContextValue | null>(null);

export function useStudio(): StudioContextValue {
  const ctx = useContext(StudioContext);
  if (!ctx) throw new Error("useStudio outside <StudioProvider>");
  return ctx;
}

export function useStudioStore<T>(selector: (s: StudioStoreState) => T): T {
  return useStore(useStudio().store, selector);
}

const SAVE_DEBOUNCE_MS = 500;
const PRECHECK_DEBOUNCE_MS = 1500;

export function StudioProvider({ termId, kind, term, children }: { termId: number; kind: StudioKind; term: Term | undefined; children: ReactNode }) {
  const { t, locale } = useI18n();
  const qc = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [store] = useState(createStudioStore);
  const state = useStore(store, (s) => s.studio);
  const precheck = useStore(store, (s) => s.precheck);
  const checking = useStore(store, (s) => s.checking);
  const precheckError = useStore(store, (s) => s.precheckError);

  const me = useMe();
  const meta = useStudioMeta();
  const draft = useStudioDraft(termId, kind);
  const classes = useStudioClasses(termId, kind);
  const rules = useStudioRules(termId, kind);
  const summaryQ = useStudioSummary(termId, kind, state.server?.version);
  const roomsQ = useRooms();
  const weeksQ = useWeeks(termId);
  const programsQ = usePrograms();

  /* ---------------------------------------------------------------- hydrate draft */
  const hydratedFor = useRef<string | null>(null);
  useEffect(() => {
    const key = `${termId}:${kind}`;
    if (draft.data && hydratedFor.current !== key) {
      hydratedFor.current = key;
      store.getState().dispatch({ type: "hydrate", draft: draft.data });
      store.setState({ past: [], future: [], precheck: null });
    }
  }, [draft.data, termId, kind, store]);

  /* ------------------------------------------------------------------- autosave */
  const saving = useRef<Promise<void> | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const saveNow = useCallback(async (): Promise<void> => {
    // loop: edits made while a request is in flight are sent right after it
    for (let round = 0; round < 10; round++) {
    if (saving.current) {
      await saving.current;
    }
    const s = store.getState().studio;
    if (!s.server || s.dirty.length === 0 || s.status === "conflict" || (round > 0 && s.status !== "idle")) return;
    const sent = [...s.dirty];
    const { dispatch } = store.getState();
    dispatch({ type: "saving" });
    const run = (async () => {
      try {
        const d = await api.studio.saveDraft(termId, kind, s.server?.version ?? 0, patchFor(s.local, sent));
        dispatch({ type: "saved", draft: d, sent });
        qc.setQueryData(sk.draft(termId, kind), d);
      } catch (e) {
        if (e instanceof DraftConflictError) dispatch({ type: "conflict", current: e.current });
        else dispatch({ type: "saveFailed", error: e instanceof Error ? e.message : String(e) });
      }
    })();
    saving.current = run;
    await run;
    saving.current = null;
    }
  }, [store, termId, kind, qc]);

  useEffect(
    () =>
      store.subscribe((s, prev) => {
        if (s.studio.dirty === prev.studio.dirty || s.studio.dirty.length === 0) return;
        if (s.studio.status === "conflict" || s.studio.status === "saving") return;
        if (timer.current) clearTimeout(timer.current);
        timer.current = setTimeout(() => void saveNow(), SAVE_DEBOUNCE_MS);
      }),
    [store, saveNow],
  );
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  const flush = useCallback(async (): Promise<boolean> => {
    if (timer.current) clearTimeout(timer.current);
    await saveNow();
    const s = store.getState().studio;
    return s.dirty.length === 0 && s.status !== "conflict" && s.status !== "error";
  }, [saveNow, store]);

  // leaving the page with unsaved edits: send them right away
  useEffect(() => {
    const onHide = () => {
      if (store.getState().studio.dirty.length) void saveNow();
    };
    window.addEventListener("pagehide", onHide);
    return () => window.removeEventListener("pagehide", onHide);
  }, [store, saveNow]);

  /* ------------------------------------------------------------------ pre-check */
  // only the newest request may set the result: an older check answering late must not replace it
  const precheckSeq = useRef(0);
  const runPrecheck = useCallback(async (): Promise<Precheck | null> => {
    const seq = ++precheckSeq.current;
    const ok = await flush();
    if (!ok && store.getState().studio.status === "conflict") {
      if (seq === precheckSeq.current && store.getState().checking) store.getState().setChecking(false);
      return null;
    }
    if (seq !== precheckSeq.current) return null;
    store.getState().setChecking(true);
    try {
      const p = await api.studio.precheck(termId, kind);
      if (seq === precheckSeq.current) store.getState().setPrecheck(p);
      return p;
    } catch (e) {
      if (seq === precheckSeq.current) store.getState().setChecking(false, e instanceof Error ? e.message : String(e));
      return null;
    }
  }, [flush, store, termId, kind]);

  const changeTick = useStore(store, (s) => s.changeTick);
  const hydrated = state.server !== null;
  useEffect(() => {
    if (!hydrated) return;
    const id = setTimeout(() => void runPrecheck(), changeTick === 0 ? 300 : PRECHECK_DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [changeTick, hydrated, runPrecheck]);

  /* ---------------------------------------------------------------------- steps */
  const stepParam = params.get("step");
  const step: StudioStep = (STUDIO_STEPS as readonly string[]).includes(stepParam ?? "") ? (stepParam as StudioStep) : (state.local.last_step ?? "scope");
  const [lastEdited, setLastEdited] = useState<StudioStep>("scope");
  useEffect(() => {
    // remember which step the last edit happened on
    return store.subscribe((s, prev) => {
      if (s.changeTick !== prev.changeTick) {
        const cur = new URLSearchParams(window.location.search).get("step");
        if (cur && cur !== "run" && cur !== "check" && (STUDIO_STEPS as readonly string[]).includes(cur)) setLastEdited(cur as StudioStep);
      }
    });
  }, [store]);

  const goStep = useCallback(
    (s: StudioStep, extra?: Record<string, string | null>) => {
      const next = new URLSearchParams(params.toString());
      next.set("step", s);
      if (s !== "classes") next.delete("rule");
      for (const [k, v] of Object.entries(extra ?? {})) {
        if (v === null) next.delete(k);
        else next.set(k, v);
      }
      router.replace(`${pathname}?${next.toString()}`, { scroll: false });
      store.getState().dispatch({ type: "setStep", step: s });
    },
    [params, router, pathname, store],
  );

  /* ------------------------------------------------------------------ advanced */
  const hydratedClient = useHydrated();
  const [advancedState, setAdvancedState] = useState<boolean | null>(null);
  const advanced = advancedState ?? (params.get("advanced") === "1" || (hydratedClient && window.localStorage.getItem(ADVANCED_KEY) === "1"));
  const setAdvanced = useCallback(
    (v: boolean) => {
      setAdvancedState(v);
      try {
        window.localStorage.setItem(ADVANCED_KEY, v ? "1" : "0");
      } catch {
        /* private mode */
      }
      const next = new URLSearchParams(params.toString());
      if (v) next.set("advanced", "1");
      else next.delete("advanced");
      router.replace(`${pathname}?${next.toString()}`, { scroll: false });
    },
    [params, router, pathname],
  );

  /* -------------------------------------------------------------- derived state */
  const rooms = useMemo(() => roomsQ.data ?? [], [roomsQ.data]);
  const termWeeks = useMemo(() => weeksQ.data ?? [], [weeksQ.data]);
  const rowState = useMemo<RowState>(() => ({ excluded: new Set(state.local.excluded), pinned: new Set(state.local.pins.filter(isPlacementPin).map((p) => p.event_id)) }), [state.local.excluded, state.local.pins]);

  const classById = useMemo(() => new Map((classes.data?.items ?? []).map((c) => [c.id, c])), [classes.data]);
  const sentence = useMemo<SentenceContext>(() => {
    const roomMap = new Map(rooms.map((r) => [r.id, r.display_name]));
    const programNames = (programsQ.data ?? []).map((p) => p.name);
    return {
      locale,
      roomCode: (id) => roomMap.get(id) ?? `#${id}`,
      classLabel: (id) => {
        const c = classById.get(id);
        return c ? `${c.course_code ?? "?"}${c.section_label ? ` §${c.section_label}` : ""}` : `#${id}`;
      },
      programs: programNames.length ? programNames : [...new Set((classes.data?.items ?? []).map((c) => c.program_name).filter((x): x is string => !!x))],
      dayName: (d) => dayName(d, locale),
      tagLabel: (tag) => (["TIP", "PC", "LAB", "AMPHI"].includes(tag) ? t(`rooms.tag.${tag as "TIP"}`) : tag),
      words: {
        allClasses: t("studio.rule.allClasses"),
        nClasses: (n) => t("studio.rule.nClasses", { n }),
        year: (y) => t("studio.classes.yearN", { n: y }),
        choose: t("studio.rule.choose"),
        fromWeek: (w) => t("studio.rule.fromWeek", { n: w }),
        // one week is singular in Turkish ("3. hafta", not "3. haftalar"; usability m2)
        weeks: (w) => (/^\d+$/.test(w) ? t("glass.studio.oneWeek", { w }) : t("studio.rule.weeks", { w })),
      },
    };
  }, [rooms, programsQ.data, classById, classes.data, locale, t]);

  const summary = useMemo(
    () =>
      deriveSummary({
        local: state.local,
        dirty: state.dirty.length > 0,
        server: state.server,
        sameContent: state.sameContent,
        summary: summaryQ.data ?? null,
        classes: classes.data?.items ?? null,
        rules: rules.data?.rules ?? null,
        termWeeks,
        precheck,
        checking,
      }),
    [state.local, state.dirty.length, state.server, state.sameContent, summaryQ.data, classes.data, rules.data, termWeeks, precheck, checking],
  );

  const refresh = useCallback(
    async (what: ("rules" | "classes" | "summary")[] = ["rules", "classes", "summary"]) => {
      await Promise.all(
        what.map((w) => qc.invalidateQueries({ queryKey: w === "rules" ? sk.rules(termId, kind) : w === "classes" ? sk.classes(termId, kind) : sk.summary(termId, kind) })),
      );
      store.getState().touch();
    },
    [qc, termId, kind, store],
  );

  const value: StudioContextValue = {
    termId,
    kind,
    term,
    store,
    state,
    local: state.local,
    dispatch: store.getState().dispatch,
    flush,
    meta: meta.data,
    summaryData: summaryQ.data,
    summary,
    classes: classes.data?.items,
    classesLoading: classes.isLoading,
    classesError: classes.isError,
    rules: rules.data,
    rooms,
    termWeeks,
    rowState,
    sentence,
    step,
    goStep,
    advanced,
    setAdvanced,
    isAdmin: me.data?.role === "ADMIN",
    precheck,
    checking,
    precheckError,
    runPrecheck,
    refresh,
    lastEdited,
  };
  const data = useMemo<StudioData>(() => ({ rooms, classes: classes.data?.items, termWeeks, sentence, advanced }), [rooms, classes.data, termWeeks, sentence, advanced]);
  return (
    <StudioContext.Provider value={value}>
      <StudioDataContext.Provider value={data}>{children}</StudioDataContext.Provider>
    </StudioContext.Provider>
  );
}
