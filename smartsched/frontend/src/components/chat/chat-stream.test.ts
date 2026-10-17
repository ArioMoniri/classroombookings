import { describe, expect, it } from "vitest";
import { createSseParser, INITIAL_STREAM, streamReducer } from "./chat-stream";

describe("chat streaming (POST /runs/{id}/chat/stream)", () => {
  it("parses SSE frames across chunk boundaries", () => {
    const out: { event: string; data: unknown }[] = [];
    const feed = createSseParser((event, data) => out.push({ event, data }));
    feed('event: text\ndata: {"text":"Mer');
    feed('haba"}\n\nevent: tool_start\ndata: {"name":"find_rooms"}\n\n');
    feed(': keep-alive\n\nevent: done\ndata: {"message_id":7,"assistant_message":"Merhaba"}\n\n');
    expect(out).toEqual([
      { event: "text", data: { text: "Merhaba" } },
      { event: "tool_start", data: { name: "find_rooms" } },
      { event: "done", data: { message_id: 7, assistant_message: "Merhaba" } },
    ]);
  });

  it("appends text deltas, shows a tool as pending, then its result", () => {
    let s = INITIAL_STREAM;
    s = streamReducer(s, { event: "text", data: { text: "BME 419 " } });
    s = streamReducer(s, { event: "text", data: { text: "için bakıyorum" } });
    s = streamReducer(s, { event: "tool_start", data: { name: "find_rooms" } });
    expect(s.text).toBe("BME 419 için bakıyorum");
    expect(s.tools).toEqual([{ name: "find_rooms", state: "pending" }]);
    s = streamReducer(s, { event: "tool", data: { name: "find_rooms", ok: true } });
    s = streamReducer(s, { event: "tool_start", data: { name: "propose_diff" } });
    s = streamReducer(s, { event: "tool", data: { name: "propose_diff", ok: false } });
    expect(s.tools).toEqual([{ name: "find_rooms", state: "ok" }, { name: "propose_diff", state: "failed" }]);
    s = streamReducer(s, { event: "retry", data: { reason: "unreadable tool input" } });
    expect(s.retries).toBe(1);
    s = streamReducer(s, { event: "done", data: { message_id: 7 } });
    expect(s.done).toBe(true);
  });

  it("an error event ends the stream with the server's detail", () => {
    const s = streamReducer(INITIAL_STREAM, { event: "error", data: { status: 502, detail: "the AI service failed; try again later" } });
    expect(s).toMatchObject({ done: true, error: { status: 502, detail: "the AI service failed; try again later" } });
  });
  it("a gateway refusal (guardrail 422 / limit 429) keeps its code and both languages", () => {
    const detail = { code: "ai_limit_reached", message: "Limit reached", message_en: "Limit reached", message_tr: "Sınıra ulaşıldı" };
    const s = streamReducer(INITIAL_STREAM, { event: "error", data: { status: 429, detail } });
    expect(s.error).toEqual({ status: 429, detail: "Limit reached", code: "ai_limit_reached", messageTr: "Sınıra ulaşıldı", messageEn: "Limit reached" });
  });
});
