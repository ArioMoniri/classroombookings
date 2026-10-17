"use client";
/**
 * Yapay zekâ › Koruma: the protections that are always on (shown as text with a lock, not as disabled switches), the
 * switchable guardrails (scope, prompt injection in typed text, upload neutralisation, output check, rate limit, the
 * optional model-based scope check), a dry-run test bench (no model call, no usage row), the red-team self-test over
 * the shipped TR + EN corpus, and the recent refusals with their reason (metadata only: no prompt text is stored).
 */
import Link from "next/link";
import { FlaskConical, Lock, ShieldCheck } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import { Alert, Loading } from "@/components/admin/kit";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { MicButton } from "@/components/voice";
import { AI_FEATURES, GUARD_SWITCHES, useAiGuardrails, useAiRefusals, useGuardCheck, useRedTeam, useSaveGuardrails } from "@/lib/api/ai-admin";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { StatusWord, useAiLabels } from "./ai-kit";
import { errorMessage } from "./ai-model";
import { VoiceCard } from "./voice-card";

const FIXED = ["noAuto", "ids", "files", "kvkk"] as const;
const EXAMPLES = ["aiAdmin.guard.ex1", "aiAdmin.guard.ex2", "aiAdmin.guard.ex3"] as const;

export function GuardTab({ canEdit }: { canEdit: boolean }) {
  const { t } = useI18n();
  return (
    <div className="flex flex-col gap-4" data-testid="ai-guard">
      <p className="type-callout text-label-2">{t("aiAdmin.guard.lead")}</p>
      <Card className="gap-2 px-4 py-4">
        <h3 className="type-headline text-label-1">{t("aiAdmin.guard.always")}</h3>
        <ul className="flex flex-col gap-1.5">
          {FIXED.map((k) => (
            <li key={k} className="flex items-start gap-2 type-callout text-label-1">
              <Lock aria-hidden className="mt-0.5 size-4 shrink-0 text-label-2" />
              <span>{t(`aiAdmin.guard.fixed.${k}` as MessageKey)}</span>
            </li>
          ))}
        </ul>
      </Card>
      <Switches canEdit={canEdit} />
      <VoiceCard canEdit={canEdit} />
      <Bench />
      <RedTeamCard />
      <Refusals />
      <p className="type-footnote text-label-2">
        <Link href="/settings" className="text-tint-text underline-offset-4 hover:underline pointer-coarse:inline-block pointer-coarse:min-h-11 pointer-coarse:py-3">
          {t("aiAdmin.guard.kvkkLink")}
        </Link>
      </p>
    </div>
  );
}

function Switches({ canEdit }: { canEdit: boolean }) {
  const { t, locale } = useI18n();
  const uid = useId();
  const q = useAiGuardrails();
  const save = useSaveGuardrails();
  if (q.isLoading) return <Loading />;
  if (!q.data) return <Alert tone="error">{errorMessage(q.error, locale, t("aiAdmin.error.load"))}</Alert>;
  return (
    <Card className="gap-1 px-4 py-4">
      <h3 className="type-headline text-label-1">{t("aiAdmin.guard.switchable")}</h3>
      <ul className="flex flex-col divide-y divide-hairline">
        {GUARD_SWITCHES.map((k) => (
          <li key={k} className="flex items-start justify-between gap-4 py-3">
            <div className="min-w-0">
              <Label htmlFor={`${uid}-${k}`} className="type-callout font-medium text-label-1">
                {t(`aiAdmin.guard.switch.${k}` as MessageKey)}
              </Label>
              <p className="type-footnote text-label-2">{t(`aiAdmin.guard.hint.${k}` as MessageKey)}</p>
            </div>
            <Switch
              id={`${uid}-${k}`}
              checked={q.data[k]}
              disabled={!canEdit || save.isPending}
              onCheckedChange={(v) => save.mutate({ [k]: v }, { onSuccess: () => toast.success(t("aiAdmin.guard.saved")), onError: (e) => toast.error(errorMessage(e, locale, t("aiAdmin.error.save"))) })}
              data-testid={`ai-guard-${k}`}
            />
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Bench() {
  const { t, locale } = useI18n();
  const labels = useAiLabels();
  const uid = useId();
  const check = useGuardCheck();
  const [text, setText] = useState("");
  const [feature, setFeature] = useState("chat");
  const [surface, setSurface] = useState<"user" | "upload">("user");
  const r = check.data;
  const verdict = r
    ? r.result === "allow" || r.result === "keep"
      ? { tone: "ok", text: r.result === "keep" ? t("aiAdmin.guard.keep") : t("aiAdmin.guard.pass") }
      : r.result === "mark"
        ? { tone: "warning", text: t("aiAdmin.guard.mark", { reason: labels.reason(r.reason_code) }) }
        : { tone: "error", text: r.result === "remove" ? t("aiAdmin.guard.remove", { reason: labels.reason(r.reason_code) }) : t("aiAdmin.guard.wouldBlock", { reason: labels.reason(r.reason_code) }) }
    : null;
  return (
    <Card className="gap-3 px-4 py-4" data-testid="ai-bench">
      <h3 className="type-headline text-label-1">{t("aiAdmin.guard.bench")}</h3>
      <p className="type-footnote text-label-2">{t("aiAdmin.guard.benchLead")}</p>
      <div className="flex flex-wrap gap-2">
        {EXAMPLES.map((k) => (
          <Button key={k} variant="secondary" onClick={() => setText(t(k))}>
            {t(k)}
          </Button>
        ))}
      </div>
      <div className="flex flex-col gap-1.5" data-voice-scope>
        <Label htmlFor={`${uid}-text`} className="type-footnote font-medium text-label-2">
          {t("aiAdmin.guard.benchText")}
        </Label>
        <Textarea id={`${uid}-text`} value={text} onChange={(e) => setText(e.target.value)} rows={3} data-testid="ai-bench-text" />
        <MicButton target="guard" className="self-start" />
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <SegmentedControl<"user" | "upload">
          aria-label={t("aiAdmin.guard.surface")}
          semantics="radiogroup"
          value={surface}
          onValueChange={setSurface}
          options={[
            { value: "user", label: t("aiAdmin.guard.surfaceUser"), testId: "ai-bench-user" },
            { value: "upload", label: t("aiAdmin.guard.surfaceUpload"), testId: "ai-bench-upload" },
          ]}
        />
        {surface === "user" ? (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`${uid}-f`} className="type-footnote font-medium text-label-2">
              {t("aiAdmin.guard.feature")}
            </Label>
            <NativeSelect id={`${uid}-f`} value={feature} onChange={(e) => setFeature(e.target.value)}>
              {AI_FEATURES.map((f) => (
                <option key={f} value={f}>
                  {labels.feature(f)}
                </option>
              ))}
            </NativeSelect>
          </div>
        ) : null}
        <Button {...busyProps(check.isPending, !text.trim())} onClick={() => check.mutate({ text, feature, surface })} data-testid="ai-bench-run">
          <BusyLabel busy={check.isPending} label={t("busy.checking")} icon={<FlaskConical aria-hidden />}>
            {t("aiAdmin.guard.run")}
          </BusyLabel>
        </Button>
      </div>
      <div role="status" aria-live="polite" data-testid="ai-bench-result">
        {check.isError ? <Alert tone="error">{errorMessage(check.error, locale, t("aiAdmin.error.load"))}</Alert> : null}
        {verdict ? (
          <div className="flex flex-col gap-1">
            <StatusWord tone={verdict.tone}>{verdict.text}</StatusWord>
            {r?.message_tr && r.result === "refuse" ? <p className="type-footnote text-label-2">{locale === "tr" ? r.message_tr : r.message_en}</p> : null}
          </div>
        ) : null}
      </div>
    </Card>
  );
}

function RedTeamCard() {
  const { t, locale } = useI18n();
  const run = useRedTeam();
  const r = run.data;
  return (
    <Card className="gap-3 px-4 py-4" data-testid="ai-redteam">
      <h3 className="type-headline text-label-1">{t("aiAdmin.redteam.title")}</h3>
      <p className="type-footnote text-label-2">{t("aiAdmin.redteam.lead")}</p>
      <Button variant="outline" className="self-start" {...busyProps(run.isPending)} onClick={() => run.mutate()} data-testid="ai-redteam-run">
        <BusyLabel busy={run.isPending} label={t("busy.checking")} icon={<ShieldCheck aria-hidden />}>
          {t("aiAdmin.redteam.run")}
        </BusyLabel>
      </Button>
      <div role="status" aria-live="polite">
        {run.isError ? <Alert tone="error">{errorMessage(run.error, locale, t("aiAdmin.error.load"))}</Alert> : null}
        {r ? (
          <div className="flex flex-col gap-1" data-testid="ai-redteam-result">
            <StatusWord tone={r.total.gate ? "ok" : "error"}>{r.total.gate ? t("aiAdmin.redteam.pass") : t("aiAdmin.redteam.fail")}</StatusWord>
            <p className="type-footnote text-label-2">{t("aiAdmin.redteam.result", { passed: r.total.passed, cases: r.total.cases, fp: r.total.false_positives })}</p>
          </div>
        ) : null}
      </div>
    </Card>
  );
}

function Refusals() {
  const { t, locale } = useI18n();
  const labels = useAiLabels();
  const q = useAiRefusals();
  const rows = q.data?.rows ?? [];
  const fmt = new Intl.DateTimeFormat(locale === "tr" ? "tr-TR" : "en-GB", { dateStyle: "short", timeStyle: "short", timeZone: "Europe/Istanbul" });
  return (
    <Card className="gap-3 px-4 py-4" data-testid="ai-refusals">
      <h3 className="type-headline text-label-1">{t("aiAdmin.log.title")}</h3>
      {q.isLoading ? <Loading /> : null}
      {!q.isLoading && !rows.length ? <p className="type-callout text-label-2">{t("aiAdmin.log.empty")}</p> : null}
      <ul className="flex flex-col divide-y divide-hairline">
        {rows.map((r) => (
          <li key={r.id} className="flex flex-col gap-0.5 py-2.5 sm:flex-row sm:items-baseline sm:gap-4" data-testid={`ai-refusal-${r.id}`}>
            <span className="type-footnote text-label-2 sm:w-36 tabular-nums">{r.at ? fmt.format(new Date(`${r.at}Z`)) : ""}</span>
            <span className="type-callout font-medium text-label-1 sm:w-48">{r.user_label ?? t("aiAdmin.users.system")}</span>
            <span className="type-callout text-label-1 sm:flex-1">{labels.reason(r.reason_code)}</span>
            <span className="type-footnote text-label-2">
              {labels.feature(r.feature)} · {labels.outcome(r.outcome)}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
