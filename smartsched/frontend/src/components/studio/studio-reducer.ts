/**
 * Local studio draft state + the "What will happen" summary derivation. Pure functions so the
 * autosave hook, the panels and the tests share one source of truth.
 *
 * The draft lives on the server (GET/PUT /terms/{id}/studio). The UI edits a local copy and records
 * which fields are dirty; the saver sends only those fields with the server `version` (optimistic
 * concurrency, 409 → conflict banner).
 */
import type { Draft, DraftParams, DraftPatch, HorizonParams, Pin, Precheck, Readiness, RuleOverride, StudioRule, StudioStep, StudioSummary } from "@/lib/api/studio-schemas";
import type { Week } from "@/lib/api/schemas";

export type Horizon = "WEEK" | "MONTH" | "TERM";

export interface DraftLocal {
  horizon: Horizon;
  horizon_params: HorizonParams;
  excluded: number[];
  pins: Pin[];
  disabled_builtin_kinds: string[];
  disabled_rule_ids: number[];
  rule_overrides: Record<string, RuleOverride>;
  params: DraftParams;
  last_step: StudioStep | null;
  preset_id: number | null;
}

export type DraftField = keyof DraftPatch;

export interface StudioState {
  /** last server copy (null until the first GET) */
  server: Draft | null;
  local: DraftLocal;
  dirty: DraftField[];
  status: "idle" | "saving" | "saved" | "error" | "conflict";
  error: string | null;
  conflict: Draft | null;
}

export type StudioAction =
  | { type: "hydrate"; draft: Draft }
  | { type: "setScope"; horizon?: Horizon; horizon_params?: HorizonParams }
  | { type: "exclude"; ids: number[] }
  | { type: "include"; ids: number[] }
  | { type: "setExcluded"; ids: number[] }
  | { type: "setPin"; pin: Pin }
  | { type: "unpin"; eventId: number }
  | { type: "setOverride"; ruleId: number; override: RuleOverride | null }
  | { type: "setRuleInPlay"; ruleId: number; inPlay: boolean }
  | { type: "setBuiltin"; kind: string; enabled: boolean }
  | { type: "setParams"; params: Partial<DraftParams> }
  | { type: "setStep"; step: StudioStep }
  | { type: "saving" }
  | { type: "saved"; draft: Draft; sent: DraftField[] }
  | { type: "saveFailed"; error: string }
  | { type: "conflict"; current: Draft }
  | { type: "keepMine"; current: Draft };

export const EMPTY_LOCAL: DraftLocal = {
  horizon: "WEEK",
  horizon_params: {},
  excluded: [],
  pins: [],
  disabled_builtin_kinds: [],
  disabled_rule_ids: [],
  rule_overrides: {},
  params: {},
  last_step: null,
  preset_id: null,
};

export const initialStudioState: StudioState = { server: null, local: EMPTY_LOCAL, dirty: [], status: "idle", error: null, conflict: null };

export function localFromDraft(d: Draft): DraftLocal {
  return {
    horizon: d.scope.horizon,
    horizon_params: d.scope.horizon_params ?? {},
    excluded: [...d.excluded_event_ids],
    pins: d.pins.map((p) => ({ ...p })),
    disabled_builtin_kinds: [...d.disabled_builtin_kinds],
    disabled_rule_ids: [...d.disabled_rule_ids],
    rule_overrides: { ...d.rule_overrides },
    params: { ...d.params },
    last_step: d.last_step ?? null,
    preset_id: d.preset_id ?? null,
  };
}

const uniq = (xs: number[]) => [...new Set(xs)];
const mark = (dirty: DraftField[], ...fields: DraftField[]): DraftField[] => [...new Set([...dirty, ...fields])];

function edit(state: StudioState, local: DraftLocal, ...fields: DraftField[]): StudioState {
  return { ...state, local, dirty: mark(state.dirty, ...fields), status: state.status === "conflict" ? "conflict" : state.status };
}

export function studioReducer(state: StudioState, action: StudioAction): StudioState {
  const l = state.local;
  switch (action.type) {
    case "hydrate":
      return { server: action.draft, local: localFromDraft(action.draft), dirty: [], status: "idle", error: null, conflict: null };
    case "setScope":
      return edit(
        state,
        { ...l, horizon: action.horizon ?? l.horizon, horizon_params: action.horizon_params ?? l.horizon_params },
        ...(action.horizon ? (["horizon"] as const) : []),
        ...(action.horizon_params ? (["horizon_params"] as const) : []),
      );
    case "exclude":
      return edit(state, { ...l, excluded: uniq([...l.excluded, ...action.ids]) }, "excluded_event_ids");
    case "include": {
      const drop = new Set(action.ids);
      return edit(state, { ...l, excluded: l.excluded.filter((i) => !drop.has(i)) }, "excluded_event_ids");
    }
    case "setExcluded":
      return edit(state, { ...l, excluded: uniq(action.ids) }, "excluded_event_ids");
    case "setPin":
      return edit(state, { ...l, pins: [...l.pins.filter((p) => p.event_id !== action.pin.event_id), action.pin] }, "pins");
    case "unpin":
      return edit(state, { ...l, pins: l.pins.filter((p) => p.event_id !== action.eventId) }, "pins");
    case "setOverride": {
      const next = { ...l.rule_overrides };
      if (!action.override || (action.override.hardness == null && action.override.weight == null)) delete next[String(action.ruleId)];
      else next[String(action.ruleId)] = action.override;
      return edit(state, { ...l, rule_overrides: next }, "rule_overrides");
    }
    case "setRuleInPlay": {
      const set = new Set(l.disabled_rule_ids);
      if (action.inPlay) set.delete(action.ruleId);
      else set.add(action.ruleId);
      return edit(state, { ...l, disabled_rule_ids: [...set].sort((a, b) => a - b) }, "disabled_rule_ids");
    }
    case "setBuiltin": {
      const set = new Set(l.disabled_builtin_kinds);
      if (action.enabled) set.delete(action.kind);
      else set.add(action.kind);
      return edit(state, { ...l, disabled_builtin_kinds: [...set].sort() }, "disabled_builtin_kinds");
    }
    case "setParams":
      return edit(state, { ...l, params: { ...l.params, ...action.params } }, "params");
    case "setStep":
      return l.last_step === action.step ? state : edit(state, { ...l, last_step: action.step }, "last_step");
    case "saving":
      return { ...state, status: "saving", error: null };
    case "saved": {
      // fields edited while the request was in flight stay dirty (and keep their local value)
      const stillDirty = state.dirty.filter((f) => !action.sent.includes(f));
      const fromServer = localFromDraft(action.draft);
      const local = { ...fromServer };
      for (const f of stillDirty) assignField(local, l, f);
      return { ...state, server: action.draft, local, dirty: stillDirty, status: stillDirty.length ? "idle" : "saved", error: null, conflict: null };
    }
    case "saveFailed":
      return { ...state, status: "error", error: action.error };
    case "conflict":
      return { ...state, status: "conflict", conflict: action.current };
    case "keepMine":
      // overwrite: adopt the server version number, resend every field
      return { ...state, server: action.current, status: "idle", conflict: null, dirty: ALL_FIELDS };
  }
}

export const ALL_FIELDS: DraftField[] = ["horizon", "horizon_params", "excluded_event_ids", "pins", "disabled_builtin_kinds", "disabled_rule_ids", "rule_overrides", "params", "last_step"];

function assignField(target: DraftLocal, source: DraftLocal, f: DraftField): void {
  switch (f) {
    case "horizon":
      target.horizon = source.horizon;
      break;
    case "horizon_params":
      target.horizon_params = source.horizon_params;
      break;
    case "excluded_event_ids":
      target.excluded = source.excluded;
      break;
    case "pins":
      target.pins = source.pins;
      break;
    case "disabled_builtin_kinds":
      target.disabled_builtin_kinds = source.disabled_builtin_kinds;
      break;
    case "disabled_rule_ids":
      target.disabled_rule_ids = source.disabled_rule_ids;
      break;
    case "rule_overrides":
      target.rule_overrides = source.rule_overrides;
      break;
    case "params":
      target.params = source.params;
      break;
    case "last_step":
      target.last_step = source.last_step;
      break;
    case "preset_id":
      target.preset_id = source.preset_id;
      break;
  }
}

/** The PUT body for the dirty fields. */
export function patchFor(local: DraftLocal, fields: readonly DraftField[]): DraftPatch {
  const p: DraftPatch = {};
  for (const f of fields) {
    switch (f) {
      case "horizon":
        p.horizon = local.horizon;
        break;
      case "horizon_params":
        p.horizon_params = local.horizon_params;
        break;
      case "excluded_event_ids":
        p.excluded_event_ids = local.excluded;
        break;
      case "pins":
        p.pins = local.pins;
        break;
      case "disabled_builtin_kinds":
        p.disabled_builtin_kinds = local.disabled_builtin_kinds;
        break;
      case "disabled_rule_ids":
        p.disabled_rule_ids = local.disabled_rule_ids;
        break;
      case "rule_overrides":
        p.rule_overrides = local.rule_overrides;
        break;
      case "params":
        p.params = local.params;
        break;
      case "last_step":
        if (local.last_step) p.last_step = local.last_step;
        break;
      case "preset_id":
        p.preset_id = local.preset_id;
        break;
    }
  }
  return p;
}

/* ------------------------------------------------------------------------- weeks */

/** Client mirror of `solver_bridge.horizon_weeks`: WEEK = chosen weeks, MONTH = 4 weeks from the
 * start week, TERM = every lecture week. Holidays stay in the list (the backend skips them). */
export function resolveWeeks(horizon: Horizon, hp: HorizonParams, termWeeks: readonly Week[]): number[] {
  const lecture = termWeeks.filter((w) => w.kind === "LECTURE" || w.kind === "MAKEUP").map((w) => w.index).sort((a, b) => a - b);
  if (horizon === "TERM") return lecture;
  const chosen = (hp.weeks ?? []).slice().sort((a, b) => a - b);
  if (horizon === "MONTH") {
    const start = hp.start_week ?? chosen[0] ?? lecture[0];
    if (start === undefined) return [];
    return Array.from({ length: 4 }, (_, k) => start + k).filter((w) => termWeeks.some((x) => x.index === w));
  }
  return chosen;
}

/* ------------------------------------------------------------------------ rules */

export interface EffectiveRule {
  rule: StudioRule;
  hardness: "hard" | "soft";
  weight: number;
  inPlay: boolean;
}

export function effectiveRules(rules: readonly StudioRule[], local: DraftLocal): EffectiveRule[] {
  const off = new Set(local.disabled_rule_ids);
  return rules.map((rule) => {
    const ov = local.rule_overrides[String(rule.id)];
    return {
      rule,
      hardness: ov?.hardness ?? rule.hardness,
      weight: ov?.weight ?? rule.weight,
      inPlay: rule.enabled && !off.has(rule.id),
    };
  });
}

/* ---------------------------------------------------------------------- summary */

export interface ClassCountInput {
  id: number;
  schedulable: boolean;
}

export interface SummaryInput {
  local: DraftLocal;
  dirty: boolean;
  server: Draft | null;
  summary: StudioSummary | null;
  classes: readonly ClassCountInput[] | null;
  rules: readonly StudioRule[] | null;
  termWeeks: readonly Week[];
  precheck: Precheck | null;
  checking: boolean;
}

export interface SummaryView {
  classesIn: number;
  classesOut: number;
  classesTotal: number;
  pinned: number;
  rooms: number;
  weeks: number[];
  holidayWeeks: number[];
  must: number;
  tryTo: number;
  builtinsOff: number;
  /** "unknown" until a pre-check for the current draft version exists */
  readiness: Readiness | "unknown" | "checking";
  problems: number;
  topIssues: Precheck["items"];
  estimate: { low: number; high: number } | null;
  lastGoodRunId: number | null;
  stability: boolean;
}

export function deriveSummary(i: SummaryInput): SummaryView {
  const excluded = new Set(i.local.excluded);
  const classesIn = i.classes ? i.classes.filter((c) => c.schedulable && !excluded.has(c.id)).length : Math.max(0, (i.summary?.counts.classes_in ?? 0) - (i.dirty ? excluded.size - (i.summary?.counts.classes_out ?? 0) : 0));
  const weeks = i.termWeeks.length ? resolveWeeks(i.local.horizon, i.local.horizon_params, i.termWeeks) : (i.summary?.weeks ?? []);
  const holidays = new Set(i.termWeeks.filter((w) => w.kind === "HOLIDAY").map((w) => w.index));
  const eff = i.rules ? effectiveRules(i.rules, i.local).filter((r) => r.inPlay) : null;
  const must = eff ? eff.filter((r) => r.hardness === "hard").length : (i.summary?.counts.rules_must ?? 0);
  const tryTo = eff ? eff.filter((r) => r.hardness === "soft").length : (i.summary?.counts.rules_try ?? 0);
  const fresh = i.precheck !== null && !i.dirty && i.server !== null && i.precheck.version === i.server.version;
  const readiness: SummaryView["readiness"] = i.checking ? "checking" : fresh && i.precheck ? i.precheck.readiness : "unknown";
  const items = i.precheck?.items ?? [];
  const order = { error: 0, warning: 1, info: 2 } as const;
  const top = [...items].sort((a, b) => order[a.severity] - order[b.severity]).slice(0, 3);
  const est = i.precheck?.estimate_s ?? i.summary?.estimate_s ?? null;
  const lastGood = i.summary?.last_good_run?.id ?? null;
  return {
    classesIn,
    classesOut: excluded.size,
    classesTotal: i.classes ? i.classes.length : (i.summary?.counts.classes_total ?? 0),
    pinned: i.local.pins.length,
    rooms: i.summary?.counts.rooms ?? 0,
    weeks,
    holidayWeeks: weeks.filter((w) => holidays.has(w)),
    must,
    tryTo,
    builtinsOff: i.local.disabled_builtin_kinds.length,
    readiness,
    problems: items.filter((x) => x.severity !== "info").length,
    topIssues: top,
    estimate: est ? { low: est.low, high: est.high } : null,
    lastGoodRunId: lastGood,
    stability: lastGood !== null && i.local.params.stability !== false,
  };
}

/** Rounded words for an estimate in seconds ("under a minute", "about 2 minutes (at most 5)"). */
export function estimateWords(est: { low: number; high: number }, t: (key: "under" | "aboutOne" | "about" | "atMost", vars?: Record<string, number>) => string): string {
  if (est.high < 60) return t("under");
  const mid = (est.low + est.high) / 2;
  const minutes = Math.max(1, Math.round(mid / 60));
  const hi = Math.max(minutes, Math.round(est.high / 60));
  const head = minutes === 1 ? t("aboutOne") : t("about", { n: minutes });
  return hi > minutes ? `${head} ${t("atMost", { n: hi })}` : head;
}
