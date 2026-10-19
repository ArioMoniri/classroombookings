/**
 * The Studio autosave is single flight (pod e2e #125, integrity-r1 #4): a flush that arrives while a save is in
 * flight joins it, and the edit made meanwhile goes out once, right after the answer, on the new version. No 409.
 */
import { describe, expect, it, vi } from "vitest";
import type { Draft } from "@/lib/api/studio-schemas";
import { createDraftSaver } from "./draft-saver";
import { createStudioStore } from "./studio-store";

const draft = (weeks: number[], version: number): Draft => ({
  draft_id: 9,
  term_id: 1,
  kind: "COURSE",
  version,
  scope: { horizon: "WEEK", horizon_params: { weeks }, weeks, holiday_weeks: [] },
  excluded_event_ids: [],
  pins: [],
  disabled_builtin_kinds: [],
  disabled_rule_ids: [],
  rule_overrides: {},
  rule_ids: [],
  params: {},
});

describe("createDraftSaver (single flight)", () => {
  it("an edit and a flush during a pending save: two PUTs, v then v+1, the newest week kept, no conflict", async () => {
    const store = createStudioStore();
    store.getState().dispatch({ type: "hydrate", draft: draft([6], 3) });
    let answer: ((d: Draft) => void) | null = null;
    const save = vi.fn((version: number, patch: { horizon_params?: unknown }) =>
      version === 3 ? new Promise<Draft>((res) => (answer = res)) : Promise.resolve(draft((patch.horizon_params as { weeks: number[] }).weeks, version + 1)),
    );
    const saveNow = createDraftSaver(store, save);

    store.getState().dispatch({ type: "setScope", horizon: "WEEK", horizon_params: { weeks: [4] } });
    const first = saveNow(); // the autosave timer
    expect(save).toHaveBeenCalledTimes(1);
    store.getState().dispatch({ type: "setScope", horizon: "WEEK", horizon_params: { weeks: [3] } }); // clicked meanwhile
    const flushed = saveNow(); // the pre-check's flush joins the running loop
    expect(save).toHaveBeenCalledTimes(1);
    answer!(draft([4], 4));
    await Promise.all([first, flushed]);

    expect(save).toHaveBeenCalledTimes(2);
    expect(save.mock.calls[0]![0]).toBe(3);
    expect(save.mock.calls[1]![0]).toBe(4);
    expect(save.mock.calls[1]![1].horizon_params).toEqual({ weeks: [3] });
    const s = store.getState().studio;
    expect(s.status).toBe("saved");
    expect(s.dirty).toEqual([]);
    expect(s.server?.version).toBe(5);
    expect(s.local.horizon_params).toEqual({ weeks: [3] });
  });
});
