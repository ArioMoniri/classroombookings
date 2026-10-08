"use client";
/** The installer requirements as a checklist (setup wizard step 1, and /admin for setup.settings). */
import { AlertTriangle, CheckCircle2, RefreshCw, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { crbsError, type RequirementStatus } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import type { useSetupRequirements } from "@/lib/api/crbs";
import { Alert, Loading } from "./kit";
import { requirementRows, summariseRequirements } from "./requirements-model";

const ICON: Record<RequirementStatus, { icon: typeof CheckCircle2; cls: string }> = {
  ok: { icon: CheckCircle2, cls: "text-status-feasible-fg" },
  warn: { icon: AlertTriangle, cls: "text-status-warning-fg" },
  err: { icon: XCircle, cls: "text-status-infeasible-fg" },
};

export function RequirementsList({ query, highlight = [], compact }: { query: ReturnType<typeof useSetupRequirements>; highlight?: readonly string[]; compact?: boolean }) {
  const { t, n } = useI18n();
  const rows = requirementRows(query.data);
  const sum = summariseRequirements(query.data);
  const label = (key: string) => {
    const r = rows.find((x) => x.key === key);
    return r?.labelKey ? t(r.labelKey) : key;
  };
  if (query.isLoading) return <Loading />;
  if (query.isError) return <Alert tone="error">{t("crbs.setup.req.unavailable", { message: bookingErrorMessage(crbsError(query.error), t) })}</Alert>;
  return (
    <div className="flex flex-col gap-3" data-testid="setup-requirements">
      {sum.blocking.length ? (
        <Alert tone="error" testId="requirements-blocked">
          {t("crbs.setup.req.blocked", { list: sum.blocking.map((r) => label(r.key)).join(", ") })}
        </Alert>
      ) : (
        <Alert tone={sum.warnings.length ? "warning" : "success"}>
          {sum.warnings.length ? t("crbs.setup.req.warnings", { n: n(sum.warnings.length) }) : t("crbs.setup.req.allOk")}
        </Alert>
      )}
      <Card variant={compact ? "plain" : "glass"} className="py-0">
        <ul aria-label={t("crbs.setup.req.title")}>
          {rows.map((r) => {
            const { icon: Icon, cls } = ICON[r.status];
            return (
              <li
                key={r.key}
                data-requirement={r.key}
                data-status={r.status}
                className={cn("flex items-start gap-3 px-4 py-2.5 shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none", highlight.includes(r.key) && "bg-status-infeasible")}
              >
                <Icon className={cn("mt-0.5 size-4 shrink-0", cls)} aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className="block type-callout text-label-1">{label(r.key)}</span>
                  {r.message ? <span className="block type-footnote break-words text-label-2">{r.message}</span> : null}
                </span>
                <span className={cn("shrink-0 type-footnote font-medium", cls)}>{t(`crbs.setup.req.status.${r.status}`)}</span>
              </li>
            );
          })}
        </ul>
      </Card>
      <div>
        <Button variant="secondary" size="sm" onClick={() => query.refetch()} disabled={query.isFetching} data-testid="requirements-recheck">
          <RefreshCw aria-hidden className={query.isFetching ? "motion-safe:animate-spin" : undefined} />
          {t("crbs.setup.req.recheck")}
        </Button>
      </div>
    </div>
  );
}
