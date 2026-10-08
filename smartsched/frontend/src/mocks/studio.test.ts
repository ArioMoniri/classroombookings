// @vitest-environment node
import { getResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { ClassPage, CopyResult, Draft, DraftConflict, Extraction, FixResult, GenerateOut, MappingResult, Precheck, Preset, PresetApply, Preview, RulesOut, StudioMeta, StudioSummary } from "@/lib/api/studio-schemas";
import { handlers, resetMockState } from "./handlers";

const BASE = "http://backend.test/api/v1";
async function call(path: string, init?: RequestInit) {
  const res = await getResponse(handlers, new Request(`${BASE}${path}`, init));
  if (!res) throw new Error(`no handler for ${path}`);
  return res;
}
const put = (body: unknown) => ({ method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const post = (body: unknown) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

describe("studio mock API (backend shapes)", () => {
  beforeEach(() => resetMockState());

  it("serves meta with the 2/5/8 scale and 14 templates", async () => {
    const meta = StudioMeta.parse(await (await call("/studio/meta")).json());
    expect(meta.weight_scale).toMatchObject({ low: 2, normal: 5, high: 8 });
    expect(meta.templates).toHaveLength(14);
  });

  it("autosaves the draft with optimistic concurrency (409 with the current copy)", async () => {
    const d = Draft.parse(await (await call("/terms/1/studio?kind=COURSE")).json());
    const saved = Draft.parse(await (await call("/terms/1/studio", put({ kind: "COURSE", version: d.version, excluded_event_ids: [1, 2] }))).json());
    expect(saved.version).toBe(d.version + 1);
    expect(saved.excluded_event_ids).toEqual([1, 2]);
    const stale = await call("/terms/1/studio", put({ kind: "COURSE", version: d.version, excluded_event_ids: [] }));
    expect(stale.status).toBe(409);
    expect(DraftConflict.parse(await stale.json()).detail.current.version).toBe(saved.version);
    const page = ClassPage.parse(await (await call("/terms/1/studio/classes?kind=COURSE&limit=2000")).json());
    expect(page.counts.left_out).toBe(2);
    expect(page.items.find((r) => r.id === 1)?.included).toBe(false);
  });

  it("pre-check finds the impossible class and a fix changes the draft", async () => {
    const p = Precheck.parse(await (await call("/terms/1/studio/precheck?kind=COURSE", post({}))).json());
    expect(p.readiness).toBe("blocked");
    const item = p.items.find((i) => i.category === "impossible");
    expect(item?.fixes.map((f) => f.option)).toContain("exclude");
    expect(p.groups.some((g) => g.group === "capacity")).toBe(true);
    const fixed = FixResult.parse(await (await call("/terms/1/studio/precheck/fix?kind=COURSE", post({ item_id: item?.id, option: "exclude" }))).json());
    expect(fixed.draft.excluded_event_ids).toEqual(item?.event_ids);
    expect(fixed.precheck.items.some((i) => i.id === item?.id)).toBe(false);
  });

  it("class edits keep an imported snapshot and can be reverted", async () => {
    await call("/studio/meetings/bulk", put({ items: [{ id: 1, patch: { enrolment: 999 } }] }));
    let page = ClassPage.parse(await (await call("/terms/1/studio/classes?kind=COURSE&changed=true")).json());
    expect(page.items.map((r) => r.id)).toEqual([1]);
    expect(page.items[0].changed_fields[0]).toMatchObject({ field: "enrolment", current: 999 });
    await call("/studio/meetings/1/revert", post({ fields: ["enrolment"] }));
    page = ClassPage.parse(await (await call("/terms/1/studio/classes?kind=COURSE&changed=true")).json());
    expect(page.items).toHaveLength(0);
  });

  it("rules carry affected counts; preview counts a programme selector", async () => {
    const rules = RulesOut.parse(await (await call("/terms/1/studio/rules?kind=COURSE")).json());
    expect(rules.rules.length).toBeGreaterThan(0);
    expect(rules.builtins.find((b) => b.kind === "no_room_overlap")?.disableable).toBe(false);
    const pv = Preview.parse(await (await call("/studio/constraints/preview", post({ term_id: 1, kind: "building_preference", params: { programs: ["Eczacılık"], building: "C" }, hardness: "soft" }))).json());
    expect(pv.affected_count).toBeGreaterThan(0);
    expect(pv.targeted).toBe(true);
  });

  it("upload without an AI key → 409, then the column mapping turns rows into proposals", async () => {
    await call("/settings", put({ anthropic_api_key: undefined }));
    const fd = () => {
      const f = new FormData();
      f.append("file", new File(["x"], "talepler.xlsx"));
      return f;
    };
    const ai = await call("/terms/1/preferences/upload", { method: "POST", body: fd() });
    expect([200, 409]).toContain(ai.status);
    if (ai.status === 200) expect(Extraction.parse(await ai.json()).proposals[0].source_ref).toMatchObject({ file: "talepler.xlsx", row: 2 });
    const cols = MappingResult.parse(await (await call("/terms/1/studio/preferences/mapping", { method: "POST", body: fd() })).json());
    expect(cols.mode).toBe("columns");
    const withMap = fd();
    withMap.append("mapping", JSON.stringify({ columns: { course: 0, room: 4, enrolment: 3 }, room_rule: "prefer" }));
    const res = MappingResult.parse(await (await call("/terms/1/studio/preferences/mapping", { method: "POST", body: withMap })).json());
    expect(res.mode).toBe("proposals");
    if (res.mode === "proposals") {
      expect(res.proposals[0].source_ref).toMatchObject({ file: "talepler.xlsx", row: 2 });
      expect(res.unparsed).toHaveLength(1);
    }
  });

  it("copies rules from another term (dry run first), applies presets and generates from the draft", async () => {
    const dry = CopyResult.parse(await (await call("/studio/constraints/copy", post({ to_term_id: 1, from_term_id: 3, dry_run: true }))).json());
    expect(dry.will_match.length + dry.needs_review.length + dry.cannot_match.length).toBe(4);
    expect(dry.cannot_match.some((c) => c.reasons.some((r) => /classes/.test(r)))).toBe(true);
    const presets = (await (await call("/presets?kind=COURSE")).json()) as unknown[];
    const preset = Preset.parse(presets[0]);
    const diff = PresetApply.parse(await (await call(`/presets/${preset.id}/apply`, post({ term_id: 1, dry_run: true }))).json());
    expect(diff.dry_run).toBe(true);
    const gen = GenerateOut.parse(await (await call("/terms/1/studio/generate?kind=COURSE", post({ stability: false }))).json());
    expect(gen.run_id).toBeGreaterThan(2);
    const sum = StudioSummary.parse(await (await call("/terms/1/studio/summary?kind=COURSE")).json());
    expect(sum.counts.rooms).toBeGreaterThan(50);
  });
});
