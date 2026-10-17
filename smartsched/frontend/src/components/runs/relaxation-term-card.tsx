"use client";
/**
 * Settings › Çözücü › "Sığmayan dersler" for the active term: the term's relaxation policy, read and written through
 * `GET/PUT /terms/{id}/relaxation-policy` (backend `app/api/v1/terms.py`; the settings key
 * `term.<id>.relaxation_policy`, administrators, audited). The card shows the stored value (`source: term`) or the
 * default (`source: default`), saves a new one and can clear it back to the default.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { Button } from "@/components/ui/button";
import { BusyLabel } from "@/components/ui/busy-label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { relaxationApi, termPolicyKey, useTermRelaxationPolicy } from "@/lib/api/relaxation";
import { useI18n } from "@/lib/i18n/provider";
import { usePermissions } from "@/lib/permissions";
import { PolicyPicker, type Policy } from "./relaxation";

export function RelaxationTermCard() {
  const { term } = useActiveTerm();
  return term ? <TermPolicy key={term.id} termId={term.id} termCode={term.code} /> : null;
}

function TermPolicy({ termId, termCode }: { termId: number; termCode: string }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const { can } = usePermissions();
  const admin = can("planning.admin");
  const stored = useTermRelaxationPolicy(termId);
  const [value, setValue] = useState<Policy | null>(null);
  const [busy, setBusy] = useState<"save" | "clear" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const current = stored.data;
  const shown = value ?? current?.policy ?? null;
  const dirty = value !== null && (current?.source !== "term" || value !== current.policy);

  const write = async (policy: Policy | null) => {
    setBusy(policy ? "save" : "clear");
    setError(null);
    try {
      const out = await relaxationApi.put(termId, policy);
      qc.setQueryData(termPolicyKey(termId), out);
      setValue(null);
      toast.success(policy ? t("relax.term.saved", { term: termCode }) : t("relax.term.cleared", { term: termCode }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card data-testid="relax-term-card">
      <CardHeader>
        <CardTitle>{t("relax.term.title", { term: termCode })}</CardTitle>
        <CardDescription>{t("relax.term.lead")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {stored.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : (
          <PolicyPicker id="relax-term" value={shown} onChange={(v) => v !== "term" && setValue(v)} withTerm={false} disabled={!!busy || !admin} />
        )}
        <p className="type-footnote text-label-2" data-testid="relax-term-known" data-source={current?.source}>
          {stored.isError
            ? t("relax.term.unknown")
            : !current
              ? t("busy.loading")
              : current.stored_invalid
                ? t("relax.term.invalid")
                : current.source === "term"
                  ? t("relax.term.stored", { policy: t(`relax.short.${current.policy}`) })
                  : t("relax.term.default", { policy: t(`relax.short.${current.policy}`) })}
        </p>
        {!admin ? <p className="type-footnote text-label-2">{t("relax.term.adminOnly")}</p> : null}
        {error ? (
          <p role="alert" className="type-footnote text-status-infeasible-fg">
            {error}
          </p>
        ) : null}
        {admin ? (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" className="pointer-coarse:min-h-11" onClick={() => shown && void write(shown)} disabled={!shown || !!busy || !dirty} aria-busy={busy === "save" || undefined} data-testid="relax-term-save">
              <BusyLabel busy={busy === "save"} label={t("busy.saving")}>{t("relax.term.save")}</BusyLabel>
            </Button>
            {current?.source === "term" ? (
              <Button size="sm" variant="outline" className="pointer-coarse:min-h-11" onClick={() => void write(null)} disabled={!!busy} aria-busy={busy === "clear" || undefined} data-testid="relax-term-clear">
                <BusyLabel busy={busy === "clear"} label={t("busy.saving")}>{t("relax.term.clear")}</BusyLabel>
              </Button>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
