/**
 * Round-2 T-R2-23 (R2-M-02): the server's `POST /runs/{id}/activate` answer is the run plus a notification summary;
 * its `stats` carry nested objects (truth, worker, waived rules …) that the strict `ScheduleRun` schema refused, so a
 * publish that succeeded on the server was shown as "Invalid response … Invalid input" and "Yayında değil". The
 * publish schema reads only what the preview needs and lets the rest through; a shape failure after a 2xx is never
 * shown as zod's English text.
 */
import { describe, expect, it } from "vitest";
import recorded from "./__fixtures__/activate-run-8.json";
import { HttpError } from "./client";
import { isResponseShapeError, responseShapeText } from "./error-text";
import { ActivateOut, refusal } from "./moderation";

describe("POST /runs/{id}/activate response (T-R2-23)", () => {
  it("parses the recorded activate body of a published full-term run", () => {
    const out = ActivateOut.parse(recorded);
    expect(out.id).toBe(8);
    expect(out.is_active).toBe(true);
    expect(out.notified).toBeNull();
    // nested stats are the reason the old strict schema failed: they must pass through untouched
    expect((out as Record<string, unknown>).stats).toMatchObject({ truth: expect.any(Object), worker: expect.any(Object) });
  });
  it("accepts the notification summary of a publish with 'Akademisyenlere bildir'", () => {
    const out = ActivateOut.parse({ ...recorded, is_active: true, notified: 3, notify: { notified: 3, skipped: 1, people: [] } });
    expect(out.notified).toBe(3);
    expect(out.notify).toMatchObject({ notified: 3 });
  });
  it("needs only the run id", () => {
    expect(ActivateOut.safeParse({ id: 12 }).success).toBe(true);
    expect(ActivateOut.safeParse({ notified: 2 }).success).toBe(false);
  });
  it("shows a shape failure after a 2xx in Turkish, never as zod's text", () => {
    const e = new HttpError(500, "Invalid response for POST /runs/12/activate: Invalid input", [{ code: "invalid_type", path: ["stats", "truth"], message: "Invalid input" }]);
    expect(isResponseShapeError(e)).toBe(true);
    expect(isResponseShapeError(new HttpError(500, "Internal Server Error"))).toBe(false);
    expect(isResponseShapeError(new HttpError(409, "Invalid response for x"))).toBe(false);
    const r = refusal(e, "tr");
    expect(r.message).toBe(responseShapeText("tr"));
    expect(r.message).not.toMatch(/Invalid/);
    expect(refusal(e, "en").message).toBe(responseShapeText("en"));
  });
});
