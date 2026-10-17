"use client";
/**
 * Settings › Bildirim kanalları (`setup.settings`; backend app/api/v1/channels.py, checklist
 * docs/deploy/notification-channels.md). One card per channel: switch, content mode (link only / full text),
 * write-only sender secrets (only "Ayarlandı" ever comes back), options, the KVKK sign-off (officer + legal basis;
 * withdrawing stops sending at once), and per channel: VAPID keys (Web Push), bot set-up (Telegram), the risk
 * acknowledgement + QR session (WhatsApp Web bridge), department targets (Teams / Slack). Below: the delivery log
 * (no addresses, no secrets). A channel sends only when its `missing` list is empty.
 */
import { ChevronDown, Plus, QrCode, RefreshCcw, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog, Field, FieldRow, Loading, SelectField } from "@/components/admin/kit";
import { Alert } from "@/components/ui/alert";
import { BusyButton } from "@/components/ui/busy-label";
import { Button, IconButton } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { StatusDot } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useBookingFormat } from "@/components/bookings/use-booking-format";
import { useDepartments } from "@/lib/api/crbs";
import { channelKeys, channelLabel, channels, useChannelDepartments, useChannelMutation, useChannelsAdmin, useDeliveries, type BridgeState, type ChannelConfig, type ChannelConfigIn } from "@/lib/api/channels";
import { apiProblem } from "@/lib/api/identity";
import { useI18n } from "@/lib/i18n/provider";

/** The secrets an administrator types per channel (server-generated ones — VAPID, webhook secret — never). */
function adminSecrets(c: ChannelConfig): string[] {
  switch (c.kind) {
    case "telegram":
      return ["bot_token"];
    case "whatsapp":
      return ["access_token"];
    case "whatsapp_web":
      return ["user_token"];
    case "sms":
      return Object.keys(c.secrets).length ? Object.keys(c.secrets) : ["account_sid", "auth_token"];
    default:
      return [];
  }
}

type OptionSpec = { name: string; kind: "text" | "number" | "select"; choices?: string[]; mono?: boolean };
const OPTIONS: Record<string, OptionSpec[]> = {
  webpush: [{ name: "contact", kind: "text" }, { name: "ttl_s", kind: "number" }],
  telegram: [{ name: "bot_username", kind: "text", mono: true }, { name: "update_mode", kind: "select", choices: ["webhook", "poll"] }],
  whatsapp: [
    { name: "phone_number_id", kind: "text", mono: true },
    { name: "template_notice", kind: "text", mono: true },
    { name: "template_code", kind: "text", mono: true },
    { name: "lang_tr", kind: "text", mono: true },
    { name: "lang_en", kind: "text", mono: true },
  ],
  sms: [{ name: "provider", kind: "select", choices: ["twilio", "vonage"] }, { name: "from_number", kind: "text", mono: true }],
};

const KEYS = [channelKeys.admin, channelKeys.mine];

export function ChannelsAdmin() {
  const { t, locale } = useI18n();
  const q = useChannelsAdmin();
  // open cards survive the refetch after a save (the cards are keyed by kind, their forms by updated_at)
  const [open, setOpen] = useState<Record<string, boolean>>({});
  if (q.isLoading) return <Loading />;
  if (q.isError || !q.data) return <Alert tone="error">{apiProblem(q.error, locale).text ?? t("channels.admin.loadError")}</Alert>;
  return (
    <div className="flex flex-col gap-5" data-testid="channels-admin">
      <p className="type-callout text-label-2">{t("channels.admin.lead")}</p>
      {!q.data.public_url ? <Alert tone="warning" title={t("channels.admin.noPublicUrlTitle")}>{t("channels.admin.noPublicUrl")}</Alert> : null}
      {q.data.channels.map((c) => (
        <ChannelCard key={c.kind} c={c} webhookUrl={q.data.telegram_webhook_url ?? null} open={!!open[c.kind]} onToggle={() => setOpen((p) => ({ ...p, [c.kind]: !p[c.kind] }))} />
      ))}
      <DeliveriesLog kinds={q.data.channels.map((c) => c.kind)} />
    </div>
  );
}

function missingLabel(name: string, t: ReturnType<typeof useI18n>["t"]): string {
  const known = ["enabled", "kvkk_signoff", "risk_ack", "bridge_session", "department_targets", "WHATSAPP_BRIDGE_URL", "provider"];
  if (known.includes(name)) return t(`channels.admin.missing.${name}` as "channels.admin.missing.enabled");
  return t(`channels.admin.field.${name}` as "channels.admin.field.bot_token");
}

function ChannelCard({ c, webhookUrl, open, onToggle }: { c: ChannelConfig; webhookUrl: string | null; open: boolean; onToggle: () => void }) {
  const { t, locale } = useI18n();
  const [error, setError] = useState<string | null>(null);
  const put = useChannelMutation((body: ChannelConfigIn) => channels.put(c.kind, body), KEYS);
  const save = (body: ChannelConfigIn, ok = t("channels.admin.saved")) => {
    setError(null);
    put.mutate(body, { onSuccess: () => toast.success(ok), onError: (e) => setError(apiProblem(e, locale).text ?? t("channels.admin.saveFailed")) });
  };
  const missing = c.missing.filter((m) => m !== "enabled");
  const label = channelLabel(c, locale);
  const bodyId = `channel-${c.kind}-body`;
  return (
    <Card data-testid={`channel-${c.kind}`}>
      <CardHeader>
        <div className="flex flex-wrap items-center gap-3">
          <CardTitle className="min-w-0 flex-1">{label}</CardTitle>
          <StatusDot tone={c.enabled ? "feasible" : c.enabled_requested ? "warning" : "neutral"}>{c.enabled ? t("channels.admin.sending") : c.enabled_requested ? t("channels.admin.incomplete") : t("channels.admin.off")}</StatusDot>
          <Switch checked={c.enabled_requested} disabled={put.isPending} onCheckedChange={(v) => save({ enabled: v })} aria-label={t("channels.admin.enableNamed", { name: label })} data-testid={`channel-enable-${c.kind}`} />
        </div>
        {c.enabled_requested && missing.length ? (
          <CardDescription data-testid={`channel-missing-${c.kind}`}>{t("channels.admin.missingList", { list: missing.map((m) => missingLabel(m, t)).join(", ") })}</CardDescription>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Button type="button" variant="ghost" shape="rect" className="-mx-2 justify-between px-2" aria-expanded={open} aria-controls={bodyId} onClick={onToggle} data-testid={`channel-toggle-${c.kind}`}>
          <span>{t("channels.admin.settings")}</span>
          <ChevronDown className={open ? "rotate-180" : undefined} aria-hidden />
        </Button>
        {open ? (
          <div id={bodyId} className="flex flex-col gap-4">
            {(
              <FieldRow label={t("channels.admin.contentMode")} hint={t("channels.admin.contentModeHint")}>
                <SegmentedControl
                  semantics="radiogroup"
                  size="md"
                  aria-label={t("channels.admin.contentMode")}
                  value={c.content_mode}
                  onValueChange={(v) => v !== c.content_mode && save({ content_mode: v })}
                  options={[
                    { value: "link_only", label: t("channels.admin.linkOnly") },
                    { value: "full", label: t("channels.admin.full") },
                  ]}
                />
              </FieldRow>
            )}
            {/* sibling keys must differ: a shared key made React keep a stale copy of the form after a save (duplicate ids) */}
            <CredentialsForm key={`credentials-${c.updated_at ?? "new"}`} c={c} onSave={save} pending={put.isPending} />
            {c.kind === "webpush" ? <VapidPanel c={c} /> : null}
            {c.kind === "telegram" ? <TelegramPanel c={c} webhookUrl={webhookUrl} /> : null}
            {c.kind === "whatsapp_web" ? <BridgePanel c={c} onAck={(v) => save({ risk_ack: v })} /> : null}
            {c.kind === "teams" || c.kind === "slack" ? <DepartmentTargets kind={c.kind} /> : null}
            <SignoffPanel key={`signoff-${c.updated_at ?? "new"}`} c={c} onSave={save} pending={put.isPending} />
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function CredentialsForm({ c, onSave, pending }: { c: ChannelConfig; onSave: (b: ChannelConfigIn) => void; pending: boolean }) {
  const { t } = useI18n();
  const secrets = adminSecrets(c);
  const options = OPTIONS[c.kind] ?? [];
  const [secretValues, setSecretValues] = useState<Record<string, string>>({});
  const [replacing, setReplacing] = useState<Record<string, boolean>>({});
  const [optionValues, setOptionValues] = useState<Record<string, string>>(() => Object.fromEntries(options.map((o) => [o.name, c.options[o.name] == null ? "" : String(c.options[o.name])])));
  if (!secrets.length && !options.length) return null;
  const changedOptions = Object.fromEntries(options.filter((o) => optionValues[o.name] !== (c.options[o.name] == null ? "" : String(c.options[o.name]))).map((o) => [o.name, optionValues[o.name] === "" ? null : o.kind === "number" ? Number(optionValues[o.name]) : optionValues[o.name]!]));
  const changedSecrets = Object.fromEntries(Object.entries(secretValues).filter(([, v]) => v.trim()));
  const dirty = Object.keys(changedOptions).length + Object.keys(changedSecrets).length > 0;
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!dirty) return;
        onSave({ ...(Object.keys(changedOptions).length ? { options: changedOptions } : {}), ...(Object.keys(changedSecrets).length ? { secrets: changedSecrets } : {}) });
        setSecretValues({});
        setReplacing({});
      }}
      data-testid={`channel-credentials-${c.kind}`}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        {options.map((o) => (
          <Field key={o.name} label={t(`channels.admin.field.${o.name}` as "channels.admin.field.contact")} htmlFor={`${c.kind}-${o.name}`}>
            {o.kind === "select" ? (
              <SelectField id={`${c.kind}-${o.name}`} value={optionValues[o.name] ?? ""} onChange={(e) => setOptionValues((p) => ({ ...p, [o.name]: e.target.value }))}>
                <option value="">—</option>
                {(o.choices ?? []).map((ch) => (
                  <option key={ch} value={ch}>
                    {t(`channels.admin.choice.${ch}` as "channels.admin.choice.webhook")}
                  </option>
                ))}
              </SelectField>
            ) : (
              <Input id={`${c.kind}-${o.name}`} type={o.kind === "number" ? "number" : "text"} value={optionValues[o.name] ?? ""} onChange={(e) => setOptionValues((p) => ({ ...p, [o.name]: e.target.value }))} autoComplete="off" spellCheck={false} className={o.mono ? "font-mono" : undefined} />
            )}
          </Field>
        ))}
        {secrets.map((name) => {
          const set = Boolean(c.secrets[name]);
          return (
            <Field key={name} label={t(`channels.admin.field.${name}` as "channels.admin.field.bot_token")} htmlFor={`${c.kind}-${name}`} hint={t("channels.admin.secretHint")}>
              {set && !replacing[name] ? (
                <span className="flex flex-wrap items-center gap-2">
                  <StatusDot tone="feasible">
                    <span data-testid={`secret-set-${c.kind}-${name}`}>{t("channels.admin.secretSet")}</span>
                  </StatusDot>
                  <Button type="button" size="sm" variant="outline" onClick={() => setReplacing((p) => ({ ...p, [name]: true }))}>
                    {t("channels.admin.replace")}
                  </Button>
                </span>
              ) : (
                <Input id={`${c.kind}-${name}`} type="password" autoComplete="new-password" spellCheck={false} value={secretValues[name] ?? ""} onChange={(e) => setSecretValues((p) => ({ ...p, [name]: e.target.value }))} data-testid={`secret-${c.kind}-${name}`} />
              )}
            </Field>
          );
        })}
      </div>
      <div>
        <BusyButton type="submit" size="sm" busy={pending} busyLabel={t("busy.saving")} disabled={!dirty} data-testid={`channel-save-${c.kind}`}>
          {t("crbs.common.save")}
        </BusyButton>
      </div>
    </form>
  );
}

function SignoffPanel({ c, onSave, pending }: { c: ChannelConfig; onSave: (b: ChannelConfigIn, ok?: string) => void; pending: boolean }) {
  const { t } = useI18n();
  const fmt = useBookingFormat();
  const s = c.kvkk_signoff;
  const [basis, setBasis] = useState("");
  const [officer, setOfficer] = useState("");
  const [withdraw, setWithdraw] = useState(false);
  return (
    <section className="flex flex-col gap-3 rounded-xl bg-fill-3 p-3 edge-hairline" aria-labelledby={`kvkk-${c.kind}`} data-testid={`kvkk-${c.kind}`}>
      <h3 id={`kvkk-${c.kind}`} className="type-headline text-label-1">
        {t("channels.admin.kvkkTitle")}
      </h3>
      {s?.signed ? (
        <>
          <StatusDot tone="feasible">{t("channels.admin.kvkkSigned", { by: s.officer || s.by || "—", at: s.at ? fmt.dateTime(s.at) : "—" })}</StatusDot>
          {s.legal_basis ? <p className="type-footnote text-label-2">{t("channels.admin.kvkkBasis", { basis: s.legal_basis })}</p> : null}
          <Button type="button" size="sm" variant="ghost" className="self-start" onClick={() => setWithdraw(true)} data-testid={`kvkk-withdraw-${c.kind}`}>
            {t("channels.admin.kvkkWithdraw")}
          </Button>
          <ConfirmDialog open={withdraw} onOpenChange={setWithdraw} title={t("channels.admin.kvkkWithdrawTitle")} description={t("channels.admin.kvkkWithdrawBody")} confirmLabel={t("channels.admin.kvkkWithdraw")} destructive busy={pending} onConfirm={() => (onSave({ kvkk_signoff: { signed: false } }, t("channels.admin.kvkkWithdrawn")), setWithdraw(false))} />
        </>
      ) : (
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!basis.trim()) return;
            onSave({ kvkk_signoff: { signed: true, legal_basis: basis.trim(), officer: officer.trim() || null } }, t("channels.admin.kvkkSaved"));
          }}
        >
          <p className="type-footnote text-label-2">{t("channels.admin.kvkkLead")}</p>
          <Field label={t("channels.admin.kvkkBasisLabel")} htmlFor={`kvkk-basis-${c.kind}`} hint={t("channels.admin.kvkkBasisHint")}>
            <Textarea id={`kvkk-basis-${c.kind}`} rows={2} maxLength={500} value={basis} onChange={(e) => setBasis(e.target.value)} data-testid={`kvkk-basis-${c.kind}`} />
          </Field>
          <Field label={t("channels.admin.kvkkOfficer")} htmlFor={`kvkk-officer-${c.kind}`}>
            <Input id={`kvkk-officer-${c.kind}`} maxLength={200} value={officer} onChange={(e) => setOfficer(e.target.value)} data-testid={`kvkk-officer-${c.kind}`} />
          </Field>
          <div>
            <BusyButton type="submit" size="sm" variant="outline" busy={pending} busyLabel={t("busy.saving")} disabled={!basis.trim()} data-testid={`kvkk-sign-${c.kind}`}>
              {t("channels.admin.kvkkSign")}
            </BusyButton>
          </div>
        </form>
      )}
    </section>
  );
}

function VapidPanel({ c }: { c: ChannelConfig }) {
  const { t, locale } = useI18n();
  const [rotate, setRotate] = useState(false);
  const gen = useChannelMutation((r: boolean) => channels.vapid(r), KEYS);
  const has = Boolean(c.options.vapid_public_key);
  const run = (r: boolean) => gen.mutate(r, { onSuccess: () => (toast.success(t("channels.admin.vapidDone")), setRotate(false)), onError: (e) => toast.error(apiProblem(e, locale).text ?? t("channels.admin.saveFailed")) });
  return (
    <FieldRow label={t("channels.admin.vapid")} hint={has ? t("channels.admin.vapidSet") : t("channels.admin.vapidMissing")}>
      {has ? (
        <Button type="button" size="sm" variant="ghost" onClick={() => setRotate(true)}>
          <RefreshCcw aria-hidden />
          {t("channels.admin.vapidRotate")}
        </Button>
      ) : (
        <BusyButton type="button" size="sm" variant="outline" busy={gen.isPending} busyLabel={t("busy.working")} onClick={() => run(false)} data-testid="vapid-generate">
          {t("channels.admin.vapidGenerate")}
        </BusyButton>
      )}
      <ConfirmDialog open={rotate} onOpenChange={setRotate} title={t("channels.admin.vapidRotateTitle")} description={t("channels.admin.vapidRotateBody")} confirmLabel={t("channels.admin.vapidRotate")} destructive busy={gen.isPending} onConfirm={() => run(true)} />
    </FieldRow>
  );
}

function TelegramPanel({ c, webhookUrl }: { c: ChannelConfig; webhookUrl: string | null }) {
  const { t, locale } = useI18n();
  const setup = useChannelMutation(() => channels.telegramSetup(), KEYS);
  const [result, setResult] = useState<string | null>(null);
  return (
    <FieldRow label={t("channels.admin.telegramSetup")} hint={c.options.update_mode === "poll" ? t("channels.admin.telegramPoll") : webhookUrl ? t("channels.admin.telegramWebhook", { url: webhookUrl }) : t("channels.admin.noPublicUrl")}>
      <BusyButton
        type="button"
        size="sm"
        variant="outline"
        busy={setup.isPending}
        busyLabel={t("busy.working")}
        disabled={!c.secrets.bot_token}
        onClick={() =>
          setup.mutate(undefined, {
            onSuccess: (o) => setResult(t("channels.admin.telegramDone", { bot: o.bot_username ?? "—", mode: o.mode ?? "—" })),
            onError: (e) => setResult(apiProblem(e, locale).text ?? t("channels.admin.saveFailed")),
          })
        }
        data-testid="telegram-setup"
      >
        {t("channels.admin.telegramSetupAction")}
      </BusyButton>
      {result ? (
        <span role="status" className="type-footnote text-label-2">
          {result}
        </span>
      ) : null}
    </FieldRow>
  );
}

function BridgePanel({ c, onAck }: { c: ChannelConfig; onAck: (v: boolean) => void }) {
  const { t, locale } = useI18n();
  const [ack, setAck] = useState(false);
  const [state, setState] = useState<BridgeState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const connect = useChannelMutation(() => channels.bridgeConnect(), KEYS);
  const status = useChannelMutation(() => channels.bridgeStatus(), KEYS);
  const logout = useChannelMutation(() => channels.bridgeLogout(), KEYS);
  const acknowledged = Boolean(c.risk_ack && (c.risk_ack as { acknowledged?: boolean }).acknowledged);
  const risk = locale === "tr" ? c.risk_tr : c.risk_en;
  const qr = typeof state?.qr === "string" && state.qr.startsWith("data:image/") ? state.qr : null;
  const onErr = (e: unknown) => setError(apiProblem(e, locale).text ?? t("channels.admin.saveFailed"));
  return (
    <section className="flex flex-col gap-3" data-testid="bridge-panel">
      <Alert tone="warning" title={t("channels.admin.bridgeRiskTitle")}>
        {risk}
      </Alert>
      {!acknowledged ? (
        <div className="flex flex-col gap-2">
          <label className="flex items-start gap-2 type-callout text-label-1">
            <Checkbox checked={ack} onCheckedChange={(v) => setAck(v === true)} className="mt-0.5" data-testid="bridge-ack" />
            <span>{t("channels.admin.bridgeAck")}</span>
          </label>
          <Button type="button" size="sm" variant="outline" className="self-start" disabled={!ack} onClick={() => onAck(true)} data-testid="bridge-ack-save">
            {t("channels.admin.bridgeAckSave")}
          </Button>
        </div>
      ) : (
        <>
          <p className="type-footnote text-label-2">{t("channels.admin.bridgeAcked", { by: (c.risk_ack as { by?: string } | null)?.by ?? "—" })}</p>
          {!c.bridge_url_configured ? <Alert tone="neutral">{t("channels.admin.bridgeNoUrl")}</Alert> : null}
          <div className="flex flex-wrap gap-2">
            <BusyButton type="button" size="sm" variant="outline" busy={connect.isPending} busyLabel={t("busy.working")} disabled={!c.bridge_url_configured || !c.secrets.user_token} onClick={() => (setError(null), connect.mutate(undefined, { onSuccess: setState, onError: onErr }))} data-testid="bridge-connect">
              <QrCode aria-hidden />
              {t("channels.admin.bridgeQr")}
            </BusyButton>
            <Button type="button" size="sm" variant="ghost" disabled={!c.bridge_url_configured} onClick={() => status.mutate(undefined, { onSuccess: setState, onError: onErr })}>
              {t("channels.admin.bridgeStatus")}
            </Button>
            <Button type="button" size="sm" variant="ghost" disabled={!c.bridge_url_configured} onClick={() => logout.mutate(undefined, { onSuccess: setState, onError: onErr })}>
              {t("channels.admin.bridgeLogout")}
            </Button>
          </div>
          <Button type="button" size="sm" variant="ghost" className="self-start" onClick={() => onAck(false)}>
            {t("channels.admin.bridgeAckWithdraw")}
          </Button>
          {state ? (
            <p role="status" className="type-footnote text-label-2">
              {state.logged_in ? t("channels.admin.bridgeLoggedIn") : state.reachable === false ? t("channels.admin.bridgeUnreachable") : t("channels.admin.bridgeLoggedOut")}
            </p>
          ) : null}
          {/* eslint-disable-next-line @next/next/no-img-element -- a data: URL from the bridge, shown once to the administrator */}
          {qr ? <img src={qr} alt={t("channels.admin.bridgeQrAlt")} className="size-56 rounded-lg bg-white p-2" /> : null}
        </>
      )}
      {error ? <Alert tone="error">{error}</Alert> : null}
    </section>
  );
}

function DepartmentTargets({ kind }: { kind: "teams" | "slack" }) {
  const { t, locale } = useI18n();
  const q = useChannelDepartments(kind);
  const departments = useDepartments();
  const [dept, setDept] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const put = useChannelMutation((v: { id: number; url: string }) => channels.putDepartment(kind, v.id, v.url), [channelKeys.departments(kind), channelKeys.admin]);
  const del = useChannelMutation((id: number) => channels.deleteDepartment(kind, id), [channelKeys.departments(kind), channelKeys.admin]);
  return (
    <section className="flex flex-col gap-3" aria-labelledby={`targets-${kind}`} data-testid={`targets-${kind}`}>
      <h3 id={`targets-${kind}`} className="type-headline text-label-1">
        {t("channels.admin.targets")}
      </h3>
      <p className="type-footnote text-label-2">{kind === "teams" ? t("channels.admin.targetsTeams") : t("channels.admin.targetsSlack")}</p>
      {(q.data ?? []).length ? (
        <ul className="flex flex-col">
          {(q.data ?? []).map((d) => (
            <li key={d.id} className="flex items-center gap-3 py-1.5 hairline-b">
              <span className="min-w-0 flex-1 type-callout text-label-1">{d.department ?? `#${d.department_id}`}</span>
              <span className="font-mono type-footnote text-label-2">{d.host ?? "—"}</span>
              <IconButton label={t("channels.admin.targetDelete")} size="sm" onClick={() => del.mutate(d.department_id, { onError: (e) => toast.error(apiProblem(e, locale).text ?? t("channels.admin.saveFailed")) })}>
                <Trash2 />
              </IconButton>
            </li>
          ))}
        </ul>
      ) : (
        <p className="type-footnote text-label-3">{t("channels.admin.targetsNone")}</p>
      )}
      <form
        className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_auto] sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          if (!dept || !url.trim()) return;
          put.mutate(
            { id: Number(dept), url: url.trim() },
            { onSuccess: () => (setUrl(""), toast.success(t("channels.admin.saved"))), onError: (err) => setError(apiProblem(err, locale).text ?? t("channels.admin.saveFailed")) },
          );
        }}
      >
        <Field label={t("channels.admin.targetDept")} htmlFor={`target-dept-${kind}`}>
          <SelectField id={`target-dept-${kind}`} value={dept} onChange={(e) => setDept(e.target.value)}>
            <option value="">—</option>
            {(departments.data ?? []).map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </SelectField>
        </Field>
        <Field label={t("channels.admin.targetUrl")} htmlFor={`target-url-${kind}`}>
          <Input id={`target-url-${kind}`} type="password" autoComplete="off" spellCheck={false} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" />
        </Field>
        <BusyButton type="submit" variant="outline" busy={put.isPending} busyLabel={t("busy.saving")} disabled={!dept || !url.trim()}>
          <Plus aria-hidden />
          {t("channels.admin.targetAdd")}
        </BusyButton>
      </form>
      {error ? <Alert tone="error">{error}</Alert> : null}
    </section>
  );
}

const DELIVERY_STATUSES = ["PENDING", "RUNNING", "SENT", "FAILED", "SKIPPED"] as const;

function DeliveriesLog({ kinds }: { kinds: string[] }) {
  const { t, locale } = useI18n();
  const fmt = useBookingFormat();
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("");
  const q = useDeliveries({ kind: kind || undefined, status: status || undefined, limit: 50 });
  return (
    <Card data-testid="channel-deliveries">
      <CardHeader>
        <CardTitle>{t("channels.admin.deliveries")}</CardTitle>
        <CardDescription>{t("channels.admin.deliveriesLead")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap gap-2">
          <SelectField aria-label={t("channels.admin.deliveriesKind")} className="w-auto min-w-44" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">{t("channels.admin.deliveriesKind")}</option>
            {kinds.map((k) => (
              <option key={k} value={k}>
                {t(`channels.kind.${k}` as "channels.kind.webpush")}
              </option>
            ))}
          </SelectField>
          <SelectField aria-label={t("channels.admin.deliveriesStatus")} className="w-auto min-w-40" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">{t("channels.admin.deliveriesStatus")}</option>
            {DELIVERY_STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`channels.admin.delivery.${s}`)}
              </option>
            ))}
          </SelectField>
        </div>
        {q.isError ? <Alert tone="error">{apiProblem(q.error, locale).text ?? t("channels.admin.loadError")}</Alert> : null}
        {q.data && !q.data.length ? <p className="type-footnote text-label-3">{t("channels.admin.deliveriesNone")}</p> : null}
        {q.data?.length ? (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("channels.admin.colTime")}</TableHead>
                  <TableHead>{t("channels.admin.colChannel")}</TableHead>
                  <TableHead className="hidden md:table-cell">{t("channels.admin.colEvent")}</TableHead>
                  <TableHead>{t("channels.admin.colStatus")}</TableHead>
                  <TableHead className="hidden md:table-cell">{t("channels.admin.colError")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {q.data.map((d) => (
                  <TableRow key={d.id}>
                    <TableCell className="tabular-nums text-label-2">{fmt.dateTime(d.created_at) || "—"}</TableCell>
                    <TableCell>{t(`channels.kind.${d.kind}` as "channels.kind.webpush")}</TableCell>
                    <TableCell className="hidden font-mono type-footnote md:table-cell">{d.event}</TableCell>
                    <TableCell>
                      <StatusDot tone={d.status === "SENT" ? "feasible" : d.status === "FAILED" ? "infeasible" : d.status === "SKIPPED" ? "neutral" : "pending"}>
                        {t(`channels.admin.delivery.${d.status}` as "channels.admin.delivery.SENT")}
                        {d.attempts > 1 ? ` · ${d.attempts}` : ""}
                      </StatusDot>
                    </TableCell>
                    <TableCell className="hidden max-w-80 truncate type-footnote text-label-2 md:table-cell" title={d.last_error ?? undefined}>
                      {d.last_error ?? (d.next_attempt_at && d.status !== "SENT" ? t("channels.admin.nextAttempt", { at: fmt.dateTime(d.next_attempt_at) }) : "—")}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
