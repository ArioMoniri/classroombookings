"use client";

import { Loader2, PlayCircle, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { NativeSelect } from "@/components/common/native-select";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api/endpoints";
import { useCreateRun, useMeetings, useRuns, useSettings, useWeeks } from "@/lib/api/hooks";
import type { Horizon, ProposedConstraint, RunKind } from "@/lib/api/schemas";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { formatDate } from "@/lib/time";
import { cn } from "@/lib/utils";

const WEIGHT_KINDS = ["room_preference", "building_preference", "min_capacity_waste", "same_room_across_weeks", "stability", "exam_gap"] as const;
const CHIPS: { key: MessageKey; tr: string; en: string }[] = [
  { key: "generate.chip.tip", tr: "TIP derslikleri sadece Tıp için", en: "TIP rooms only for medicine" },
  { key: "generate.chip.evening", tr: "İkinci öğretim B/C bloklarda kalsın", en: "Keep evening programmes in B/C blocks" },
  { key: "generate.chip.sameRoom", tr: "Her hafta aynı derslik", en: "Same room every week" },
  { key: "generate.chip.fit", tr: "Küçük sınıfları amfiye koyma", en: "Avoid tiny classes in amphitheatres" },
  { key: "generate.chip.pharmacy", tr: "Eczacılık Pazartesi C blokta kalsın", en: "Keep pharmacy in C block on Mondays" },
  { key: "generate.chip.nursing", tr: "1. sınıf hemşirelik 17:30'dan sonra ders almasın", en: "No first-year nursing lectures after 17:30" },
];

type Proposed = ProposedConstraint & { accepted: boolean };

export function GenerateView() {
  const { t, locale } = useI18n();
  const router = useRouter();
  const { term, terms } = useActiveTerm();
  const [termId, setTermId] = useState<number | null>(null);
  const effectiveTermId = termId ?? term?.id ?? 1;
  const weeks = useWeeks(effectiveTermId);
  const settings = useSettings();
  const runs = useRuns({ term_id: effectiveTermId });
  const meetings = useMeetings({ page_size: 1 });
  const create = useCreateRun();
  const [kind, setKind] = useState<RunKind>("COURSE");
  const [horizon, setHorizon] = useState<Horizon>("WEEK");
  const [selectedWeeks, setSelectedWeeks] = useState<number[]>([7]);
  const [prompt, setPrompt] = useState("");
  const [weightsState, setWeights] = useState<Record<string, number> | null>(null);
  const [timeLimitState, setTimeLimit] = useState<number | null>(null);
  const [seedState, setSeed] = useState<number | null>(null);
  const weights = weightsState ?? settings.data?.default_weights ?? {};
  const timeLimit = timeLimitState ?? settings.data?.solver_default_time_limit ?? 120;
  const seed = seedState ?? settings.data?.solver_default_seed ?? 0;
  const [stability, setStability] = useState(true);
  const [proposed, setProposed] = useState<Proposed[]>([]);
  const [analysing, setAnalysing] = useState(false);
  // stability parent: the newest good run of the same kind (an EXAM board must not seed a COURSE run)
  const previousRun = runs.data?.find((r) => r.kind === kind && (r.status === "FEASIBLE" || r.status === "OPTIMAL"));

  const lectureWeeks = useMemo(() => (weeks.data ?? []).filter((w) => w.kind !== "HOLIDAY"), [weeks.data]);
  const examWeeks = useMemo(() => (weeks.data ?? []).filter((w) => w.kind === "EXAM"), [weeks.data]);

  const toggleWeek = (i: number) => setSelectedWeeks((s) => (s.includes(i) ? s.filter((x) => x !== i) : [...s, i].sort((a, b) => a - b)));
  const horizonWeeks: number[] = horizon === "TERM" ? lectureWeeks.filter((w) => w.kind === "LECTURE").map((w) => w.index) : horizon === "MONTH" ? selectedWeeks.length ? Array.from({ length: 4 }, (_, k) => selectedWeeks[0] + k).filter((x) => lectureWeeks.some((w) => w.index === x)) : [] : selectedWeeks;

  const insertChip = (c: (typeof CHIPS)[number]) => setPrompt((p) => `${p}${p && !p.trim().endsWith(";") ? "; " : ""}${locale === "tr" ? c.tr : c.en}`);

  const analyse = async () => {
    if (!prompt.trim()) return;
    setAnalysing(true);
    try {
      // POST /terms/{id}/elicit: typed rules with names resolved to ids server-side (never by the model)
      const res = await api.ai.elicit(effectiveTermId, prompt, locale === "en" ? "en" : "tr");
      setProposed(res.proposals.filter((c) => c.status !== "rejected").map((c) => ({ ...c, accepted: false })));
      if (res.assistant_message) toast(res.assistant_message);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e)); // 409: no Anthropic key configured
    } finally {
      setAnalysing(false);
    }
  };

  const submit = async () => {
    if (horizonWeeks.length === 0) {
      toast.error(t("generate.week"));
      return;
    }
    const accepted: ProposedConstraint[] = proposed.filter((p) => p.accepted).map((p) => {
      const c: Partial<Proposed> = { ...p };
      delete c.accepted;
      return c as ProposedConstraint;
    });
    if (accepted.length > 0) {
      // reviewed rules become term constraints (source AI) before the solver sees them
      const res = await api.ai.accept(effectiveTermId, accepted);
      if (res.rejected.length) toast.warning(`${res.rejected.length} ✕`, { description: res.rejected.map((r) => String(r.reason ?? r.error ?? "")).filter(Boolean).join("; ") });
      setProposed((p) => p.filter((x) => !x.accepted));
    }
    const { run_id } = await create.mutateAsync({
      term_id: effectiveTermId,
      kind,
      horizon,
      horizon_params: { weeks: horizonWeeks },
      params: { time_limit_s: timeLimit, seed, stability, weights },
      prompt: prompt.trim() || undefined,
      parent_run_id: stability && previousRun ? previousRun.id : null,
    });
    toast.success(`Run #${run_id} ${t("generate.queued").toLocaleLowerCase(locale)}`);
    router.push(`/runs/${run_id}`);
  };

  return (
    <div className="mx-auto max-w-[880px]" data-testid="generate">
      <PageHeader title={t("generate.title")} subtitle={t("generate.subtitle")} />
      <div className="space-y-4">
        <Card>
          <CardHeader><CardTitle>1 · {t("generate.horizon")}</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="grid gap-1.5">
                <Label htmlFor="gen-term">{t("generate.term")}</Label>
                <NativeSelect id="gen-term" value={String(effectiveTermId)} onChange={(e) => { setTermId(Number(e.target.value)); setSelectedWeeks([1]); }}>
                  {terms.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
                </NativeSelect>
              </div>
              <div className="grid gap-1.5">
                <Label>{t("generate.kind")}</Label>
                <div role="radiogroup" className="inline-flex h-8 rounded-lg border p-0.5">
                  {(["COURSE", "EXAM"] as const).map((k) => (
                    <button key={k} type="button" role="radio" aria-checked={kind === k} onClick={() => { setKind(k); setHorizon(k === "EXAM" ? "WEEK" : horizon); setSelectedWeeks(k === "EXAM" ? examWeeks.slice(0, 1).map((w) => w.index) : [7]); }} className={cn("flex-1 rounded-md px-3 text-sm", kind === k ? "bg-primary text-primary-foreground" : "text-muted-foreground")}>
                      {t(k === "COURSE" ? "generate.course" : "generate.exam")}
                    </button>
                  ))}
                </div>
              </div>
              <div className="grid gap-1.5">
                <Label>{t("generate.horizon")}</Label>
                <div role="radiogroup" className="inline-flex h-8 rounded-lg border p-0.5">
                  {(["WEEK", "MONTH", "TERM"] as const).map((h) => (
                    <button key={h} type="button" role="radio" aria-checked={horizon === h} onClick={() => setHorizon(h)} data-testid={`horizon-${h}`} className={cn("flex-1 rounded-md px-3 text-sm", horizon === h ? "bg-primary text-primary-foreground" : "text-muted-foreground")}>
                      {t(h === "WEEK" ? "generate.week" : h === "MONTH" ? "generate.month" : "generate.wholeTerm")}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            {horizon !== "TERM" ? (
              <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("generate.week")}>
                {(kind === "EXAM" ? examWeeks : lectureWeeks).map((w) => {
                  const on = horizon === "MONTH" ? horizonWeeks.includes(w.index) : selectedWeeks.includes(w.index);
                  return (
                    <button key={w.id} type="button" aria-pressed={on} aria-label={`W${w.index} ${formatDate(w.start_date, locale)}`} onClick={() => (horizon === "MONTH" ? setSelectedWeeks([w.index]) : toggleWeek(w.index))} className={cn("flex flex-col items-center rounded-md border px-2 py-1 text-xs", on ? "border-primary bg-primary-tint text-primary" : "hover:bg-accent")}>
                      <span className="font-mono font-semibold">W{w.index}</span>
                      <span className="text-[10px] text-muted-foreground">{formatDate(w.start_date, locale)}</span>
                      {w.kind !== "LECTURE" ? <Badge variant="outline" className="mt-0.5 text-[9px]">{w.kind}</Badge> : null}
                    </button>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">{t("generate.weeksRange", { from: 1, to: horizonWeeks.length })} · {lectureWeeks.length} {t("requests.weeks").toLocaleLowerCase(locale)}</p>
            )}
            <div className="flex flex-wrap items-center gap-3 rounded-md bg-muted/60 px-3 py-2 text-xs text-muted-foreground">
              <span>{meetings.data ? `${meetings.data.total} ${t("requests.meetings").toLocaleLowerCase(locale)}` : "…"}</span>
              <span>· 61 {t("common.rooms").toLocaleLowerCase(locale)}</span>
              <span>· {horizonWeeks.length} {t("requests.weeks").toLocaleLowerCase(locale)}</span>
              {previousRun ? (
                <label className="ml-auto flex items-center gap-2"><span>{t("generate.previousRun")} #{previousRun.id}</span><Switch checked={stability} onCheckedChange={setStability} /></label>
              ) : null}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>2 · {t("generate.prompt")}</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <Textarea rows={4} placeholder={t("generate.promptPlaceholder")} value={prompt} onChange={(e) => setPrompt(e.target.value)} onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") void analyse(); }} aria-describedby="prompt-hint" data-testid="prompt" />
            <p id="prompt-hint" className="text-xs text-muted-foreground">{t("generate.chips")}:</p>
            <div className="flex flex-wrap gap-1.5">
              {CHIPS.map((c) => <button key={c.key} type="button" onClick={() => insertChip(c)} aria-label={`${t("generate.chips")}: ${t(c.key)}`} className="rounded-full border px-2.5 py-1 text-xs hover:bg-accent">{t(c.key)}</button>)}
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => void analyse()} disabled={!prompt.trim() || analysing} data-testid="analyse">
                {analysing ? <Loader2 className="animate-spin" /> : <Sparkles />} {t("generate.proposed")}
              </Button>
              {settings.data && !settings.data.anthropic_api_key_masked ? <span className="text-xs text-status-warning-fg">{t("chat.noKey")}</span> : null}
            </div>
            {proposed.length > 0 ? (
              <ul className="space-y-2" data-testid="proposed-constraints">
                {proposed.map((c, i) => (
                  <li key={i} className={cn("flex flex-wrap items-center gap-2 rounded-md border p-2 text-sm", c.accepted && "border-status-feasible-border bg-status-feasible/30")}>
                    <Badge variant={c.hardness === "hard" ? "default" : "secondary"}>{c.hardness}</Badge>
                    <span className="font-mono text-xs">{c.kind}</span>
                    <span className="flex-1 text-muted-foreground">“{c.nl_text}”{c.title ? <span className="block text-xs text-foreground">{c.title}</span> : null}{c.issues.length ? <span className="block text-xs text-status-warning-fg">{c.issues.join("; ")}</span> : null}</span>
                    {!c.accepted ? (
                      <>
                        <Button size="xs" onClick={() => setProposed((p) => p.map((x, j) => (j === i ? { ...x, accepted: true } : x)))}>{t("generate.accept")}</Button>
                        <Button size="xs" variant="ghost" onClick={() => setProposed((p) => p.filter((_, j) => j !== i))}>{t("generate.reject")}</Button>
                      </>
                    ) : <Badge variant="outline">✓</Badge>}
                  </li>
                ))}
              </ul>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>3 · {t("generate.weights")}</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
              {WEIGHT_KINDS.map((k) => (
                <div key={k} className="grid gap-1">
                  <div className="flex items-center justify-between text-sm"><Label htmlFor={`w-${k}`}>{t(`generate.weight.${k}`)}</Label><span className="font-mono text-xs tabular-nums">{weights[k] ?? 0}</span></div>
                  <Slider id={`w-${k}`} min={0} max={10} step={1} value={[weights[k] ?? 0]} onValueChange={(v) => setWeights({ ...weights, [k]: Array.isArray(v) ? v[0] : v })} aria-label={t(`generate.weight.${k}`)} />
                </div>
              ))}
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="grid gap-1"><Label htmlFor="tl">{t("generate.timeLimit")} ({t("generate.seconds")})</Label><Input id="tl" type="number" min={10} max={900} value={timeLimit} onChange={(e) => setTimeLimit(Number(e.target.value))} /></div>
              <div className="grid gap-1"><Label htmlFor="seed">{t("generate.seed")}</Label><Input id="seed" type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} /></div>
              <div className="grid gap-1"><Label>{t("generate.stability")}</Label><Switch checked={stability} onCheckedChange={setStability} aria-label={t("generate.stability")} /></div>
            </div>
          </CardContent>
        </Card>

        <div className="sticky bottom-0 -mx-4 flex items-center justify-between gap-3 border-t bg-background/90 px-4 py-3 backdrop-blur-sm sm:-mx-6 sm:px-6 lg:static lg:mx-0 lg:rounded-xl lg:border lg:px-4">
          <span className="text-xs text-muted-foreground">{t("generate.timeLimit")}: {timeLimit}s · {horizonWeeks.length} {t("requests.weeks").toLocaleLowerCase(locale)}</span>
          <Button size="lg" onClick={() => void submit()} disabled={create.isPending || horizonWeeks.length === 0} data-testid="generate-submit">
            {create.isPending ? <Loader2 className="animate-spin" /> : <PlayCircle />} {create.isPending ? t("generate.submitting") : t("generate.submit")}
          </Button>
        </div>
      </div>
    </div>
  );
}
