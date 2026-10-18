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

/** CH-06 summary facts: requests per minute over the window, and the minute with the most 5xx (null when none). */
export function requestsDigest(points: RequestPoint[]): { perMinute: number; spike: { t: number; errors: number } | null } {
  const requests = points.reduce((a, p) => a + p.requests, 0);
  let spike: { t: number; errors: number } | null = null;
  for (const p of points) if (p.errors > 0 && (!spike || p.errors > spike.errors)) spike = { t: p.t, errors: p.errors };
  return { perMinute: points.length ? Math.round(requests / points.length) : 0, spike };
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
