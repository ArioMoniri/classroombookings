"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { NativeSelect } from "@/components/common/native-select";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api/endpoints";
import { useRuns, useTerms } from "@/lib/api/hooks";
import type { CopyItem, CopyResult } from "@/lib/api/studio-schemas";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { formatDate } from "@/lib/time";
import { fallbackSentence, plainRuleText } from "./rule-helpers";
import { useStudio } from "./studio-context";

const BUCKETS: { key: "will_match" | "needs_review" | "cannot_match"; label: MessageKey }[] = [
  { key: "will_match", label: "studio.copy.willMatch" },
  { key: "needs_review", label: "studio.copy.needsReview" },
  { key: "cannot_match", label: "studio.copy.cannotMatch" },
];

/** (d) Copy rules from a previous run or term: dry run → grouped review → copy the selected ones. */
export function CopyDialog({ open, onOpenChange, initialRunId }: { open: boolean; onOpenChange: (v: boolean) => void; initialRunId?: number | null }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl" data-testid="copy-dialog">
        {open ? <CopyBody onClose={() => onOpenChange(false)} initialRunId={initialRunId} /> : null}
      </DialogContent>
    </Dialog>
  );
}

function CopyBody({ onClose, initialRunId }: { onClose: () => void; initialRunId?: number | null }) {
  const onOpenChange = (v: boolean) => !v && onClose();
  const { t, locale } = useI18n();
  const { termId, meta, sentence, store, refresh } = useStudio();
  const runs = useRuns({ term_id: termId });
  const terms = useTerms();
  const [source, setSource] = useState<string>(initialRunId ? `run:${initialRunId}` : "");
  const [loaded, setLoaded] = useState<{ key: string; data: CopyResult | null } | null>(null);
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);

  const options = useMemo(() => {
    const rs = (runs.data ?? []).filter((r) => r.status === "FEASIBLE" || r.status === "OPTIMAL" || r.status === "TIMEOUT").slice(0, 8);
    return [
      ...rs.map((r) => ({ value: `run:${r.id}`, label: t("studio.copy.fromRun", { id: r.id, term: r.term_code, date: formatDate(r.created_at, locale) }) })),
      ...(terms.data ?? []).filter((x) => x.id !== termId).map((x) => ({ value: `term:${x.id}`, label: t("studio.copy.fromTerm", { term: x.name }) })),
    ];
  }, [runs.data, terms.data, termId, t, locale]);

  const effective = source || options.find((o) => o.value.startsWith("term:"))?.value || options[0]?.value || "";
  const result = loaded?.key === effective ? loaded.data : null;
  const loading = busy || (effective !== "" && loaded?.key !== effective);

  useEffect(() => {
    if (!effective) return;
    let alive = true;
    const [type, id] = effective.split(":");
    api.studio
      .copy({ to_term_id: termId, from_run_id: type === "run" ? Number(id) : null, from_term_id: type === "term" ? Number(id) : null, dry_run: true })
      .then((r) => {
        if (!alive) return;
        setLoaded({ key: effective, data: r });
        setChecked(new Set([...r.will_match, ...r.needs_review].map((x) => x.source_id)));
      })
      .catch(() => alive && setLoaded({ key: effective, data: null }));
    return () => {
      alive = false;
    };
  }, [effective, termId]);

  const copy = async () => {
    const [type, id] = effective.split(":");
    setBusy(true);
    try {
      const r = await api.studio.copy({ to_term_id: termId, from_run_id: type === "run" ? Number(id) : null, from_term_id: type === "term" ? Number(id) : null, constraint_ids: [...checked], dry_run: false });
      await refresh(["rules", "classes", "summary"]);
      store.getState().record({
        label: t("studio.copy.copied", { n: r.created.length }),
        undo: async () => {
          await Promise.all(r.created.map((cid) => api.constraints.remove(cid)));
          await refresh(["rules", "classes", "summary"]);
        },
        redo: async () => {
          await api.studio.copy({ to_term_id: termId, from_run_id: type === "run" ? Number(id) : null, from_term_id: type === "term" ? Number(id) : null, constraint_ids: [...checked], dry_run: false });
          await refresh(["rules", "classes", "summary"]);
        },
      });
      toast.success(t("studio.copy.copied", { n: r.created.length }), { action: { label: t("common.undo"), onClick: () => void store.getState().undo() } });
      onOpenChange(false);
    } finally {
      setBusy(false);
    }
  };

  const text = (c: CopyItem) => (c.nl_text ? plainRuleText(meta, c.kind, c.params, c.nl_text, sentence) : fallbackSentence(meta, c.kind, null, locale));

  return (
    <>
        <DialogHeader>
          <DialogTitle>{t("studio.add.copy")}</DialogTitle>
          <DialogDescription>{t("studio.copy.help")}</DialogDescription>
        </DialogHeader>
        <label className="grid gap-1 text-sm">
          <span className="font-medium">{t("studio.copy.source")}</span>
          <NativeSelect value={effective} onChange={(e) => setSource(e.target.value)} data-testid="copy-source">
            {options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </NativeSelect>
        </label>
        {loading && !result ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
            <Loader2 className="size-4 animate-spin" aria-hidden /> {t("common.loading")}
          </p>
        ) : null}
        {result
          ? BUCKETS.map((b) => {
              const items = result[b.key];
              if (!items.length) return null;
              return (
                <section key={b.key} aria-label={t(b.label)} className="space-y-1.5">
                  <h4 className="text-sm font-semibold">
                    {t(b.label)} <span className="font-normal text-muted-foreground">({items.length})</span>
                  </h4>
                  <ul className="space-y-1.5">
                    {items.map((c) => (
                      <li key={c.source_id} className="flex items-start gap-2 rounded-md border p-2 text-sm">
                        <Checkbox
                          checked={checked.has(c.source_id)}
                          disabled={b.key === "cannot_match"}
                          onCheckedChange={(v) =>
                            setChecked((s) => {
                              const n = new Set(s);
                              if (v) n.add(c.source_id);
                              else n.delete(c.source_id);
                              return n;
                            })
                          }
                          aria-label={text(c)}
                        />
                        <div className="min-w-0 flex-1">
                          <p>{text(c)}</p>
                          <p className="text-xs text-muted-foreground">
                            {c.hardness === "hard" ? t("studio.rule.must") : t("studio.rule.try")} · {t("studio.rule.appliesTo", { n: c.affected_count })}
                          </p>
                          {c.reasons.length ? <p className="text-xs text-status-warning-fg">{c.reasons.join("; ")}</p> : null}
                        </div>
                      </li>
                    ))}
                  </ul>
                </section>
              );
            })
          : null}
        {result && !result.will_match.length && !result.needs_review.length && !result.cannot_match.length ? <p className="text-sm text-muted-foreground">{t("studio.copy.none")}</p> : null}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button onClick={() => void copy()} disabled={loading || checked.size === 0} data-testid="copy-confirm">
            {t("studio.copy.add", { n: checked.size })}
          </Button>
        </DialogFooter>
    </>
  );
}
