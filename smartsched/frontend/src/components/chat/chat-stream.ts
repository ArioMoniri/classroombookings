/**
 * Streaming chat client for `POST /runs/{id}/chat/stream` (text/event-stream; app/api/v1/chat.py): `text` deltas,
 * `tool_start` / `tool` / `retry` events, then `done` (the ChatOut body) or `error` ({status, detail}). The panel
 * renders the text as it arrives (appended, no typing animation) and each tool call as pending → result; when the
 * stream cannot start (proxy without streaming, older backend) the non-streaming `POST /chat` is the fallback.
 */
import { buildUrl, HttpError } from "@/lib/api/client";

export type StreamEvent = { event: string; data: unknown };
export type ToolState = { name: string; state: "pending" | "ok" | "failed" };
export interface StreamState {
  text: string;
  tools: ToolState[];
  retries: number;
  done: boolean;
  error: { status: number; detail: string } | null;
}
export const INITIAL_STREAM: StreamState = { text: "", tools: [], retries: 0, done: false, error: null };

const rec = (v: unknown): Record<string, unknown> => (v && typeof v === "object" ? (v as Record<string, unknown>) : {});

export function streamReducer(s: StreamState, e: StreamEvent): StreamState {
  const d = rec(e.data);
  switch (e.event) {
    case "text":
      return { ...s, text: s.text + String(d.text ?? "") };
    case "tool_start":
      return { ...s, tools: [...s.tools, { name: String(d.name ?? "?"), state: "pending" }] };
    case "tool": {
      const name = String(d.name ?? "?");
      const state = d.ok === false ? "failed" : "ok";
      const i = s.tools.findIndex((t) => t.name === name && t.state === "pending");
      const tools = i >= 0 ? s.tools.map((t, k) => (k === i ? { ...t, state } : t)) : [...s.tools, { name, state }];
      return { ...s, tools: tools as ToolState[] };
    }
    case "retry":
      return { ...s, retries: s.retries + 1 };
    case "done":
      return { ...s, done: true };
    case "error":
      return { ...s, done: true, error: { status: Number(d.status ?? 502), detail: String(d.detail ?? "") } };
    default:
      return s;
  }
}

/** Incremental SSE parser: feed it decoded chunks; it calls `on` once per complete frame. */
export function createSseParser(on: (event: string, data: unknown) => void): (chunk: string) => void {
  let buf = "";
  return (chunk) => {
    buf += chunk.replace(/\r\n/g, "\n");
    let cut: number;
    while ((cut = buf.indexOf("\n\n")) >= 0) {
      const frame = buf.slice(0, cut);
      buf = buf.slice(cut + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of frame.split("\n")) {
        if (line.startsWith(":")) continue;
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
      }
      if (!data.length) continue;
      const text = data.join("\n");
      let parsed: unknown = text;
      try {
        parsed = JSON.parse(text);
      } catch {
        /* a plain-text data line */
      }
      on(event, parsed);
    }
  };
}

/** Stream one chat turn. Rejects with an HttpError before the first event when the stream cannot start. */
export async function streamChat(runId: number, message: string, lang: "tr" | "en", on: (e: StreamEvent) => void, signal?: AbortSignal): Promise<void> {
  const res = await fetch(buildUrl(`/runs/${runId}/chat/stream`), {
    method: "POST",
    headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
    body: JSON.stringify({ message, lang }),
    credentials: "same-origin",
    signal,
  });
  if (!res.ok || !res.body || !(res.headers.get("content-type") ?? "").includes("text/event-stream")) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = (await res.json()) as { detail?: unknown };
      if (typeof j.detail === "string") detail = j.detail;
    } catch {
      /* not JSON */
    }
    throw new HttpError(res.status, detail);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  const feed = createSseParser((event, data) => on({ event, data }));
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    feed(decoder.decode(value, { stream: true }));
  }
  feed(decoder.decode());
}
