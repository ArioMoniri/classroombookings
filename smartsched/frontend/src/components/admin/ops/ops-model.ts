/** Pure helpers for the operations panel (W3-OPS): formatting, card tones, the mini chart geometry. */
import type { CardStatus, OpsStatus, RequestPoint } from "@/lib/api/ops";

export const TONE: Record<CardStatus, string> = {
  ok: "bg-status-feasible text-status-feasible-fg",
  warn: "bg-status-warning text-status-warning-fg",
  down: "bg-status-infeasible text-status-infeasible-fg",
  off: "bg-fill-2 text-label-2",
  unknown: "bg-fill-2 text-label-2",
};

export function formatBytes(n: number | undefined | null, locale: string): string {
  if (n == null || !Number.isFinite(n)) return "–";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: v >= 100 || i === 0 ? 0 : 1 }).format(v)} ${units[i]}`;
}

/** `3 g 4 sa` / `3 d 4 h`, `12 dk` / `12 min` */
export function formatUptime(seconds: number, locale: string): string {
  const tr = locale.startsWith("tr");
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return tr ? `${d} g ${h} sa` : `${d} d ${h} h`;
  if (h > 0) return tr ? `${h} sa ${m} dk` : `${h} h ${m} min`;
  return tr ? `${m} dk` : `${m} min`;
}

export type CardKey = "api" | "db" | "queues" | "mail" | "disk" | "errors" | "grafana" | "prometheus" | "loki" | "podci";
export const CARD_ORDER: CardKey[] = ["api", "db", "queues", "mail", "disk", "errors", "grafana", "prometheus", "loki", "podci"];

export function cardStatus(s: OpsStatus, key: CardKey): CardStatus {
  switch (key) {
    case "grafana":
    case "prometheus":
    case "loki":
      return s.services[key].status;
    case "podci":
      return s.podci.status;
    default:
      return s[key].status;
  }
}

/** The worst status first: what needs a look. */
export function overall(s: OpsStatus): CardStatus {
  const all = CARD_ORDER.map((k) => cardStatus(s, k));
  if (all.includes("down")) return "down";
  if (all.includes("warn") || s.alerts.length) return "warn";
  return "ok";
}

export interface ChartGeometry {
  bars: { x: number; h: number; err: number; t: number }[];
  line: string;
  maxRequests: number;
  maxP95: number;
}

/** Bars for requests (errors stacked in red) and a polyline for p95, in a `width × height` viewBox. */
export function chartGeometry(points: RequestPoint[], width: number, height: number): ChartGeometry {
  const n = Math.max(1, points.length);
  const step = width / n;
  const maxRequests = Math.max(1, ...points.map((p) => p.requests));
  const p95s = points.map((p) => p.p95_ms ?? 0);
  const maxP95 = Math.max(1, ...p95s);
  const bars = points.map((p, i) => ({ x: i * step, h: (p.requests / maxRequests) * height, err: (p.errors / maxRequests) * height, t: p.t }));
  const line = points
    .map((p, i) => (p.p95_ms == null ? null : `${(i * step + step / 2).toFixed(1)},${(height - (p.p95_ms / maxP95) * height).toFixed(1)}`))
    .filter(Boolean)
    .join(" ");
  return { bars, line, maxRequests, maxP95 };
}

export function totals(points: RequestPoint[]): { requests: number; errors: number; errorPct: number; p95: number | null } {
  const requests = points.reduce((a, p) => a + p.requests, 0);
  const errors = points.reduce((a, p) => a + p.errors, 0);
  const p95s = points.map((p) => p.p95_ms).filter((v): v is number => v != null);
  return { requests, errors, errorPct: requests ? (errors / requests) * 100 : 0, p95: p95s.length ? Math.max(...p95s) : null };
}

/** Grafana is embeddable only on the same origin (W3-SEC sets frame-ancestors 'self' for /grafana/). */
export function sameOrigin(url: string, origin: string): boolean {
  try {
    return new URL(url, origin).origin === origin;
  } catch {
    return false;
  }
}
