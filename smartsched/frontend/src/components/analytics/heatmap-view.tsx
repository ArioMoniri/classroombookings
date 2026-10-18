"use client";
/**
 * Doluluk ısı haritası (`/analytics/heatmap`): room utilisation (group by building / room type / capacity band /
 * room; one week or the whole term; the live board = published runs + blocks + bookings, or one run) and the
 * instructor load (who teaches when, periods, idle gaps). Backend: `GET /analytics/heatmap/rooms` and
 * `/analytics/heatmap/instructors` (services/utilisation.py). State lives in the URL, so a view can be shared.
 */
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { PageHeader } from "@/components/common/page-header";
import { useRunText } from "@/components/compare/run-text";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { Checkbox } from "@/components/ui/checkbox";
import { NativeSelect } from "@/components/ui/native-select";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { GROUP_BY, useRunOptions, type GroupBy } from "@/lib/api/analytics";
import { useI18n } from "@/lib/i18n/provider";
import { FadePanel } from "./fade-panel";
import { NoTerms } from "./forecast-bits";
import { readHeatUrl, type HeatTab, type HeatUrlState } from "./heat-model";
import { InstructorsHeat } from "./instructors-heat";
import { PeaksView } from "./peaks-view";
import { RoomsHeat } from "./rooms-heat";

export function HeatmapView() {
  const { t } = useI18n();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const s = readHeatUrl(params);
  const { term, terms, isLoading: termsLoading } = useActiveTerm();
  const runs = useRunOptions(term?.id ?? null);
  const runText = useRunText();
  const runChoices = useMemo(() => (runs.data ?? []).filter((r) => (s.tab === "instructors" ? r.kind === "COURSE" : true)), [runs.data, s.tab]);

  const set = (patch: Partial<Record<keyof HeatUrlState, string | null>>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v === null) next.delete(k);
      else next.set(k, v);
    }
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };
  const termId = term?.id;
  const runId = s.source === "run" && s.run !== null && runChoices.some((r) => r.id === s.run) ? s.run : null;
  const source = runId !== null ? ({ run_id: runId } as const) : termId !== undefined ? ({ term_id: termId } as const) : null;
  const weekCount = term?.week_count ?? 0;

  // E2EB-F03: an install with no term yet gets one next step, not a control panel over "Önce bir dönem seçin."
  if (!termsLoading && terms.length === 0)
    return (
      <div className="flex min-w-0 flex-col gap-4" data-testid="heatmap-page">
        <PageHeader title={t("analytics.title")} subtitle={t("analytics.subtitle")} />
        <NoTerms />
      </div>
    );

  return (
    <div className="flex min-w-0 flex-col gap-4" data-testid="heatmap-page">
      <PageHeader title={t("analytics.title")} subtitle={term ? `${term.name} · ${t("analytics.subtitle")}` : t("analytics.subtitle")} />
      <SegmentedControl<HeatTab>
        aria-label={t("analytics.tabs")}
        options={[
          { value: "rooms", label: t("analytics.tab.rooms"), controls: "heat-panel-rooms", testId: "heat-tab-rooms" },
          { value: "instructors", label: t("analytics.tab.instructors"), controls: "heat-panel-instructors", testId: "heat-tab-instructors" },
          { value: "peaks", label: t("adaptive.peaks.tab"), controls: "heat-panel-peaks", testId: "heat-tab-peaks" },
        ]}
        value={s.tab}
        onValueChange={(v) => set({ tab: v === "rooms" ? null : v, g: null })}
        className="self-start"
      />
      {s.tab === "peaks" ? (
        // AS-16 Yoğun saatler: its own controls (group, period kind, term), no source / week / bookings switches
        <div id="heat-panel-peaks" role="tabpanel" aria-label={t("adaptive.peaks.tab")} className="flex min-w-0 flex-col gap-4">
          <PeaksView />
        </div>
      ) : (
      <>
      <section aria-label={t("analytics.controls")} className="flex flex-wrap items-end gap-x-4 gap-y-3 rounded-xl bg-card p-3 edge-hairline" data-testid="heat-controls">
        <div className="flex min-w-0 max-w-full flex-col gap-1 max-sm:w-full">
          <span className="type-footnote font-medium text-label-2" id="heat-source-label">{t("analytics.sourceLabel")}</span>
          {/* 200 % text (mobile-b phase 2): the segment scrolls in its own row instead of the page */}
          <div className="max-w-full overflow-x-auto [scrollbar-width:none]">
          <SegmentedControl
            size="sm"
            semantics="radiogroup"
            aria-labelledby="heat-source-label"
            options={[
              { value: "live", label: t("analytics.source.live"), testId: "heat-source-live" },
              { value: "run", label: t("analytics.source.run"), testId: "heat-source-run", disabled: runChoices.length === 0 },
            ]}
            value={runId !== null || s.source === "run" ? "run" : "live"}
            onValueChange={(v) => set({ source: v === "live" ? null : "run", run: v === "run" ? String(s.run ?? runChoices[0]?.id ?? "") || null : null, g: null })}
          />
          </div>
        </div>
        {s.source === "run" ? (
          <label className="flex min-w-0 flex-col gap-1 max-sm:w-full">
            <span className="type-footnote font-medium text-label-2">{t("analytics.run")}</span>
            <NativeSelect size="sm" className="w-72 max-w-full" value={runId ?? ""} onChange={(e) => set({ run: e.target.value || null, g: null })} data-testid="heat-run">
              {runId === null ? <option value="">{t("analytics.chooseRun")}</option> : null}
              {runChoices.map((r) => (
                <option key={r.id} value={r.id}>{runText(r)}</option>
              ))}
            </NativeSelect>
          </label>
        ) : null}
        {s.tab === "rooms" ? (
          <label className="flex min-w-0 flex-col gap-1 max-sm:w-full">
            <span className="type-footnote font-medium text-label-2">{t("analytics.groupBy")}</span>
            <NativeSelect size="sm" className="w-44 max-sm:w-full" value={s.group} onChange={(e) => set({ group: e.target.value === "building" ? null : e.target.value, g: null })} data-testid="heat-group">
              {GROUP_BY.map((g: GroupBy) => (
                <option key={g} value={g}>{t(`analytics.group.${g}`)}</option>
              ))}
            </NativeSelect>
          </label>
        ) : null}
        <div className="flex min-w-0 max-w-full flex-col gap-1 max-sm:w-full">
          <span className="type-footnote font-medium text-label-2" id="heat-scope-label">{t("analytics.scopeLabel")}</span>
          {/* 200 % text (mobile-b phase 2): the segment scrolls in its own row instead of the page */}
          <div className="max-w-full overflow-x-auto [scrollbar-width:none]">
          <SegmentedControl
            size="sm"
            semantics="radiogroup"
            aria-labelledby="heat-scope-label"
            options={[
              { value: "week", label: t("analytics.scope.week"), testId: "heat-scope-week" },
              { value: "term", label: t("analytics.scope.term"), testId: "heat-scope-term" },
            ]}
            value={s.scope}
            onValueChange={(v) => set({ scope: v === "week" ? null : v, week: null })}
          />
          </div>
        </div>
        {s.scope === "week" && weekCount > 0 ? (
          <label className="flex min-w-0 flex-col gap-1 max-sm:w-full">
            <span className="type-footnote font-medium text-label-2">{t("analytics.week")}</span>
            <NativeSelect size="sm" className="w-36 max-sm:w-full" value={s.week ?? ""} onChange={(e) => set({ week: e.target.value || null })} data-testid="heat-week">
              <option value="">{t("analytics.weekAuto")}</option>
              {Array.from({ length: weekCount }, (_, i) => i + 1).map((w) => (
                <option key={w} value={w}>{t("analytics.weekN", { n: w })}</option>
              ))}
            </NativeSelect>
          </label>
        ) : null}
        {s.tab === "rooms" ? (
          <fieldset className="flex flex-col gap-1.5">
            <legend className="mb-1 type-footnote font-medium text-label-2">{t("analytics.include")}</legend>
            <div className="flex flex-wrap gap-3">
              <label className="flex items-center gap-2 type-callout">
                <Checkbox checked={s.blocks} onCheckedChange={(v) => set({ blocks: v ? null : "0" })} data-testid="heat-blocks" />
                {t("analytics.blocks")}
              </label>
              {runId === null ? (
                <label className="flex items-center gap-2 type-callout">
                  <Checkbox checked={s.bookings} onCheckedChange={(v) => set({ bookings: v ? null : "0" })} data-testid="heat-bookings" />
                  {t("analytics.bookings")}
                </label>
              ) : null}
            </div>
          </fieldset>
        ) : null}
      </section>
      {!term ? (
        <p className="type-callout text-label-2">{t("analytics.noTerm")}</p>
      ) : source === null && s.source === "run" ? (
        <div className="rounded-xl bg-fill-3 px-4 py-5"><p className="type-callout">{t("analytics.chooseRunHint")}</p></div>
      ) : (
        <FadePanel panelKey={s.tab} className="flex min-w-0 flex-col gap-4">
          <div id={`heat-panel-${s.tab}`} role="tabpanel" aria-label={t(`analytics.tab.${s.tab}`)} className="flex min-w-0 flex-col gap-4">
            {s.tab === "rooms" ? (
              <RoomsHeat
                query={{ ...(source ?? {}), group_by: s.group, scope: s.scope, week: s.scope === "week" ? (s.week ?? undefined) : undefined, bookings: s.bookings, blocks: s.blocks, rooms: false }}
                group={s.g}
                onGroup={(g) => set({ g: g || null })}
              />
            ) : (
              <InstructorsHeat query={{ ...(source ?? {}), scope: s.scope, week: s.scope === "week" ? (s.week ?? undefined) : undefined }} />
            )}
          </div>
        </FadePanel>
      )}
      </>
      )}
    </div>
  );
}
