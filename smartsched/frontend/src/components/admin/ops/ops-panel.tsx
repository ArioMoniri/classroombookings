"use client";
/**
 * Yönetim › Operasyon (W3-OPS, `/admin/ops`): service status cards, firing alerts, the request/latency mini chart,
 * grouped error events (new → acknowledged → resolved / ignored), links into (and same-origin panels of) the Grafana
 * dashboards, and a log tail from Loki. Admins only (`setup.settings` or `planning.admin`; the backend checks again).
 * Phone-ready: one column, 44 px targets, 16 px inputs; nothing depends on hover.
 */
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Alert, Loading, NoAccess, PageTitle } from "@/components/admin/kit";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { HttpError } from "@/lib/api/client";
import {
  LOG_SERVICES,
  useOpsDashboards,
  useOpsError,
  useOpsErrors,
  useOpsLogs,
  useOpsRequests,
  useOpsStatus,
  useSetErrorStatus,
  type CardStatus,
  type ErrorGroup,
  type ErrorStatus,
  type OpsStatus,
} from "@/lib/api/ops";
import type { MessageKey } from "@/lib/i18n";
import { intlLocale } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { usePermissions } from "@/lib/permissions";
import { cn } from "@/lib/utils";
import { CARD_ORDER, TONE, cardStatus, chartGeometry, formatBytes, formatUptime, overall, sameOrigin, totals, type CardKey } from "./ops-model";

const OPS_PERMS = ["setup.settings", "planning.admin"];

function useWhen() {
  const { locale } = useI18n();
  return (iso: string | null | undefined) => {
    if (!iso) return "–";
    const d = new Date(iso.endsWith("Z") || /[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(intlLocale(locale), { dateStyle: "short", timeStyle: "short" });
  };
}

function StatusPill({ status }: { status: CardStatus }) {
  const { t } = useI18n();
  return <span className={cn("rounded-full px-2 py-0.5 type-caption font-medium", TONE[status])}>{t(`ops.status.${status}` as MessageKey)}</span>;
}

export function OpsPanel() {
  const { t } = useI18n();
  const { can, loading } = usePermissions();
  const status = useOpsStatus();
  const [logFilter, setLogFilter] = useState<{ service: string; q: string } | null>(null);
  const logRef = useRef<HTMLHeadingElement>(null);
  if (loading) return <Loading />;
  if (!can(OPS_PERMS)) return <NoAccess title={t("crbs.admin.noAccessTitle")} body={t("ops.noAccess")} />;
  const forbidden = status.error instanceof HttpError && status.error.status === 403;
  if (forbidden) return <NoAccess title={t("crbs.admin.noAccessTitle")} body={t("ops.noAccess")} />;

  const findInLogs = (requestId: string) => {
    setLogFilter({ service: "backend", q: requestId });
    requestAnimationFrame(() => logRef.current?.focus());
  };

  return (
    <div className="flex max-w-6xl flex-col gap-6" data-testid="ops-panel">
      <PageTitle title={t("ops.title")} subtitle={t("ops.lead")} actions={status.data ? <StatusPill status={overall(status.data)} /> : null} />
      {status.isLoading ? <Loading /> : null}
      {status.isError && !forbidden ? <Alert tone="error">{t("ops.loadError")}</Alert> : null}
      {status.data ? <StatusCards s={status.data} /> : null}
      {status.data?.alerts.length ? <Alerts s={status.data} /> : null}
      <RequestsChart />
      <ErrorGroups onFindInLogs={findInLogs} />
      <GrafanaSection />
      <LogTail headingRef={logRef} preset={logFilter} />
    </div>
  );
}

/* ------------------------------------------------------------------------------------------------ status cards */

function StatusCards({ s }: { s: OpsStatus }) {
  const { t, locale } = useI18n();
  const when = useWhen();
  const lines: Record<CardKey, string[]> = {
    api: [t("ops.card.api.uptime", { v: formatUptime(s.api.uptime_s, locale) }), t("ops.card.api.workers", { n: s.api.workers }), s.release.sha ? t("ops.card.api.release", { sha: s.release.sha.slice(0, 8) }) : t("ops.card.api.version", { v: s.release.version }), ...(s.release.deployed_at ? [t("ops.card.api.deployed", { when: when(s.release.deployed_at) })] : [])],
    db: [t("ops.card.db.latency", { ms: s.db.latency_ms }), t(`ops.card.db.migrations.${s.db.migrations}` as MessageKey)],
    queues: [t("ops.card.queues.line", { queued: s.queues.queued, running: s.queues.running }), t("ops.card.queues.failed", { n: s.queues.failed_24h }), ...(s.queues.stalled_runs?.length ? [t("ops.card.queues.stalled", { n: s.queues.stalled_runs.length })] : [])],
    mail: [t("ops.card.mail.line", { pending: s.mail.pending, failed: s.mail.failed }), s.mail.oldest_pending_min != null ? t("ops.card.mail.oldest", { min: Math.round(s.mail.oldest_pending_min) }) : t("ops.card.mail.unsent", { n: s.mail.unsent })],
    disk: s.disk.status === "unknown" ? [t("ops.status.unknown")] : [t("ops.card.disk.used", { pct: s.disk.used_pct ?? 0 }), t("ops.card.disk.free", { free: formatBytes(s.disk.free_bytes, intlLocale(locale)) })],
    errors: [t("ops.card.errors.open", { n: s.errors.open }), t("ops.card.errors.day", { n: s.errors.seen_24h })],
    grafana: [probeLine(s.services.grafana)],
    prometheus: [probeLine(s.services.prometheus)],
    loki: [probeLine(s.services.loki)],
    podci: s.podci.last_run ? [t("ops.card.podci.run", { state: t(`ops.ci.${s.podci.last_run.state}` as MessageKey), sha: s.podci.last_run.sha }), s.podci.last_run.started] : [probeLine(s.podci)],
  };
  function probeLine(p: { configured: boolean; reachable: boolean; latency_ms?: number }) {
    if (!p.configured) return t("ops.probe.off");
    return p.reachable ? t("ops.probe.up", { ms: p.latency_ms ?? 0 }) : t("ops.probe.down");
  }
  return (
    <section aria-labelledby="ops-cards-h">
      <h2 id="ops-cards-h" className="sr-only">
        {t("ops.cardsTitle")}
      </h2>
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {CARD_ORDER.map((k) => {
          const st = cardStatus(s, k);
          return (
            <li key={k}>
              <Card className="h-full gap-1.5 px-4 py-3" data-testid={`ops-card-${k}`} data-status={st}>
                <div className="flex items-center justify-between gap-2">
                  <p className="type-headline text-label-1">{t(`ops.card.${k}.title` as MessageKey)}</p>
                  <StatusPill status={st} />
                </div>
                {lines[k].map((l, i) => (
                  <p key={i} className="type-footnote text-label-2">
                    {l}
                  </p>
                ))}
                {k === "podci" && s.podci.configured ? (
                  <a className="type-footnote text-tint-text underline-offset-2 hover:underline pointer-coarse:min-h-11 pointer-coarse:py-2" href="/ci/">
                    {t("ops.card.podci.open")}
                  </a>
                ) : null}
              </Card>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Alerts({ s }: { s: OpsStatus }) {
  const { t, locale } = useI18n();
  return (
    <section aria-labelledby="ops-alerts-h" data-testid="ops-alerts">
      <h2 id="ops-alerts-h" className="mb-2 type-title-3 text-label-1">
        {t("ops.alerts.title", { n: s.alerts.length })}
      </h2>
      <ul className="flex flex-col gap-2">
        {s.alerts.map((a, i) => (
          <li key={`${a.name}-${i}`}>
            <Alert tone={a.severity === "critical" ? "error" : "warning"}>{(locale === "tr" ? a.summary_tr : a.summary_en) ?? a.name}</Alert>
          </li>
        ))}
      </ul>
    </section>
  );
}

/* ----------------------------------------------------------------------------------------------- mini chart */

const RANGES = ["30", "60", "180"] as const;

function RequestsChart() {
  const { t, locale } = useI18n();
  const [range, setRange] = useState<(typeof RANGES)[number]>("60");
  const q = useOpsRequests(Number(range));
  const points = q.data?.points ?? [];
  const W = 600;
  const H = 120;
  const g = chartGeometry(points, W, H);
  const tot = totals(points);
  const nf = new Intl.NumberFormat(intlLocale(locale), { maximumFractionDigits: 1 });
  return (
    <section aria-labelledby="ops-chart-h" data-testid="ops-chart">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 id="ops-chart-h" className="type-title-3 text-label-1">
          {t("ops.chart.title")}
        </h2>
        <SegmentedControl aria-label={t("ops.chart.range")} value={range} onValueChange={(v) => setRange(v as (typeof RANGES)[number])} options={RANGES.map((r) => ({ value: r, label: t("ops.chart.minutes", { n: Number(r) }), testId: `ops-range-${r}` }))} />
      </div>
      <Card className="gap-2 px-4 py-3">
        <p className="type-footnote text-label-2" data-testid="ops-chart-summary">
          {t("ops.chart.summary", { requests: nf.format(tot.requests), errors: nf.format(tot.errors), pct: nf.format(tot.errorPct), p95: tot.p95 == null ? "–" : nf.format(tot.p95) })}
        </p>
        <svg viewBox={`0 0 ${W} ${H}`} className="h-28 w-full" role="img" aria-label={t("ops.chart.aria", { requests: tot.requests, errors: tot.errors })} preserveAspectRatio="none">
          {g.bars.map((b) => (
            <g key={b.t}>
              <rect x={b.x + 1} y={H - b.h} width={Math.max(1, W / Math.max(1, points.length) - 2)} height={b.h} className="fill-tint/40" />
              {b.err > 0 ? <rect x={b.x + 1} y={H - b.err} width={Math.max(1, W / Math.max(1, points.length) - 2)} height={b.err} className="fill-status-infeasible-solid" /> : null}
            </g>
          ))}
          {g.line ? <polyline points={g.line} fill="none" strokeWidth={2} className="stroke-status-warning-solid" vectorEffect="non-scaling-stroke" /> : null}
        </svg>
        <p className="type-caption text-label-3">{q.data?.source === "prometheus" ? t("ops.chart.sourceProm") : t("ops.chart.sourceProcess")}</p>
      </Card>
    </section>
  );
}

/* ---------------------------------------------------------------------------------------------- error groups */

const FILTERS = ["open", "acknowledged", "resolved", "ignored", "all"] as const;
type Filter = (typeof FILTERS)[number];
const NEXT: Record<ErrorStatus, ErrorStatus[]> = {
  open: ["acknowledged", "resolved", "ignored"],
  acknowledged: ["resolved", "ignored", "open"],
  resolved: ["open"],
  ignored: ["open"],
};

function ErrorGroups({ onFindInLogs }: { onFindInLogs: (requestId: string) => void }) {
  const { t } = useI18n();
  const [filter, setFilter] = useState<Filter>("open");
  const q = useOpsErrors(filter === "all" ? "" : filter);
  const setStatus = useSetErrorStatus();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [open, setOpen] = useState<number | null>(null);
  const items = q.data?.items ?? [];

  const act = (e: ErrorGroup, status: ErrorStatus) =>
    setStatus.mutate(
      { id: e.id, status },
      {
        onSuccess: () => {
          toast.success(t(`ops.errors.done.${status}` as MessageKey));
          headingRef.current?.focus(); // the row may leave the list: focus never falls to <body>
        },
        onError: () => toast.error(t("ops.errors.actionFailed")),
      },
    );

  return (
    <section aria-labelledby="ops-errors-h" data-testid="ops-errors">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 id="ops-errors-h" ref={headingRef} tabIndex={-1} className="type-title-3 text-label-1 focus-visible:outline-2">
          {t("ops.errors.title")}
        </h2>
        <SegmentedControl aria-label={t("ops.errors.filter")} value={filter} onValueChange={(v) => setFilter(v as Filter)} options={FILTERS.map((f) => ({ value: f, label: `${t(`ops.errors.filters.${f}` as MessageKey)}${f !== "all" && q.data?.counts[f] ? ` (${q.data.counts[f]})` : ""}`, text: t(`ops.errors.filters.${f}` as MessageKey), testId: `ops-errors-filter-${f}` }))} />
      </div>
      {q.isLoading ? <Loading /> : null}
      {q.isError ? <Alert tone="error">{t("ops.loadError")}</Alert> : null}
      {q.isSuccess && !items.length ? (
        <p className="rounded-xl bg-fill-3 p-3 type-callout text-label-2" data-testid="ops-errors-empty">
          {t(`ops.errors.empty.${filter}` as MessageKey)}
        </p>
      ) : null}
      <ul className="flex flex-col gap-2">
        {items.map((e) => (
          <li key={e.id}>
            <ErrorRow e={e} expanded={open === e.id} onToggle={() => setOpen(open === e.id ? null : e.id)} onAct={(st) => act(e, st)} busy={setStatus.isPending} onFindInLogs={onFindInLogs} />
          </li>
        ))}
      </ul>
      {q.data ? <p className="mt-2 type-caption text-label-3">{t("ops.errors.retention", { days: q.data.retention_days })}</p> : null}
    </section>
  );
}

function ErrorRow({ e, expanded, onToggle, onAct, busy, onFindInLogs }: { e: ErrorGroup; expanded: boolean; onToggle: () => void; onAct: (s: ErrorStatus) => void; busy: boolean; onFindInLogs: (rid: string) => void }) {
  const { t } = useI18n();
  const when = useWhen();
  const detail = useOpsError(expanded ? e.id : null);
  const statusTone: Record<ErrorStatus, CardStatus> = { open: "down", acknowledged: "warn", resolved: "ok", ignored: "off" };
  return (
    <Card className="gap-1.5 px-4 py-3" data-testid={`ops-error-${e.id}`} data-status={e.status}>
      <div className="flex flex-wrap items-center gap-2">
        <span className={cn("rounded-full px-2 py-0.5 type-caption font-medium", TONE[statusTone[e.status]])}>{t(`ops.errors.status.${e.status}` as MessageKey)}</span>
        <span className="rounded-full bg-fill-2 px-2 py-0.5 type-caption text-label-2">{t(`ops.errors.source.${e.source}` as MessageKey)}</span>
        <p className="min-w-0 break-words type-headline text-label-1">{e.kind}</p>
        <span className="ml-auto type-footnote text-label-2" data-testid={`ops-error-count-${e.id}`}>
          {t("ops.errors.count", { n: e.count })}
        </span>
      </div>
      <p className="break-words type-callout text-label-1">{e.message}</p>
      <p className="break-words type-footnote text-label-2">
        {[e.method, e.route].filter(Boolean).join(" ") || "–"}
        {e.status_code ? ` · ${e.status_code}` : ""}
        {e.user_role ? ` · ${t("ops.errors.role", { role: e.user_role })}` : ""}
        {e.release ? ` · ${t("ops.errors.release", { sha: e.release.slice(0, 8) })}` : ""}
      </p>
      <p className="type-footnote text-label-2">
        {t("ops.errors.seen", { first: when(e.first_seen), last: when(e.last_seen) })}
        {e.reopened ? ` · ${t("ops.errors.reopened", { n: e.reopened })}` : ""}
      </p>
      {expanded ? (
        <pre className="max-h-72 overflow-auto rounded-md bg-fill-3 p-2 font-mono type-caption whitespace-pre-wrap break-words text-label-1" data-testid={`ops-error-stack-${e.id}`}>
          {detail.isLoading ? t("crbs.common.loading") : detail.data?.sample_stack || t("ops.errors.noStack")}
        </pre>
      ) : null}
      <div className="flex flex-wrap gap-2 pt-1">
        <Button variant="outline" size="sm" onClick={onToggle} aria-expanded={expanded} data-testid={`ops-error-toggle-${e.id}`}>
          {expanded ? t("ops.errors.hide") : t("ops.errors.details")}
        </Button>
        {NEXT[e.status].map((st) => (
          <Button key={st} variant={st === "resolved" ? "default" : "outline"} size="sm" disabled={busy} onClick={() => onAct(st)} data-testid={`ops-error-${st}-${e.id}`}>
            {t(`ops.errors.action.${st}` as MessageKey)}
          </Button>
        ))}
        {e.last_request_id ? (
          <Button variant="ghost" size="sm" onClick={() => onFindInLogs(e.last_request_id!)} data-testid={`ops-error-logs-${e.id}`}>
            {t("ops.errors.findLogs")}
          </Button>
        ) : null}
      </div>
    </Card>
  );
}

/* --------------------------------------------------------------------------------------------------- Grafana */

function GrafanaSection() {
  const { t, locale } = useI18n();
  const q = useOpsDashboards();
  const [origin, setOrigin] = useState("");
  useEffect(() => setOrigin(window.location.origin), []);
  const up = q.data?.grafana.reachable;
  const embeds = up && origin ? (q.data?.dashboards ?? []).slice(0, 2).map((d) => d.panels[0]).filter((p) => p && sameOrigin(p.embed, origin)) : [];
  return (
    <section aria-labelledby="ops-grafana-h" data-testid="ops-grafana">
      <h2 id="ops-grafana-h" className="mb-2 type-title-3 text-label-1">
        {t("ops.grafana.title")}
      </h2>
      {q.data && !up ? (
        <p className="mb-2 rounded-xl bg-fill-3 p-3 type-callout text-label-2" data-testid="ops-grafana-off">
          {q.data.grafana.configured ? t("ops.grafana.down") : t("ops.grafana.off")}
        </p>
      ) : null}
      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {(q.data?.dashboards ?? []).map((d) => (
          <li key={d.uid}>
            <a href={d.url} className={cn("flex min-h-11 items-center rounded-xl border bg-card px-4 py-2 type-callout text-label-1", !up && "pointer-events-none opacity-60")} aria-disabled={!up || undefined} tabIndex={up ? undefined : -1} data-testid={`ops-dash-${d.uid}`}>
              {locale === "tr" ? d.title_tr : d.title_en}
            </a>
          </li>
        ))}
      </ul>
      {embeds.length ? (
        <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
          {embeds.map((p) => (
            <iframe key={p!.embed} src={`${p!.embed}&theme=light&kiosk`} title={locale === "tr" ? p!.title_tr : p!.title_en} className="h-56 w-full rounded-xl border bg-card" loading="lazy" referrerPolicy="same-origin" sandbox="allow-scripts allow-same-origin" />
          ))}
        </div>
      ) : null}
    </section>
  );
}

/* -------------------------------------------------------------------------------------------------- log tail */

const LIMITS = ["50", "100", "200"] as const;

function LogTail({ headingRef, preset }: { headingRef: React.RefObject<HTMLHeadingElement | null>; preset: { service: string; q: string } | null }) {
  const { t, locale } = useI18n();
  const [service, setService] = useState("backend");
  const [text, setText] = useState("");
  const [limit, setLimit] = useState<(typeof LIMITS)[number]>("100");
  const [args, setArgs] = useState<{ service: string; q: string; limit: number; minutes: number } | null>(null);
  useEffect(() => {
    if (!preset) return;
    setService(preset.service);
    setText(preset.q);
    setArgs({ service: preset.service, q: preset.q, limit: Number(limit), minutes: 1440 });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only a new preset (a "find in logs" click) refetches
  }, [preset]);
  const q = useOpsLogs(args);
  const fmt = (ms: number) => new Date(ms).toLocaleTimeString(intlLocale(locale), { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  return (
    <section aria-labelledby="ops-logs-h" data-testid="ops-logs">
      <h2 id="ops-logs-h" ref={headingRef} tabIndex={-1} className="mb-2 type-title-3 text-label-1 focus-visible:outline-2">
        {t("ops.logs.title")}
      </h2>
      <form
        className="flex flex-col gap-2 sm:flex-row sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          setArgs({ service, q: text.trim(), limit: Number(limit), minutes: 1440 });
        }}
      >
        <label className="flex flex-col gap-1 type-footnote text-label-2 sm:w-44">
          {t("ops.logs.service")}
          <NativeSelect value={service} onChange={(e) => setService(e.target.value)} data-testid="ops-logs-service">
            {LOG_SERVICES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </NativeSelect>
        </label>
        <label className="flex flex-1 flex-col gap-1 type-footnote text-label-2">
          {t("ops.logs.filter")}
          <Input value={text} onChange={(e) => setText(e.target.value)} placeholder={t("ops.logs.filterHint")} maxLength={200} data-testid="ops-logs-q" />
        </label>
        <label className="flex flex-col gap-1 type-footnote text-label-2 sm:w-28">
          {t("ops.logs.lines")}
          <NativeSelect value={limit} onChange={(e) => setLimit(e.target.value as (typeof LIMITS)[number])} data-testid="ops-logs-limit">
            {LIMITS.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </NativeSelect>
        </label>
        <Button type="submit" data-testid="ops-logs-fetch">
          {t("ops.logs.fetch")}
        </Button>
      </form>
      <div className="mt-2" aria-live="polite">
        {q.isFetching ? <Loading /> : null}
        {q.data && !q.data.available ? (
          <p className="rounded-xl bg-fill-3 p-3 type-callout text-label-2" data-testid="ops-logs-off">
            {(locale === "tr" ? q.data.message_tr : q.data.message_en) ?? t("ops.logs.off")}
          </p>
        ) : null}
        {q.data?.available && !q.data.lines.length ? <p className="type-callout text-label-2">{t("ops.logs.empty")}</p> : null}
        {q.data?.available && q.data.lines.length ? (
          <pre className="max-h-96 overflow-auto rounded-xl bg-fill-3 p-2 font-mono type-caption whitespace-pre-wrap break-words text-label-1" data-testid="ops-logs-lines">
            {q.data.lines.map((l) => `${fmt(l.ts)}  ${l.line}`).join("\n")}
          </pre>
        ) : null}
      </div>
    </section>
  );
}
