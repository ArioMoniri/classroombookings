"use client";
/**
 * HB-23c: the helper file router's API (docs/design/v3/helper-file-router.md §6, backend lane HB-23b).
 *
 * - `POST /helper/files/classify` (multipart `file`, `context?`, `lang`) → `{card, stage?}`: a `file` card (detected /
 *   unknown / needs_planner), a `choice` card (ambiguous), or a `refusal` / `error` card. Nothing is stored except an
 *   encrypted 10-minute stage; `stage.upload_token` carries the key (never put it in a URL, a log or localStorage).
 * - `POST /helper/files/route` `{upload_token, kind}` → `{card}`: the chooser pick and "Başka bir tür seç".
 * - `POST /helper/files/handoff` `{upload_token, kind, feature_id, params}` → `{ok, href_params}`: the card's primary
 *   (the audit row `helper.file.handoff`); it does not consume the token, the target page does.
 * - `DELETE /helper/files/{sid}`: the card's ✕, "Vazgeç", the sheet's close, "Dosyayı kaldır".
 * - `GET /helper/files/examples` and `/helper/files/examples/{kind}.{ext}`: header-only templates (§6.6).
 *
 * The `file` wire type (§7.2) is not in the generated `schema.gen.ts` until HB-23b updates the backend snapshot, so its
 * zod lives here with the same rules (`Txt` / `Texts` reused, strict objects, `Name` ids). When the snapshot gains
 * `file`, switch {@link FileCard} to the generated one; the shape below is the contract the backend must match.
 */
import { z } from "zod";
import { ChoiceCard, ErrorCard, LimitCard, RefusalCard, Texts, Txt } from "@/components/helper/schema.gen";
import { API_PREFIX, HttpError, request } from "./client";

const s = { silent: true } as const;

/** §1.3 / §12: `min(upload_max_mb, council_max_file_mb)`; the client refuses bigger files without a request. */
export const CLASSIFY_MAX_MB = 15;
export const CLASSIFY_MAX_BYTES = CLASSIFY_MAX_MB * 1024 * 1024;
/** §6.3: the stage lives 10 minutes. */
export const STAGE_TTL_MS = 10 * 60 * 1000;

const Name = z.string().max(64).regex(/^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$/);
const Scalar = z.union([z.string().max(64).regex(/^[A-Za-z0-9_\-:.]{1,64}$/), z.number(), z.boolean()]);

export const FileWarning = z.strictObject({
  code: z.string().regex(/^[a-z_]{2,48}$/),
  message: Txt,
  status: z.enum(["info", "warn", "bad"]).default("info"),
});
export type FileWarning = z.infer<typeof FileWarning>;

export const FileRoute = z.strictObject({
  feature_id: Name,
  params: z.record(z.string().regex(/^[a-z][a-z0-9_]*$/), Scalar).default({}),
  label: Txt,
  /** §8.5: ≤ 28 characters, used under 640 px; the accessible name keeps `label` */
  label_short: Txt.nullish(),
  carries_file: z.boolean(),
});
export type FileRoute = z.infer<typeof FileRoute>;

export const FileTerm = z.strictObject({
  term_id: z.number().int().nullable(),
  name: Txt,
  source: z.enum(["file_name", "sheet_title"]),
  matches_active: z.boolean(),
});
export type FileTerm = z.infer<typeof FileTerm>;

export const FileCard = z.strictObject({
  v: z.literal(1).default(1),
  id: z.string().regex(/^[a-f0-9]{8,32}$/),
  type: z.literal("file"),
  action: z.literal("classify_file").default("classify_file"),
  title: Txt.nullish(),
  lang: z.enum(["tr", "en"]).optional(),
  state: z.enum(["detected", "unknown", "needs_planner"]),
  kind: Name.nullish(),
  kind_label: Txt.nullish(),
  certainty: z.enum(["sure", "likely", "unsure"]).nullish(),
  format: Name,
  evidence: Texts.default({}),
  term: FileTerm.nullish(),
  warnings: z.array(FileWarning).max(4).default([]),
  primary: FileRoute.nullish(),
  secondary: z.array(FileRoute).max(2).default([]),
  explain: Texts.default({}),
  examples: z.array(Name).max(8).default([]),
  ai_sorted: z.boolean().default(false),
});
export type FileCard = z.infer<typeof FileCard>;

/** What classify / route can answer with: the router's own card, or a reused v1 card. */
export const FileAnswerCard = z.discriminatedUnion("type", [FileCard, ChoiceCard, RefusalCard, ErrorCard, LimitCard]);
export type FileAnswerCard = z.infer<typeof FileAnswerCard>;

export const Stage = z.object({
  upload_token: z.string().min(16).max(4000).regex(/^[A-Za-z0-9_\-.]+$/),
  expires_at: z.string(),
  size: z.number().int().nonnegative().optional(),
  format: z.string().optional(),
  /** the stage id for `DELETE /helper/files/{sid}`; when absent it is read from the token's payload (`sid`) */
  sid: z.string().regex(/^[A-Za-z0-9_\-]{4,64}$/).optional(),
});
export type Stage = z.infer<typeof Stage>;

/**
 * `stage`: the (first) staged file; `stages`: one per readable file when several were dropped (the setup wizard);
 * `resend: true`: `HELPER_FILE_STAGE=off`, nothing was staged and the target page re-sends the browser's File.
 */
export const ClassifyOut = z.object({ card: FileAnswerCard, stage: Stage.nullish(), stages: z.array(Stage).nullish(), resend: z.boolean().nullish() });
export type ClassifyOut = z.infer<typeof ClassifyOut>;

export const RouteOut = z.object({ card: FileAnswerCard });
export const HandoffOut = z.object({ ok: z.boolean(), href_params: z.record(z.string(), Scalar).nullish() }).passthrough();
export type HandoffOut = z.infer<typeof HandoffOut>;

export const ExampleItem = z.object({ kind: Name, format: z.enum(["xlsx", "csv", "ics", "sql", "json"]), file_name: z.string().nullish(), label: Txt.nullish(), description: Txt.nullish() }).passthrough();
export const ExamplesOut = z.array(ExampleItem).catch([]);
export type ExampleItem = z.infer<typeof ExampleItem>;

/** The template's extension per kind (`GET /helper/files/examples` → `format`; §6.6). */
export const EXAMPLE_EXT: Readonly<Record<string, ExampleItem["format"]>> = {
  planning_list: "xlsx",
  exam_list: "xlsx",
  weekly_grid: "xlsx",
  room_master: "csv",
  users_csv: "csv",
  calendar_ics: "ics",
  crbs_dump: "sql",
  intake_json: "json",
};

/** The stage id of a token: `base64url(payload).base64url(hmac)`, payload `{k: "file", s: <sid>, …}` (§6.3). Null when unreadable. */
export function stageIdOf(token: string): string | null {
  const head = token.split(".")[0];
  if (!head) return null;
  try {
    const b64 = head.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(head.length / 4) * 4, "=");
    const json = JSON.parse(atob(b64)) as { s?: unknown; sid?: unknown };
    const sid = json.s ?? json.sid;
    return typeof sid === "string" && /^[A-Za-z0-9_\-]{4,64}$/.test(sid) ? sid : null;
  } catch {
    return null;
  }
}

export const sidOf = (stage: Pick<Stage, "upload_token" | "sid">): string | null => stage.sid ?? stageIdOf(stage.upload_token);

/** 410 `stage_expired` / `stage_used` (§6.3): the token can no longer be used. */
export function isStageGone(err: unknown): boolean {
  if (!(err instanceof HttpError)) return false;
  if (err.status === 410) return true;
  const d = err.detail as { code?: unknown; detail?: { code?: unknown } } | null | undefined;
  const code = d && typeof d === "object" ? (typeof d.code === "string" ? d.code : typeof d.detail?.code === "string" ? d.detail.code : null) : null;
  return code === "stage_expired" || code === "stage_used";
}

export const helperFilesApi = {
  /** one file, or several (planners: one setup-wizard card with a stage per readable file); `termId`: the page's active term */
  classify: (files: File | readonly File[], opts: { context?: string | null; lang: string; termId?: number | null; signal?: AbortSignal }) => {
    const fd = new FormData();
    for (const f of Array.isArray(files) ? files : [files]) fd.append("file", f, f.name);
    if (opts.context) fd.append("context", opts.context);
    fd.append("lang", opts.lang);
    if (opts.termId) fd.append("term_id", String(opts.termId));
    return request("/helper/files/classify", { ...s, method: "POST", formData: fd, schema: ClassifyOut, signal: opts.signal });
  },
  route: (uploadToken: string, kind: string, termId?: number | null) =>
    request("/helper/files/route", { ...s, method: "POST", body: termId ? { upload_token: uploadToken, kind, term_id: termId } : { upload_token: uploadToken, kind }, schema: RouteOut }),
  /** one token, or `upload_tokens` for several files (the setup wizard) */
  handoff: (body: { upload_token?: string; upload_tokens?: string[]; kind: string | null; feature_id: string; params: Record<string, string | number | null> }) =>
    request("/helper/files/handoff", { ...s, method: "POST", body, schema: HandoffOut }),
  drop: (sid: string) => request<void>(`/helper/files/${encodeURIComponent(sid)}`, { ...s, method: "DELETE" }),
  examples: () => request("/helper/files/examples", { ...s, schema: ExamplesOut }),
};

/** Fire-and-forget stage deletion (✕, Vazgeç, close): never blocks or fails the person's action. */
export function dropStage(stage: Pick<Stage, "upload_token" | "sid"> | null | undefined): void {
  if (!stage) return;
  const sid = sidOf(stage);
  if (sid) void helperFilesApi.drop(sid).catch(() => undefined);
}

/** The download link of a header-only template (a static file of the API; no data). */
export const exampleHref = (kind: string, ext: string): string => `${API_PREFIX}/helper/files/examples/${encodeURIComponent(kind)}.${ext}`;
