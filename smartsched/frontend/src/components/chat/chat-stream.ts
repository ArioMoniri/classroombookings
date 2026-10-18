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
  /** `detail` is the server's text (English when the server sent a coded refusal); a gateway refusal (guardrail 422,
   * limit / rate 429, transfer basis 409: app/ai/pipeline.AIGuardError) also carries its code and both languages */
  error: { status: number; detail: string; code?: string; messageTr?: string; messageEn?: string } | null;
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
    case "error": {
      const status = Number(d.status ?? 502);
      if (d.detail && typeof d.detail === "object") {
        const x = rec(d.detail);
        const en = typeof x.message_en === "string" ? x.message_en : undefined;
        const tr = typeof x.message_tr === "string" ? x.message_tr : undefined;
        const code = typeof x.code === "string" ? x.code : undefined;
        const detail = en ?? (typeof x.message === "string" ? x.message : code ?? "");
        return { ...s, done: true, error: { status, detail, ...(code ? { code } : {}), ...(tr ? { messageTr: tr } : {}), ...(en ? { messageEn: en } : {}) } };
      }
      return { ...s, done: true, error: { status, detail: String(d.detail ?? "") } };
    }
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
    let body: unknown;
    try {
      body = await res.json();
      const d = (body as { detail?: unknown }).detail;
      if (typeof d === "string") detail = d;
      else if (d && typeof d === "object" && typeof (d as { message_en?: unknown }).message_en === "string") detail = (d as { message_en: string }).message_en;
    } catch {
      /* not JSON */
    }
    // F-VO-2: the body is kept, so a coded refusal (422 `prompt_injection_*`, 429 limits) reads in the user's language
    throw new HttpError(res.status, detail, body);
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
