"use client";
/**
 * The plan's diagnoses: one group per code, errors first (every missing invigilator has a cause), each group with
 * its count, the posts it touches and a summary of the backend's suggestions; items are the backend's own words
 * and suggestions. Long groups page in steps of 10 ("Daha fazla göster"), nothing is dropped. A post named by an
 * item opens it in the duties view. A shortage whose posts were staffed by hand afterwards (`resolved: true`) is
 * kept, in a group of its own at the end, with a check mark and "Giderildi" (never silently dropped).
 */
import { AlertTriangle, CheckCircle2, ChevronDown, Info, Lightbulb, XOctagon } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import type { Diagnosis } from "@/lib/api/invigilation";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { diagCounts, groupDiagnoses, suggestionSummary } from "./invigilation-model";

const KNOWN = new Set(["no_candidates", "slot_shortage", "cap_shortage", "overlap_shortage", "locked_conflict", "lock_stale", "teaching_unchecked", "exams_without_room", "exams_without_date", "pool_empty"]);
const STEP = 10;

export function DiagnosisList({ items, onPost, postLabel }: { items: readonly Diagnosis[]; onPost: (postKey: string) => void; postLabel?: (postKey: string) => string }) {
  const { t, n } = useI18n();
  const groups = useMemo(() => groupDiagnoses(items), [items]);
  if (!groups.length)
    return (
      <p className="flex items-center gap-2 type-callout text-label-2" data-testid="invig-diagnosis" data-empty="true">
        <CheckCircle2 aria-hidden className="size-4 text-status-feasible-fg" />
        {t("invigilation.diag.none")}
      </p>
    );
  const c = diagCounts(items);
  return (
    <section aria-labelledby="invig-diag-title" className="flex flex-col gap-2" data-testid="invig-diagnosis">
      <h3 id="invig-diag-title" className="type-title-3">
        {t("invigilation.diag.title")} <span className="type-callout font-normal text-label-2 tnum">{t("invigilation.diag.counts", { errors: n(c.errors), others: n(c.others) })}
          {c.resolved ? ` · ${t("invigilation.diag.resolvedCount", { n: n(c.resolved) })}` : ""}</span>
      </h3>
      <ul className="flex flex-col gap-2">
        {groups.map((g, i) => (
          <Group key={`${g.resolved ? "resolved" : "open"}:${g.severity}:${g.code}`} code={g.code} severity={g.severity} resolved={g.resolved} items={g.items} posts={g.posts} defaultOpen={i === 0 && g.severity === "error" && !g.resolved} onPost={onPost} postLabel={postLabel} />
        ))}
      </ul>
    </section>
  );
}

function Group({ code, severity, resolved, items, posts, defaultOpen, onPost, postLabel }: { code: string; severity: Diagnosis["severity"]; resolved: boolean; items: Diagnosis[]; posts: number; defaultOpen: boolean; onPost: (k: string) => void; postLabel?: (k: string) => string }) {
  const { t, n, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const [open, setOpen] = useState(defaultOpen);
  const [shown, setShown] = useState(STEP);
  const Icon = resolved ? CheckCircle2 : severity === "error" ? XOctagon : severity === "warning" ? AlertTriangle : Info;
  const tone = resolved ? "bg-status-feasible text-status-feasible-fg" : severity === "error" ? "bg-status-infeasible text-status-infeasible-fg" : severity === "warning" ? "bg-status-warning text-status-warning-fg" : "bg-fill-2 text-label-1";
  const name = KNOWN.has(code) ? t(`invigilation.diag.code.${code}` as MessageKey) : code;
  const title = resolved ? t("invigilation.diag.resolvedGroup", { title: name }) : name;
  // a resolved shortage needs no advice any more
  const tips = resolved ? [] : suggestionSummary(items, lang);
  const panel = `invig-diag-${resolved ? "resolved" : "open"}-${severity}-${code}`;
  return (
    <li className="overflow-hidden rounded-xl bg-card edge-hairline" data-testid="invig-diag-group" data-code={code} data-severity={severity} data-resolved={resolved ? "true" : undefined}>
      <div className={cn("flex flex-wrap items-center gap-2 px-3 py-2", tone)}>
        <Icon aria-hidden className="size-4 shrink-0" />
        <span className="min-w-0 flex-1 type-headline">
          {title}
          <span className="ml-2 type-callout font-normal tnum">{t("invigilation.diag.groupCount", { n: n(items.length), posts: n(posts) })}</span>
        </span>
        <Button size="sm" variant="ghost" aria-expanded={open} aria-controls={panel} onClick={() => setOpen((o) => !o)} data-testid="invig-diag-toggle">
          <ChevronDown aria-hidden className={cn("transition-transform duration-(--dur-fast)", open && "rotate-180")} />
          {open ? t("invigilation.diag.hide") : t("invigilation.diag.show")}
        </Button>
      </div>
      {tips.length ? (
        <ul className="flex flex-col gap-1 px-3 pt-2 type-callout" aria-label={t("invigilation.diag.suggestions")}>
          {tips.map((s) => (
            <li key={s.text} className="flex items-start gap-2">
              <Lightbulb aria-hidden className="mt-0.5 size-3.5 shrink-0 text-label-2" />
              <span>
                {s.text}
                {items.length > 1 ? <span className="ml-1 type-footnote text-label-2 tnum">{t("invigilation.diag.tipTimes", { n: n(s.count) })}</span> : null}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {open ? (
        <div id={panel} className="flex flex-col gap-0 px-3 py-2">
          <ol className="flex flex-col">
            {items.slice(0, shown).map((d, i) => (
              <li key={i} className="flex flex-col gap-1 py-2 edge-hairline-b last:shadow-none" data-testid="invig-diag-item" data-resolved={d.resolved ? "true" : undefined}>
                <p className={cn("type-callout", d.resolved && "text-label-2")}>
                  {d.resolved ? (
                    <span className="mr-1.5 inline-flex items-center gap-1 align-baseline type-footnote font-semibold text-status-feasible-fg" data-testid="invig-diag-resolved">
                      <CheckCircle2 aria-hidden className="size-3.5 self-center" />
                      {t("invigilation.diag.resolved")}
                    </span>
                  ) : null}
                  {d.text?.[lang] || d.text?.tr || d.message || d.code}
                </p>
                {d.resolved ? <p className="type-footnote text-label-2">{t("invigilation.diag.resolvedHint")}</p> : d.suggestions?.length ? (
                  <ul className="flex flex-wrap gap-x-3 gap-y-0.5 type-footnote text-label-2">
                    {d.suggestions.map((s, j) => (
                      <li key={j} className="flex items-center gap-1"><Lightbulb aria-hidden className="size-3" />{s.text?.[lang] || s.text?.tr || s.code}</li>
                    ))}
                  </ul>
                ) : null}
                {d.post_keys?.length ? (
                  <div className="flex flex-wrap gap-1.5">
                    {d.post_keys.slice(0, 4).map((k) => (
                      <Button key={k} size="xs" variant="outline" onClick={() => onPost(k)} data-testid="invig-diag-post">
                        {t("invigilation.diag.openPost", { key: postLabel?.(k) ?? k.replace(/\|/g, " · ") })}
                      </Button>
                    ))}
                    {d.post_keys.length > 4 ? <span className="type-footnote text-label-2">{t("invigilation.diag.morePosts", { n: n(d.post_keys.length - 4) })}</span> : null}
                  </div>
                ) : null}
              </li>
            ))}
          </ol>
          {items.length > shown ? (
            <Button size="sm" variant="ghost" className="self-start" onClick={() => setShown((s) => s + STEP * 5)} data-testid="invig-diag-more">
              {t("invigilation.diag.more", { n: n(items.length - shown) })}
            </Button>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
