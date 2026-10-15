import { describe, expect, it } from "vitest";
import { Draft } from "@/lib/api/studio-schemas";
import { draftExport, draftFileName } from "./draft-export";

const d = Draft.parse({ draft_id: 7, term_id: 3, kind: "COURSE", version: 12, scope: { horizon: "WEEK", weeks: [3] }, excluded_event_ids: [5], pins: [], rule_overrides: {}, disabled_rule_ids: [9] });

describe("Export draft as JSON (Studio backlog, advanced)", () => {
  it("wraps the saved draft with a schema tag and the export time", () => {
    const out = draftExport(d, "2026-10-15T12:00:00.000Z");
    expect(out.schema).toBe("smartsched.studio-draft/1");
    expect(out.exported_at).toBe("2026-10-15T12:00:00.000Z");
    expect(out.draft).toMatchObject({ draft_id: 7, version: 12, excluded_event_ids: [5], disabled_rule_ids: [9] });
    expect(JSON.parse(JSON.stringify(out))).toEqual(out);
  });
  it("names the file by term, kind and version", () => {
    expect(draftFileName(d)).toBe("smartsched-draft-term3-course-v12.json");
  });
});
