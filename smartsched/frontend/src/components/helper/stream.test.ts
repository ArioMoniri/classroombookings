/** HX-03: the `POST /helper/turn` stream (API.md event table) → typed events; cards only through the zod. */
import { afterEach, describe, expect, it, vi } from "vitest";
import fixtures from "./__fixtures__/cards.json";
import { streamTurn, toTurnEvent } from "./stream";

const frame = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

afterEach(() => vi.unstubAllGlobals());

describe("helper turn stream", () => {
  it("maps every event of the contract", () => {
    expect(toTurnEvent("run_started", { turn_id: "abcd1234abcd1234" })).toEqual({ type: "run_started", turnId: "abcd1234abcd1234" });
    expect(toTurnEvent("tool_start", { name: "find_free_rooms" })).toEqual({ type: "tool_start", name: "find_free_rooms" });
    expect(toTurnEvent("tool", { name: "find_free_rooms", ok: false })).toEqual({ type: "tool", name: "find_free_rooms", ok: false });
    expect(toTurnEvent("text", { text: "A 204 boş." })).toEqual({ type: "text", text: "A 204 boş." });
    expect(toTurnEvent("card", { card: fixtures.nav })).toMatchObject({ type: "card", card: { type: "nav", feature_id: "admin.holidays" } });
    expect(toTurnEvent("run_finished", { mode: "index", outcome: "fallback", fallback: "ai_limit_reached" })).toEqual({ type: "run_finished", mode: "index", outcome: "fallback", fallback: "ai_limit_reached", reason: null });
    expect(toTurnEvent("error", { status: 500, detail: "x" })).toEqual({ type: "error", status: 500, detail: "x" });
    expect(toTurnEvent("ping", {})).toBeNull();
  });

  it("an unreadable card is a fallback, never raw data", () => {
    expect(toTurnEvent("card", { card: { ...fixtures.answer, text: "<img src=x onerror=alert(1)>" } })).toEqual({ type: "bad_card" });
    expect(toTurnEvent("card", { card: { type: "widget", id: "abcdef12", v: 1 } })).toEqual({ type: "bad_card" });
  });

  it("streams a turn split across chunks", async () => {
    const body = frame("run_started", { turn_id: "t1" }) + frame("card", { card: fixtures.answer_index }) + frame("run_finished", { mode: "index", outcome: "index" });
    const enc = new TextEncoder();
    const chunks = [body.slice(0, 17), body.slice(17, 90), body.slice(90)];
    const stream = new ReadableStream({ start(c) { for (const ch of chunks) c.enqueue(enc.encode(ch)); c.close(); } });
    const fetchMock = vi.fn(async () => new Response(stream, { headers: { "content-type": "text/event-stream" } }));
    vi.stubGlobal("fetch", fetchMock);
    const got: string[] = [];
    await streamTurn("tatil nerede", "tr", (e) => got.push(e.type));
    expect(got).toEqual(["run_started", "card", "run_finished"]);
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/helper/turn", expect.objectContaining({ method: "POST", body: JSON.stringify({ text: "tatil nerede", lang: "tr" }) }));
  });

  it("HX-16: sends the page context only when it is given and valid", async () => {
    const ok = () => new Response(new ReadableStream({ start(c) { c.close(); } }), { headers: { "content-type": "text/event-stream" } });
    const fetchMock = vi.fn(async () => ok());
    vi.stubGlobal("fetch", fetchMock);
    await streamTurn("bu oda", "tr", () => undefined, { context: { route: "/rooms/12", entity_kind: "room", entity_id: 12 } });
    expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/helper/turn", expect.objectContaining({ body: JSON.stringify({ text: "bu oda", lang: "tr", context: { route: "/rooms/12", entity_kind: "room", entity_id: 12 } }) }));
    await streamTurn("bu oda", "tr", () => undefined, { context: null });
    expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/helper/turn", expect.objectContaining({ body: JSON.stringify({ text: "bu oda", lang: "tr" }) }));
    // a shape the server would refuse with a 422 is dropped, never sent
    await streamTurn("bu oda", "tr", () => undefined, { context: { route: "/rooms/12", entity_kind: "room", entity_id: 0 } });
    expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/helper/turn", expect.objectContaining({ body: JSON.stringify({ text: "bu oda", lang: "tr" }) }));
  });

  it("a refused start keeps the server's detail (limit card)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: { code: "rate_limited", message_tr: "Çok hızlı.", card: fixtures.limit } }), { status: 429, headers: { "content-type": "application/json" } })));
    await expect(streamTurn("x", "tr", () => undefined)).rejects.toMatchObject({ status: 429, detail: { code: "rate_limited" } });
  });
});
