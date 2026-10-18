"use client";
/**
 * AS-17 run provenance (`GET /runs/{id}` → `stats.profile`, `stats.weights_effective`, `stats.weights_source`): one
 * line under the verdict, "Profil: Final haftası v2 · ağırlıklar", where "ağırlıklar" opens the weights that did not
 * come from the code defaults and where each came from. Runs from before AS-01 carry none of it: nothing is shown.
 */
import { useWeightLabel } from "@/components/seasons/weight-label";
import { Badge } from "@/components/ui/badge";
import type { ScheduleRun } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";

export interface RunProfileInfo {
  profile: { key: string; version: number; name: { tr: string; en: string } } | null;
  /** weights whose source is not the code default, with the source */
  changed: { key: string; value: number; source: "settings" | "profile" | "run" }[];
  skipped: number[];
  /** AS-08: the peak-smoothing weight the run used (shown only when > 0) */
  peakSmoothing: number;
}

const rec = (v: unknown): Record<string, unknown> | null => (v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null);

/** the provenance of a run, or null for a run the bridge built before AS-01 (no `weights_effective`) */
export function runProfileInfo(stats: Record<string, unknown> | undefined): RunProfileInfo | null {
  if (!stats) return null;
  const eff = rec(stats.weights_effective);
  if (!eff && !("profile" in stats)) return null;
  const src = rec(stats.weights_source) ?? {};
  const p = rec(stats.profile);
  const name = rec(p?.name);
  const changed: RunProfileInfo["changed"] = [];
  for (const [key, raw] of Object.entries(eff ?? {})) {
    const s = String(src[key] ?? "default");
    if (s === "default" || typeof raw !== "number") continue;
    changed.push({ key, value: raw, source: s.startsWith("profile:") ? "profile" : s === "run" ? "run" : "settings" });
  }
  const skipped = Array.isArray(stats.horizon_skipped_weeks) ? stats.horizon_skipped_weeks.filter((w): w is number => typeof w === "number") : [];
  return {
    profile: p ? { key: String(p.key ?? ""), version: Number(p.version ?? 1), name: { tr: String(name?.tr ?? p.key ?? ""), en: String(name?.en ?? name?.tr ?? p.key ?? "") } } : null,
    changed: changed.sort((a, b) => a.key.localeCompare(b.key)),
    skipped,
    peakSmoothing: typeof eff?.peak_smoothing === "number" ? eff.peak_smoothing : 0,
  };
}

export function RunProfileLine({ r }: { r: Pick<ScheduleRun, "stats_detail"> }) {
  const { t, locale } = useI18n();
  const wl = useWeightLabel();
  const info = runProfileInfo(r.stats_detail);
  if (!info) return null;
  const lang = locale === "tr" ? "tr" : "en";
  const head = info.profile ? t("adaptive.run.profile", { name: info.profile.name[lang], v: info.profile.version }) : t("adaptive.run.noProfile");
  return (
    <div className="type-footnote text-label-2" data-testid="run-profile" data-profile={info.profile?.key ?? "none"}>
      {info.changed.length ? (
        <details>
          <summary className="flex min-h-11 cursor-pointer flex-wrap items-center gap-x-1 pointer-fine:min-h-0">
            <span>{head}</span>
            <span aria-hidden>·</span>
            <span className="text-tint-text">{t("adaptive.run.weights", { n: info.changed.length })}</span>
          </summary>
          <ul className="mt-1 flex flex-col gap-0.5 pl-3" data-testid="run-weights">
            {info.changed.map((w) => (
              <li key={w.key}>
                {wl(w.key)}: <span className="font-semibold tabular-nums text-label-1">{w.value}</span> · {t(`adaptive.run.source.${w.source}`)}
              </li>
            ))}
          </ul>
        </details>
      ) : (
        <p>
          {head} · {t("adaptive.run.defaults")}
        </p>
      )}
      {info.peakSmoothing > 0 ? <p data-testid="run-peak-smoothing">{t("adaptive.run.peakSmoothing", { n: info.peakSmoothing })}</p> : null}
      {info.skipped.length ? <p>{t("adaptive.run.skipped", { weeks: info.skipped.join(", ") })}</p> : null}
    </div>
  );
}

/** AS20-F07: a what-if draft run (`params.scenario`) names itself under the run title, so it is never taken for a plan */
export function RunScenarioLine({ r }: { r: Pick<ScheduleRun, "label" | "params"> }) {
  const { t } = useI18n();
  if (!r.params?.scenario) return null;
  return (
    <p className="mt-1 flex flex-wrap items-center gap-2 type-footnote text-label-2" data-testid="run-scenario">
      <Badge tone="tint">{t("adaptive.run.scenario")}</Badge>
      {r.label ? <span className="text-label-1">{r.label}</span> : null}
    </p>
  );
}
