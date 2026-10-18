// FIX-K (orchestrator ask, HX12B-F06 / HB18-F05 follow-up): the "'Planlama yönetimi' izni" toast on a planner's
// run page came from a background GET of an admin-only resource (GET /settings from the run chat, fixed by FIX-E).
// So that no other background read can do it again, a GET answered 403 never reaches the global error toast; the
// screen that asked shows its own no-access state. A refused action (POST / PUT / DELETE) still toasts.
import { afterEach, describe, expect, it, vi } from "vitest";
import { onApiError, request } from "./client";

const forbidden = () =>
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ detail: { code: "forbidden", permission: "planning.admin", message_tr: 'Bu işlem için "Planlama yönetimi" izni gerekiyor' } }), { status: 403, headers: { "content-type": "application/json" } })),
  );

describe("403 on a background read", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("a GET 403 rejects without the global toast; a POST 403 still toasts", async () => {
    const seen: number[] = [];
    const off = onApiError((e) => seen.push(e.status));
    forbidden();
    await expect(request("/settings")).rejects.toMatchObject({ status: 403 });
    expect(seen).toEqual([]);
    await expect(request("/settings", { method: "PUT", body: {} })).rejects.toMatchObject({ status: 403 });
    expect(seen).toEqual([403]);
    off();
  });
});
