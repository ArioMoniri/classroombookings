"use client";

import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api/endpoints";
import { qk } from "@/lib/api/hooks";
import { useRunDataIssues } from "@/lib/api/shell-extra";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { readNotes, unparsedFromIssues } from "./notes-reading";

/** The importer's reasons (English, `preference_rules._unparsed`) → planner text. */
const REASONS: Record<string, MessageKey> = {
  "no rule could be read from this wish": "classes.insp.notesReason.noRule",
  "no room feature for this wish": "classes.insp.notesReason.noFeature",
  "rooms not in the room list": "classes.insp.notesReason.unknownRoom",
};

/**
 * "Derse özel açıklama": the request's own words, what became a rule, and what was not read (A-04).
 * The coordinator sees "JASP on the lectern PC" even when no rule could carry it.
 */
export function NotesSection({ requestId, notes, termId, runId }: { requestId: number; notes: string | null | undefined; termId: number | null; runId: number | null }) {
  const { t } = useI18n();
  const has = Boolean(notes?.trim());
  const q = termId !== null ? { term_id: termId } : undefined;
  const rules = useQuery({ queryKey: qk.constraints(q), queryFn: () => api.constraints.list(q), enabled: has && termId !== null, staleTime: 30_000 });
  const issues = useRunDataIssues(runId, has);
  const reading = readNotes(requestId, notes, rules.data ?? [], issues.isSuccess ? unparsedFromIssues(issues.data.groups, requestId) : null);
  if (!reading) return null;
  // disabled queries stay pending in TanStack v5: only wait for the ones that run
  const settled = (termId === null || !rules.isPending) && (runId === null || !issues.isPending);
  return (
    <section aria-labelledby={`notes-${requestId}`} className="flex flex-col gap-1.5 py-3 hairline-t" data-testid="inspector-notes">
      <h3 id={`notes-${requestId}`} className="type-caption font-semibold text-label-3">{t("classes.insp.notes")}</h3>
      <blockquote className="rounded-lg bg-fill-3 px-2.5 py-1.5 type-footnote leading-[18px] whitespace-pre-line text-label-1" lang="tr">
        {reading.notes}
      </blockquote>
      {!settled ? null : reading.unread ? (
        <p className="flex flex-wrap items-center gap-1.5 type-footnote text-label-2">
          <Badge variant="outline" tone="warning" data-testid="notes-unread">{t("classes.insp.notesUnread")}</Badge>
          {t("classes.insp.notesNoRule")}
        </p>
      ) : (
        <ul className="flex flex-col gap-1 type-footnote" aria-label={t("classes.insp.notesRead")}>
          {reading.rules.map((r) => (
            <li key={r.id} className="flex flex-wrap items-baseline gap-1.5" data-testid="notes-rule">
              <span aria-hidden className="text-status-feasible-fg">✓</span>
              <span className="text-label-1">“{r.text}”</span>
              <span className="text-label-2">→ {r.state === "on" ? t("classes.insp.notesRuleOn") : t("classes.insp.notesRulePending")}</span>
            </li>
          ))}
          {reading.unparsed.map((u, i) => (
            <li key={`u-${i}`} className="flex flex-wrap items-baseline gap-1.5" data-testid="notes-unparsed">
              <Badge variant="outline" tone="warning">{t("classes.insp.notesUnread")}</Badge>
              <span className="text-label-1">“{u.text}”</span>
              {u.reason ? <span className="text-label-2">· {REASONS[u.reason] ? t(REASONS[u.reason]) : u.reason}</span> : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
