/**
 * Hand-over links of the helper's cards (helper.md §4.3; the formats the pages read, lib/handover.ts):
 * `/profile?calendar=1`, `/admin/users?invite=1&email=&name=&role=&department=`, `/runs/<id>?publish=1`,
 * `/runs/<id>?chat=`. The run-scoped controls (Yayınla, Dışa aktar) live on `/runs/<id>` only, so their page is the
 * run: the one in the address, else the published run, else the newest finished one.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api/endpoints";
import { chatPrefill, invitePrefill, publishRequested } from "@/lib/handover";
import { featureById } from "./feature-links";
import { handoverHref, isRunScoped, pickRun, resolveRunId, runChatHref, runFeatureHref } from "./handover-links";

const run = (id: number, status: string, over: Record<string, unknown> = {}) => ({ id, status, is_active: false, created_at: `2026-02-${String(id).padStart(2, "0")}T08:00:00`, ...over });

beforeEach(() => vi.restoreAllMocks());

describe("hand-over links", () => {
  it("calendar and invite use the page's prefill formats", () => {
    expect(handoverHref("profile.calendar")).toBe("/profile?calendar=1");
    const invite = handoverHref("admin.users.invite", { invite: { email: "ayse@uni.edu.tr", name: "Ayşe Yılmaz", role: "TEACHER", department: "4" } })!;
    expect(invite).toBe("/admin/users?invite=1&email=ayse%40uni.edu.tr&name=Ay%C5%9Fe+Y%C4%B1lmaz&role=TEACHER&department=4");
    expect(invitePrefill(new URL(invite, "http://x").searchParams)).toEqual({ email: "ayse@uni.edu.tr", name: "Ayşe Yılmaz", role: "TEACHER", department: "4" });
    expect(handoverHref("admin.users.invite")).toBe("/admin/users?invite=1&email=&name=&role=&department=");
    expect(handoverHref("admin.holidays")).toBeNull();
  });

  it("publish opens the run's own dialog; the chat prefills the run chat's composer", () => {
    const publish = handoverHref("runs.publish", { runId: 12 })!;
    expect(publish).toBe("/runs/12?publish=1");
    expect(publishRequested(new URL(publish, "http://x").searchParams, 12)).toBe(true);
    expect(handoverHref("runs.publish", { runId: null })).toBe("/runs");
    const chat = runChatHref(12, "Pazartesi 08:40'ı boşalt");
    expect(chat).toBe("/runs/12?chat=Pazartesi+08%3A40%27%C4%B1+bo%C5%9Falt");
    expect(chatPrefill(new URL(chat, "http://x").searchParams)).toBe("Pazartesi 08:40'ı boşalt");
  });

  it("Yayınla and Dışa aktar are on the run, not on the runs list", () => {
    expect(isRunScoped(featureById("runs.publish")!)).toBe(true);
    expect(isRunScoped(featureById("runs.export")!)).toBe(true);
    expect(isRunScoped(featureById("runs")!)).toBe(false);
    expect(runFeatureHref("runs.export", 12)).toBe("/runs/12");
    expect(runFeatureHref("runs.export", null)).toBe("/runs");
  });

  it("the run: the address's, else the published one, else the newest finished one", async () => {
    expect(pickRun([run(3, "OPTIMAL"), run(5, "FEASIBLE", { is_active: true }), run(7, "OPTIMAL")] as never)).toBe(5);
    expect(pickRun([run(3, "OPTIMAL"), run(7, "FEASIBLE"), run(9, "RUNNING"), run(8, "ERROR")] as never)).toBe(7);
    expect(pickRun([run(9, "RUNNING")] as never)).toBeNull();
    const list = vi.spyOn(api.runs, "list").mockResolvedValue([run(5, "OPTIMAL", { is_active: true })] as never);
    expect(await resolveRunId("/runs/12")).toBe(12);
    expect(list).not.toHaveBeenCalled();
    expect(await resolveRunId("/runs")).toBe(5);
    list.mockRejectedValue(new Error("403"));
    expect(await resolveRunId("/timetable")).toBeNull();
  });

  it("HB18-F05: Yayınla goes to the newest finished run that is not published yet (the published one has no Yayınla)", async () => {
    const runs = [run(3, "OPTIMAL", { is_active: true }), run(7, "FEASIBLE"), run(8, "OPTIMAL"), run(9, "RUNNING")] as never;
    expect(pickRun(runs, "runs.publish")).toBe(8);
    expect(pickRun(runs, "runs.export")).toBe(3);
    expect(pickRun([run(3, "OPTIMAL", { is_active: true })] as never, "runs.publish")).toBe(3);
    vi.spyOn(api.runs, "list").mockResolvedValue(runs);
    expect(await resolveRunId("/runs", "runs.publish")).toBe(8);
    expect(await resolveRunId("/runs")).toBe(3);
  });
});
