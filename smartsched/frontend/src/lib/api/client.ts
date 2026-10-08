/**
 * Fetch wrapper: same-origin `/api/v1/*` (proxied by the Next route handler, which
 * attaches the JWT from the httpOnly cookie and forwards to the FastAPI backend).
 */
import type { z } from "zod";
import { ApiError } from "./schemas";

export const API_PREFIX = "/api/v1";

export class HttpError extends Error {
  readonly status: number;
  readonly errorId: string | undefined;
  readonly detail: unknown;
  constructor(status: number, message: string, detail?: unknown, errorId?: string) {
    super(message);
    this.name = "HttpError";
    this.status = status;
    this.detail = detail;
    this.errorId = errorId;
  }
}

type Listener = (error: HttpError) => void;
const errorListeners = new Set<Listener>();

/** UI layers (toaster, auth guard) subscribe here; keeps the client free of React. */
export function onApiError(listener: Listener): () => void {
  errorListeners.add(listener);
  return () => errorListeners.delete(listener);
}

export type Query = Record<string, string | number | boolean | null | undefined>;

export function buildUrl(path: string, query?: Query): string {
  const url = path.startsWith("/") ? `${API_PREFIX}${path}` : `${API_PREFIX}/${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "") continue;
    params.set(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

interface RequestOptions<T> {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  query?: Query;
  body?: unknown;
  /** multipart upload; body is ignored when set */
  formData?: FormData;
  schema?: z.ZodType<T>;
  signal?: AbortSignal;
  /** suppress global error toast (caller handles) */
  silent?: boolean;
}

async function parseError(res: Response): Promise<HttpError> {
  let detail: unknown;
  let message = `${res.status} ${res.statusText}`;
  let errorId: string | undefined;
  try {
    const json: unknown = await res.json();
    const parsed = ApiError.safeParse(json);
    if (parsed.success) {
      detail = parsed.data.detail;
      errorId = parsed.data.error_id;
      message = typeof parsed.data.detail === "string" ? parsed.data.detail : parsed.data.detail.map((d) => d.msg).join("; ");
    } else {
      detail = json;
    }
  } catch {
    /* non-JSON error body */
  }
  return new HttpError(res.status, message, detail, errorId);
}

export async function request<T = unknown>(path: string, opts: RequestOptions<T> = {}): Promise<T> {
  const { method = "GET", query, body, formData, schema, signal, silent } = opts;
  const headers: Record<string, string> = { Accept: "application/json" };
  let payload: BodyInit | undefined;
  if (formData) {
    payload = formData;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(buildUrl(path, query), { method, headers, body: payload, signal, credentials: "same-origin" });
  } catch (e) {
    const err = new HttpError(0, e instanceof Error ? e.message : "Network error");
    if (!silent) errorListeners.forEach((l) => l(err));
    throw err;
  }
  if (!res.ok) {
    const err = await parseError(res);
    if (!silent) errorListeners.forEach((l) => l(err));
    throw err;
  }
  if (res.status === 204) return undefined as T;
  const json: unknown = await res.json();
  if (!schema) return json as T;
  const parsed = schema.safeParse(json);
  if (!parsed.success) {
    const err = new HttpError(500, `Invalid response for ${method} ${path}: ${parsed.error.issues[0]?.message ?? "schema mismatch"}`, parsed.error.issues);
    if (!silent) errorListeners.forEach((l) => l(err));
    throw err;
  }
  return parsed.data;
}
