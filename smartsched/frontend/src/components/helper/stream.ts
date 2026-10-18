/**
 * HX-03: the stream client of `POST /helper/turn` (backend HB-06, app/api/v1/helper_turn.py). Events: `run_started`
 * {turn_id} → (`tool_start` {name} → `tool` {name, ok})* → `text` {text} → `card` {card}* → `run_finished` {mode,
 * outcome, fallback, reason}; or `error` {status, detail}. Every card is parsed with the generated zod; a card the
 * client cannot read becomes `bad_card` (the fallback), never raw data. The SSE frame parser is the run chat's
 * (components/chat/chat-stream.ts), shared as helper.md §2.6 asks.
 *
 * HX-16: the body carries `context` (the "Bu sayfa: …" chip, HB-D) only when it is given and passes the server's own
 * rules ({@link TurnContext}); a shape the server would refuse with a 422 is dropped, never sent.
 */
import { createSseParser } from "@/components/chat/chat-stream";
import { buildUrl, HttpError } from "@/lib/api/client";
import { TurnContext } from "@/lib/api/helper";
import { HelperCard } from "./schema.gen";

export type TurnEvent =
  | { type: "run_started"; turnId: string }
  | { type: "tool_start"; name: string }
  | { type: "tool"; name: string; ok: boolean }
  | { type: "text"; text: string }
  | { type: "card"; card: HelperCard }
  /** a card the client cannot read (an unknown type from a newer server): shown as the fallback */
  | { type: "bad_card" }
  | { type: "run_finished"; mode: "ai" | "index"; outcome: string; fallback: string | null; reason: string | null }
  | { type: "error"; status: number; detail: string };

const rec = (v: unknown): Record<string, unknown> => (v && typeof v === "object" ? (v as Record<string, unknown>) : {});

/** One SSE frame of `POST /helper/turn` → a typed event (unknown frames are dropped). */
export function toTurnEvent(event: string, data: unknown): TurnEvent | null {
  const d = rec(data);
  switch (event) {
    case "run_started":
      return { type: "run_started", turnId: String(d.turn_id ?? "") };
    case "tool_start":
      return { type: "tool_start", name: String(d.name ?? "") };
    case "tool":
      return { type: "tool", name: String(d.name ?? ""), ok: d.ok !== false };
    case "text":
      return typeof d.text === "string" ? { type: "text", text: d.text } : null;
    case "card": {
      const r = HelperCard.safeParse(d.card);
      return r.success ? { type: "card", card: r.data } : { type: "bad_card" };
    }
    case "run_finished":
      return {
        type: "run_finished",
        mode: d.mode === "ai" ? "ai" : "index",
        outcome: String(d.outcome ?? ""),
        fallback: typeof d.fallback === "string" ? d.fallback : null,
        reason: typeof d.reason === "string" ? d.reason : null,
      };
    case "error":
      return { type: "error", status: Number(d.status ?? 500), detail: typeof d.detail === "string" ? d.detail : "" };
    default:
      return null;
  }
}

/** Stream one helper turn. Rejects with an HttpError (detail kept) before the first event when it cannot start. */
export async function streamTurn(
  text: string,
  lang: "tr" | "en",
  on: (e: TurnEvent) => void,
  opts: { signal?: AbortSignal; context?: TurnContext | null } = {},
): Promise<void> {
  const { signal } = opts;
  const context = opts.context ? TurnContext.safeParse(opts.context) : null;
  const res = await fetch(buildUrl("/helper/turn"), {
    method: "POST",
    headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
    body: JSON.stringify(context?.success ? { text, lang, context: context.data } : { text, lang }),
    credentials: "same-origin",
    signal,
  });
  if (!res.ok || !res.body || !(res.headers.get("content-type") ?? "").includes("text/event-stream")) {
    let detail: unknown;
    try {
      detail = ((await res.json()) as { detail?: unknown }).detail;
    } catch {
      /* not JSON */
    }
    throw new HttpError(res.status, typeof detail === "string" ? detail : `${res.status} ${res.statusText}`, detail);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  const feed = createSseParser((event, data) => {
    const e = toTurnEvent(event, data);
    if (e) on(e);
  });
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    feed(decoder.decode(value, { stream: true }));
  }
  feed(decoder.decode());
}
