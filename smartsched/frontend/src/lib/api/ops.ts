"use client";
/**
 * Operations panel (W3-OPS; backend `app/api/v1/ops.py`, `app/core/observability.py`).
 *
 * Admin (`setup.settings` or `planning.admin`):
 * - `GET /ops/status`: service cards (`api`, `db`, `queues`, `mail`, `deliveries`, `disk`, `errors`; each `{status: ok |
 *   warn | down | off | unknown, ...}`), `services.{grafana,prometheus,loki}` reachability, `release` (version, sha,
 *   deployed_at), `podci` (reachability + `last_run {state, branch, sha, started}`), firing `alerts[]`.
 * - `GET /ops/requests?minutes=` per-minute `points[] {t, requests, errors, p95_ms}`; `source` `prometheus` | `process`.
 * - `GET /ops/errors?status=&source=&limit=` grouped error events + `counts` by status; `GET /ops/errors/{id}` with the
 *   scrubbed `sample_stack`; `POST /ops/errors/{id}/status {status: open | acknowledged | resolved | ignored}`.
 * - `GET /ops/logs?service=&q=&limit=&minutes=` the last lines from Loki (`available: false` + message when it is off).
 * - `GET /ops/dashboards`: the provisioned Grafana dashboards (`url`, `panels[].embed`, same origin under /grafana/).
 * Anyone (rate limited, <= 8 KB, scrubbed again on the server): `POST /ops/errors` — the browser error reporter below.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "./client";

const s = { silent: true } as const;

export type CardStatus = "ok" | "warn" | "down" | "off" | "unknown";
export interface Card {
  status: CardStatus;
  [k: string]: unknown;
}
export interface Probe {
  configured: boolean;
  reachable: boolean;
  status: CardStatus;
  latency_ms?: number;
  http_status?: number;
  error?: string;
}
export interface PodCi extends Probe {
  last_run?: { state: string; branch: string; sha: string; started: string };
}
export interface OpsAlert {
  name: string;
  severity: string;
  summary_tr?: string | null;
  summary_en?: string | null;
  since?: string | null;
}
export interface OpsStatus {
  generated_at: string;
  release: { version: string; sha: string | null; deployed_at: string | null; environment: string };
  api: Card & { uptime_s: number; workers: number };
  db: Card & { latency_ms: number; migrations: string; migration_head?: string | null; dialect: string };
  queues: Card & { queued: number; running: number; failed_24h: number; stalled_runs?: number[] };
  mail: Card & { pending: number; failed: number; unsent: number; sent: number; oldest_pending_min: number | null };
  deliveries: Card & { failed: number };
  disk: Card & { total_bytes?: number; used_bytes?: number; free_bytes?: number; used_pct?: number };
  errors: Card & { open: number; seen_24h: number };
  /** the last successful backup (deploy/backup.sh textfile metric, else Prometheus); absent on older backends */
  backup?: Card & { last_success_at: string | null; age_h: number | null; source: "textfile" | "prometheus" | null; stale_after_h: number };
  services: { grafana: Probe; prometheus: Probe; loki: Probe };
  grafana_path: string;
  podci: PodCi;
  alerts: OpsAlert[];
}
export interface RequestPoint {
  t: number;
  requests: number;
  errors: number;
  p95_ms: number | null;
}
export interface RequestSeries {
  source: "prometheus" | "process";
  points: RequestPoint[];
}
export const ERROR_STATUSES = ["open", "acknowledged", "resolved", "ignored"] as const;
export type ErrorStatus = (typeof ERROR_STATUSES)[number];
export interface ErrorGroup {
  id: number;
  fingerprint: string;
  source: "backend" | "frontend";
  kind: string;
  message: string;
  route: string | null;
  method: string | null;
  status_code: number | null;
  user_role: string | null;
  release: string | null;
  count: number;
  first_seen: string | null;
  last_seen: string | null;
  status: ErrorStatus;
  reopened: number;
  last_request_id: string | null;
  sample_stack?: string | null;
}
export interface ErrorList {
  items: ErrorGroup[];
  counts: Partial<Record<ErrorStatus, number>>;
  retention_days: number;
}
export interface LogLine {
  ts: number;
  service: string;
  line: string;
}
export interface LogTail {
  service: string;
  services: string[];
  available: boolean;
  lines: LogLine[];
  message_tr?: string;
  message_en?: string;
}
export interface DashboardPanel {
  id: number;
  title_tr: string;
  title_en: string;
  embed: string;
}
export interface Dashboard {
  uid: string;
  title_tr: string;
  title_en: string;
  url: string;
  panels: DashboardPanel[];
}
export interface Dashboards {
  grafana: Probe & { path: string };
  dashboards: Dashboard[];
}

export const LOG_SERVICES = ["backend", "frontend", "proxy", "db", "caddy", "grafana", "prometheus", "loki", "alloy"] as const;

export const ops = {
  status: () => request<OpsStatus>("/ops/status", s),
  requests: (minutes: number) => request<RequestSeries>("/ops/requests", { ...s, query: { minutes } }),
  errors: (status: string, source?: string) => request<ErrorList>("/ops/errors", { ...s, query: { status, source, limit: 100 } }),
  error: (id: number) => request<ErrorGroup>(`/ops/errors/${id}`, s),
  setStatus: (id: number, status: ErrorStatus) => request<ErrorGroup>(`/ops/errors/${id}/status`, { ...s, method: "POST", body: { status } }),
  logs: (service: string, q: string, limit: number, minutes: number) => request<LogTail>("/ops/logs", { ...s, query: { service, q: q || undefined, limit, minutes } }),
  dashboards: () => request<Dashboards>("/ops/dashboards", s),
};

export function useOpsStatus() {
  return useQuery({ queryKey: ["ops", "status"], queryFn: ops.status, refetchInterval: 30_000 });
}
export function useOpsRequests(minutes: number) {
  return useQuery({ queryKey: ["ops", "requests", minutes], queryFn: () => ops.requests(minutes), refetchInterval: 60_000, placeholderData: keepPreviousData });
}
export function useOpsErrors(status: string) {
  return useQuery({ queryKey: ["ops", "errors", status], queryFn: () => ops.errors(status), refetchInterval: 60_000, placeholderData: keepPreviousData });
}
export function useOpsError(id: number | null) {
  return useQuery({ queryKey: ["ops", "error", id], queryFn: () => ops.error(id as number), enabled: id != null });
}
export function useSetErrorStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: ErrorStatus }) => ops.setStatus(id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ops"] }),
  });
}
export function useOpsLogs(args: { service: string; q: string; limit: number; minutes: number } | null) {
  return useQuery({
    queryKey: ["ops", "logs", args],
    queryFn: () => ops.logs(args!.service, args!.q, args!.limit, args!.minutes),
    enabled: args != null,
  });
}
export function useOpsDashboards() {
  return useQuery({ queryKey: ["ops", "dashboards"], queryFn: ops.dashboards, staleTime: 60_000 });
}

/* --------------------------------------------------------------------------------------- browser error reporter */

export interface ClientErrorReport {
  message: string;
  kind?: string;
  stack?: string;
  component_stack?: string;
  url?: string;
  origin: "window.onerror" | "unhandledrejection" | "boundary";
}

const MAX_BYTES = 8 * 1024;
const PER_MINUTE = 10;
let sentAt: number[] = [];
const seen = new Map<string, number>();

/** Light client-side scrub (the server scrubs again): e-mail addresses, tokens, query strings. */
export function scrubClient(text: string | undefined | null): string {
  if (!text) return "";
  return text
    .replace(/eyJ[\w-]{6,}\.[\w-]{6,}\.[\w-]{6,}/g, "[token]")
    .replace(/(bearer|basic)\s+[\w.~+/=-]{8,}/gi, "$1 [token]")
    .replace(/[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g, "[email]")
    .replace(/(https?:\/\/[^\s?#"']+|\/[\w./%-]*)\?[^\s"')]*/g, "$1?[query]");
}

/** Trim a report to the server's 8 KB limit (stack first, then component stack, then message). */
export function fitReport(r: ClientErrorReport): ClientErrorReport {
  const out: ClientErrorReport = {
    ...r,
    message: scrubClient(r.message).slice(0, 1000),
    kind: r.kind?.slice(0, 120),
    stack: scrubClient(r.stack).slice(0, 5000) || undefined,
    component_stack: scrubClient(r.component_stack).slice(0, 1500) || undefined,
    url: r.url ? scrubClient(r.url).slice(0, 500) : undefined,
  };
  while (new Blob([JSON.stringify(out)]).size > MAX_BYTES && (out.stack?.length ?? 0) > 200) out.stack = out.stack!.slice(0, Math.floor(out.stack!.length / 2));
  return out;
}

/** POST one browser error (deduplicated for 60 s, at most 10 a minute per tab). Never throws, never toasts. */
export function reportClientError(r: ClientErrorReport, now: number = Date.now()): boolean {
  try {
    const key = `${r.kind ?? ""}|${r.message}`.slice(0, 300);
    const last = seen.get(key);
    if (last !== undefined && now - last < 60_000) return false;
    sentAt = sentAt.filter((t) => now - t < 60_000);
    if (sentAt.length >= PER_MINUTE) return false;
    sentAt.push(now);
    seen.set(key, now);
    if (seen.size > 200) seen.clear();
    const body = JSON.stringify(fitReport(r));
    void fetch("/api/v1/ops/errors", { method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: true, credentials: "same-origin" }).catch(() => undefined);
    return true;
  } catch {
    return false;
  }
}

/** Test hook: forget the reporter's dedupe / rate state. */
export function resetClientReporter(): void {
  sentAt = [];
  seen.clear();
}

function describe(value: unknown): { message: string; kind?: string; stack?: string } {
  if (value instanceof Error) return { message: value.message || value.name, kind: value.name, stack: value.stack };
  if (value && typeof value === "object" && "name" in value && "message" in value) {
    const v = value as { name: unknown; message: unknown; stack?: unknown };
    return { message: String(v.message || v.name), kind: String(v.name), stack: typeof v.stack === "string" ? v.stack : undefined };
  }
  if (typeof value === "string") return { message: value };
  try {
    return { message: JSON.stringify(value).slice(0, 500) };
  } catch {
    return { message: String(value) };
  }
}

/** `window.onerror` + `unhandledrejection` → `reportClientError`. Returns the uninstall function. */
export function installErrorReporter(target: Window = window): () => void {
  const onError = (e: ErrorEvent) => {
    // resource load errors (img/script) have no error object and no message: not application errors
    if (!e.error && !e.message) return;
    const d = describe(e.error ?? e.message);
    reportClientError({ ...d, url: target.location?.href, origin: "window.onerror" });
  };
  const onRejection = (e: PromiseRejectionEvent) => {
    const d = describe(e.reason);
    // aborted fetches (navigations) are not errors
    if (d.kind === "AbortError") return;
    reportClientError({ ...d, kind: d.kind ?? "UnhandledRejection", url: target.location?.href, origin: "unhandledrejection" });
  };
  target.addEventListener("error", onError);
  target.addEventListener("unhandledrejection", onRejection);
  return () => {
    target.removeEventListener("error", onError);
    target.removeEventListener("unhandledrejection", onRejection);
  };
}
