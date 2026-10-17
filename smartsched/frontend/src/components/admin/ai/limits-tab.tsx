"use client";
/**
 * Yapay zekâ › Limitler: the org monthly budget (tokens and / or USD; 0 = none), the per-user default daily / monthly
 * token limits, per-role defaults, per-user overrides (user > role > default), the warning threshold (soft, default
 * 80 %: in-app + e-mail to the recipients, a banner for the user; 100 % refuses with `ai_limit_reached` /
 * `ai_budget_exceeded`), the alert recipients, per-user requests per minute and concurrent calls, and an audited
 * one-off top-up of this month's budget. Every rule reads as a sentence.
 */
import { Plus, Save, Trash2 } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import { Alert, Field, Loading } from "@/components/admin/kit";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { type Limits, type LimitsIn, useAiLimits, useSaveLimits, useTopup } from "@/lib/api/ai-admin";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { compactTokens, errorMessage, parseLimit, pctText, usd } from "./ai-model";

const ROLES = ["ADMIN", "PLANNER", "VIEWER", "TEACHER"] as const;

export function LimitsTab({ canEdit }: { canEdit: boolean }) {
  const { t, locale } = useI18n();
  const q = useAiLimits();
  if (q.isLoading) return <Loading />;
  if (q.isError || !q.data) return <Alert tone="error">{errorMessage(q.error, locale, t("aiAdmin.error.load"))}</Alert>;
  return (
    <div className="flex flex-col gap-4" data-testid="ai-limits">
      {/* mounted once: after a save the form already shows what was stored; a remount would drop the focus */}
      <LimitsForm data={q.data} canEdit={canEdit} />
      {canEdit ? <Topup data={q.data} /> : null}
    </div>
  );
}

type Pair = { daily: string; monthly: string };
const pairOf = (p?: { daily?: number; monthly?: number }): Pair => ({ daily: String(p?.daily ?? ""), monthly: String(p?.monthly ?? "") });

function LimitsForm({ data, canEdit }: { data: Limits; canEdit: boolean }) {
  const { t, locale } = useI18n();
  const uid = useId();
  const save = useSaveLimits();
  const [f, setF] = useState({
    org_monthly_tokens: String(data.org_monthly_tokens),
    org_monthly_cost_usd: String(data.org_monthly_cost_usd),
    user_daily_tokens: String(data.user_daily_tokens),
    user_monthly_tokens: String(data.user_monthly_tokens),
    soft_pct: String(data.soft_pct),
    requests_per_minute: String(data.requests_per_minute),
    max_concurrent: String(data.max_concurrent),
    alert_recipients: data.alert_recipients.join(", "),
  });
  const [roles, setRoles] = useState<Record<string, Pair>>(() => Object.fromEntries(ROLES.map((r) => [r, pairOf(data.roles[r])])));
  const [users, setUsers] = useState<{ id: string; daily: string; monthly: string }[]>(() => Object.entries(data.users).map(([id, p]) => ({ id, ...pairOf(p) })));
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const soft = Number(f.soft_pct) || 80;

  const submit = () => {
    setError(null);
    const nums = (["org_monthly_tokens", "user_daily_tokens", "user_monthly_tokens", "requests_per_minute", "max_concurrent"] as const).map((k) => [k, parseLimit(f[k])] as const);
    const cost = Number(f.org_monthly_cost_usd.replace(",", "."));
    const pct = Number(f.soft_pct);
    const recipients = f.alert_recipients.split(/[,\s]+/).filter(Boolean).map(Number);
    const pairs = (p: Pair) => {
      const d = parseLimit(p.daily);
      const m = parseLimit(p.monthly);
      return d === null || m === null ? null : { ...(p.daily.trim() ? { daily: d } : {}), ...(p.monthly.trim() ? { monthly: m } : {}) };
    };
    const roleBody: Record<string, { daily?: number; monthly?: number }> = {};
    for (const r of ROLES) {
      const v = pairs(roles[r]!);
      if (v === null) return setError(t("aiAdmin.limits.invalid"));
      if (Object.keys(v).length) roleBody[r] = v;
    }
    const userBody: Record<string, { daily?: number; monthly?: number }> = {};
    for (const u of users) {
      const v = pairs(u);
      if (v === null || !/^\d+$/.test(u.id.trim())) return setError(t("aiAdmin.limits.invalid"));
      if (Object.keys(v).length) userBody[u.id.trim()] = v;
    }
    if (nums.some(([, v]) => v === null) || !Number.isFinite(cost) || cost < 0 || !(pct >= 1 && pct <= 99) || recipients.some((n) => !Number.isInteger(n) || n <= 0)) return setError(t("aiAdmin.limits.invalid"));
    const body: LimitsIn = { ...(Object.fromEntries(nums) as Record<string, number>), org_monthly_cost_usd: cost, soft_pct: pct, alert_recipients: recipients, roles: roleBody, users: userBody };
    save.mutate(body, { onSuccess: () => toast.success(t("aiAdmin.limits.saved")), onError: (e) => setError(errorMessage(e, locale, t("aiAdmin.error.save"))) });
  };

  const num = (k: keyof typeof f, label: MessageKey, hint?: string) => (
    <Field label={t(label)} htmlFor={`${uid}-${k}`} hint={hint}>
      <Input id={`${uid}-${k}`} inputMode="numeric" value={f[k]} onChange={set(k)} disabled={!canEdit} data-testid={`ai-limit-${k}`} />
    </Field>
  );

  return (
    <>
      <Card className="gap-3 px-4 py-4">
        <h3 className="type-headline text-label-1">{t("aiAdmin.limits.org")}</h3>
        <p className="type-footnote text-label-2">
          {t("aiAdmin.limits.orgNow", { tokens: compactTokens(data.org.month_tokens, locale), cost: usd(data.org.month_cost_usd, locale) })}
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          {num("org_monthly_tokens", "aiAdmin.limits.orgTokens", t("aiAdmin.limits.zeroHint"))}
          <Field label={t("aiAdmin.limits.orgCost")} htmlFor={`${uid}-cost`} hint={t("aiAdmin.limits.zeroHint")}>
            <Input id={`${uid}-cost`} inputMode="decimal" value={f.org_monthly_cost_usd} onChange={set("org_monthly_cost_usd")} disabled={!canEdit} data-testid="ai-limit-org_monthly_cost_usd" />
          </Field>
        </div>
      </Card>
      <Card className="gap-3 px-4 py-4">
        <h3 className="type-headline text-label-1">{t("aiAdmin.limits.defaults")}</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          {num("user_daily_tokens", "aiAdmin.limits.userDaily", t("aiAdmin.limits.zeroHint"))}
          {num("user_monthly_tokens", "aiAdmin.limits.userMonthly", t("aiAdmin.limits.zeroHint"))}
        </div>
        <h4 className="mt-2 type-callout font-semibold text-label-1">{t("aiAdmin.limits.roles")}</h4>
        <p className="type-footnote text-label-2">{t("aiAdmin.limits.rolesHint")}</p>
        <div className="flex flex-col gap-2">
          {ROLES.map((r) => (
            <div key={r} className="grid items-end gap-2 sm:grid-cols-[10rem_1fr_1fr]" data-testid={`ai-role-${r}`}>
              <p className="type-callout text-label-1 sm:pb-2">{t(`aiAdmin.role.${r}` as MessageKey)}</p>
              {(["daily", "monthly"] as const).map((k) => (
                <Field key={k} label={t(`aiAdmin.limits.${k}` as MessageKey)} htmlFor={`${uid}-${r}-${k}`}>
                  <Input id={`${uid}-${r}-${k}`} inputMode="numeric" value={roles[r]![k]} disabled={!canEdit} onChange={(e) => setRoles((x) => ({ ...x, [r]: { ...x[r]!, [k]: e.target.value } }))} />
                </Field>
              ))}
            </div>
          ))}
        </div>
        <h4 className="mt-2 type-callout font-semibold text-label-1">{t("aiAdmin.limits.users")}</h4>
        <div className="flex flex-col gap-2">
          {users.map((u, i) => (
            <div key={i} className="grid items-end gap-2 sm:grid-cols-[10rem_1fr_1fr_auto]" data-testid={`ai-user-limit-${i}`}>
              <Field label={t("aiAdmin.limits.userId")} htmlFor={`${uid}-u${i}`}>
                <Input id={`${uid}-u${i}`} inputMode="numeric" value={u.id} disabled={!canEdit} onChange={(e) => setUsers((x) => x.map((y, j) => (j === i ? { ...y, id: e.target.value } : y)))} />
              </Field>
              {(["daily", "monthly"] as const).map((k) => (
                <Field key={k} label={t(`aiAdmin.limits.${k}` as MessageKey)} htmlFor={`${uid}-u${i}-${k}`}>
                  <Input id={`${uid}-u${i}-${k}`} inputMode="numeric" value={u[k]} disabled={!canEdit} onChange={(e) => setUsers((x) => x.map((y, j) => (j === i ? { ...y, [k]: e.target.value } : y)))} />
                </Field>
              ))}
              {canEdit ? (
                <Button variant="ghost" onClick={() => setUsers((x) => x.filter((_, j) => j !== i))} aria-label={t("aiAdmin.limits.remove")}>
                  <Trash2 aria-hidden />
                  <span className="sm:sr-only">{t("aiAdmin.limits.remove")}</span>
                </Button>
              ) : null}
            </div>
          ))}
          {canEdit ? (
            <Button variant="outline" className="self-start" onClick={() => setUsers((x) => [...x, { id: "", daily: "", monthly: "" }])} data-testid="ai-user-limit-add">
              <Plus aria-hidden />
              {t("aiAdmin.limits.addUser")}
            </Button>
          ) : null}
        </div>
      </Card>
      <Card className="gap-3 px-4 py-4">
        <h3 className="type-headline text-label-1">{t("aiAdmin.limits.alerts")}</h3>
        <p className="type-callout text-label-1">{t("aiAdmin.limits.ruleWarn", { pct: pctText(soft, locale) })}</p>
        <p className="type-callout text-label-1">{t("aiAdmin.limits.ruleBlock")}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          {num("soft_pct", "aiAdmin.limits.soft")}
          <Field label={t("aiAdmin.limits.recipients")} htmlFor={`${uid}-rec`} hint={t("aiAdmin.limits.recipientsHint")}>
            <Input id={`${uid}-rec`} value={f.alert_recipients} onChange={set("alert_recipients")} disabled={!canEdit} data-testid="ai-limit-recipients" />
          </Field>
          {num("requests_per_minute", "aiAdmin.limits.rate", t("aiAdmin.limits.zeroHint"))}
          {num("max_concurrent", "aiAdmin.limits.concurrent", t("aiAdmin.limits.zeroHint"))}
        </div>
      </Card>
      {error ? <Alert tone="error" testId="ai-limits-error">{error}</Alert> : null}
      {canEdit ? (
        <Button className="self-start" onClick={submit} {...busyProps(save.isPending)} data-testid="ai-limits-save">
          <BusyLabel busy={save.isPending} label={t("busy.saving")} icon={<Save aria-hidden />}>
            {t("aiAdmin.limits.save")}
          </BusyLabel>
        </Button>
      ) : null}
    </>
  );
}

function Topup({ data }: { data: Limits }) {
  const { t, locale } = useI18n();
  const uid = useId();
  const topup = useTopup();
  const [tokens, setTokens] = useState("");
  const [cost, setCost] = useState("");
  const [reason, setReason] = useState("");
  const thisMonth = data.topups.filter((x) => x.month === data.org.month);
  const tk = parseLimit(tokens) ?? -1;
  const c = Number(cost.replace(",", ".") || 0);
  const valid = tk >= 0 && c >= 0 && (tk > 0 || c > 0) && reason.trim().length >= 3;
  return (
    <Card className="gap-3 px-4 py-4" data-testid="ai-topup">
      <h3 className="type-headline text-label-1">{t("aiAdmin.topup.title")}</h3>
      <p className="type-footnote text-label-2">{t("aiAdmin.topup.lead")}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("aiAdmin.topup.tokens")} htmlFor={`${uid}-t`}>
          <Input id={`${uid}-t`} inputMode="numeric" value={tokens} onChange={(e) => setTokens(e.target.value)} data-testid="ai-topup-tokens" />
        </Field>
        <Field label={t("aiAdmin.topup.cost")} htmlFor={`${uid}-c`}>
          <Input id={`${uid}-c`} inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} />
        </Field>
      </div>
      <Field label={t("aiAdmin.topup.reason")} htmlFor={`${uid}-r`} hint={t("aiAdmin.topup.reasonHint")}>
        <Textarea id={`${uid}-r`} value={reason} onChange={(e) => setReason(e.target.value)} rows={2} data-testid="ai-topup-reason" />
      </Field>
      <Button
        variant="outline"
        className="self-start"
        {...busyProps(topup.isPending, !valid)}
        onClick={() =>
          topup.mutate(
            { tokens: Math.max(tk, 0), cost_usd: c, reason: reason.trim() },
            {
              onSuccess: () => {
                setTokens("");
                setCost("");
                setReason("");
                toast.success(t("aiAdmin.topup.done"));
              },
              onError: (e) => toast.error(errorMessage(e, locale, t("aiAdmin.error.save"))),
            },
          )
        }
        data-testid="ai-topup-submit"
      >
        <BusyLabel busy={topup.isPending} label={t("busy.saving")} icon={<Plus aria-hidden />}>
          {t("aiAdmin.topup.submit")}
        </BusyLabel>
      </Button>
      {thisMonth.length ? (
        <ul className="flex flex-col gap-1">
          {thisMonth.map((x, i) => (
            <li key={i} className="type-footnote text-label-2">
              {[x.tokens ? compactTokens(x.tokens, locale) : null, x.cost_usd ? usd(x.cost_usd, locale) : null].filter(Boolean).join(" + ")} · {x.reason}
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}
