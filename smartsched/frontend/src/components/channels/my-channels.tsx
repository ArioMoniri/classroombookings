"use client";
/**
 * Profile › Bağlı kanallar: where notifications reach this person besides e-mail. Lists the own linked
 * addresses (status dot + word, "Test gönder", "Kaldır") and the channels the administrator switched on:
 * - Web Push: "Bu cihaza bildirim gönder" registers /push-sw.js (narrow scope) and subscribes this browser;
 * - Telegram: a one-time deep link, then the card polls `POST /me/channels/telegram/check` while it is open;
 * - SMS / WhatsApp: phone (+ the institution-naming opt-in for WhatsApp) → a 6-digit code → verify;
 * - Teams / Slack: department channels, nothing to link (shown as information).
 * Linking is always the person's own opt-in; unlinking deletes the address.
 */
import { BellRing, Check, Mail, MessageCircle, Phone, Send, Trash2, Users } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useEffectEvent, useId, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/admin/kit";
import { Alert } from "@/components/ui/alert";
import { BusyButton } from "@/components/ui/busy-label";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { StatusDot } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { channelKeys, channelLabel, channels, useChannelMutation, useMyChannels, type AvailableChannel, type LinkedChannel } from "@/lib/api/channels";
import { apiProblem } from "@/lib/api/identity";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { deviceLabel, notificationsBlocked, pushSupport, PushError, subscribeThisBrowser } from "./push";

const ICON: Record<string, ReactNode> = {
  webpush: <BellRing aria-hidden />,
  telegram: <Send aria-hidden />,
  whatsapp: <MessageCircle aria-hidden />,
  sms: <Phone aria-hidden />,
  teams: <Users aria-hidden />,
  slack: <Users aria-hidden />,
};

/** Telegram link polling: every 3 s while the card waits, for at most 10 minutes (the code's lifetime). */
const POLL_MS = 3000;
const POLL_MAX_MS = 10 * 60_000;

export function MyChannels({ email, compact = false }: { email?: string | null; compact?: boolean }) {
  const { t, locale } = useI18n();
  const q = useMyChannels();
  const [removing, setRemoving] = useState<LinkedChannel | null>(null);
  const unlink = useChannelMutation((id: number) => channels.unlink(id), [channelKeys.mine]);
  const test = useChannelMutation((id: number) => channels.test(id));
  if (q.isLoading) return <p className="type-callout text-label-2">{t("channels.me.loading")}</p>;
  if (q.isError) return <Alert tone="error">{apiProblem(q.error, locale).text ?? t("channels.me.loadError")}</Alert>;
  const data = q.data ?? { available: [], linked: [] };
  const labelOf = (kind: string) => {
    const a = data.available.find((x) => x.kind === kind);
    return a ? channelLabel(a, locale) : t(`channels.kind.${kind}` as "channels.kind.webpush");
  };
  const linkable = data.available.filter((a) => a.link !== "department");
  const departmental = data.available.filter((a) => a.link === "department");
  return (
    <div className="flex flex-col gap-4" data-testid="my-channels">
      <ul className="flex flex-col">
        {!compact ? (
          <li className="flex min-h-12 items-center gap-3 py-2 hairline-b">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-fill-2 text-label-2 [&_svg]:size-4">
              <Mail aria-hidden />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block type-callout font-medium text-label-1">{t("channels.me.email")}</span>
              <span className="block truncate type-footnote text-label-2">{email || t("channels.me.noEmail")}</span>
            </span>
            <StatusDot tone={email ? "feasible" : "neutral"}>{email ? t("channels.me.active") : t("channels.me.off")}</StatusDot>
          </li>
        ) : null}
        {data.linked.map((c) => (
          <li key={c.id} className="flex flex-wrap items-center gap-3 py-2 hairline-b" data-testid={`linked-${c.kind}`}>
            <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-fill-2 text-label-2 [&_svg]:size-4">{ICON[c.kind] ?? <BellRing aria-hidden />}</span>
            <span className="min-w-0 flex-1">
              <span className="block type-callout font-medium text-label-1">{labelOf(c.kind)}</span>
              <span className="block truncate type-footnote text-label-2">{[c.label, c.display_hint].filter(Boolean).join(" · ") || "—"}</span>
            </span>
            <StatusDot tone={c.status === "active" ? "feasible" : "warning"}>{c.status === "active" ? t("channels.me.active") : c.status === "blocked" ? t("channels.me.blocked") : t("channels.me.failed")}</StatusDot>
            <span className="flex gap-1">
              <Button
                variant="ghost"
                size="sm"
                disabled={c.status !== "active"}
                onClick={() =>
                  test.mutate(c.id, {
                    onSuccess: () => toast.success(t("channels.me.testQueued")),
                    onError: (e) => toast.error(apiProblem(e, locale).text ?? t("channels.me.testFailed")),
                  })
                }
                data-testid={`channel-test-${c.id}`}
              >
                {t("channels.me.test")}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setRemoving(c)} aria-label={t("channels.me.removeNamed", { name: labelOf(c.kind) })} data-testid={`channel-remove-${c.id}`}>
                <Trash2 aria-hidden />
                <span className="max-sm:sr-only">{t("channels.me.remove")}</span>
              </Button>
            </span>
          </li>
        ))}
      </ul>
      {linkable.length ? (
        <div className="flex flex-col gap-3">
          {linkable.map((a) => (
            <ChannelLinker key={a.kind} channel={a} linked={data.linked.filter((l) => l.kind === a.kind)} />
          ))}
        </div>
      ) : !compact && !data.linked.length ? (
        <p className="type-footnote text-label-3" data-testid="channels-none">{t("channels.me.noneAvailable")}</p>
      ) : null}
      {departmental.length && !compact ? (
        <ul className="flex flex-col gap-1 type-footnote text-label-2">
          {departmental.map((a) => (
            <li key={a.kind}>{a.department_target ? t("channels.me.department", { channel: channelLabel(a, locale) }) : t("channels.me.departmentNone", { channel: channelLabel(a, locale) })}</li>
          ))}
        </ul>
      ) : null}
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(o) => !o && setRemoving(null)}
        title={t("channels.me.removeTitle", { name: removing ? labelOf(removing.kind) : "" })}
        description={t("channels.me.removeBody")}
        confirmLabel={t("channels.me.remove")}
        destructive
        busy={unlink.isPending}
        onConfirm={() =>
          removing &&
          unlink.mutate(removing.id, {
            onSuccess: () => {
              toast.success(t("channels.me.removed"));
              setRemoving(null);
            },
            onError: (e) => toast.error(apiProblem(e, locale).text ?? t("channels.me.removeFailed")),
          })
        }
      />
    </div>
  );
}

function LinkerFrame({ channel, open, onOpen, children, done }: { channel: AvailableChannel; open: boolean; onOpen: () => void; children: ReactNode; done?: boolean }) {
  const { t, locale } = useI18n();
  return (
    <div className={cn("rounded-xl bg-fill-3 px-3 py-2.5 edge-hairline")} data-testid={`linker-${channel.kind}`}>
      <div className="flex flex-wrap items-center gap-3">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-fill-2 text-label-2 [&_svg]:size-4">{ICON[channel.kind] ?? <BellRing aria-hidden />}</span>
        <span className="min-w-0 flex-1 type-callout font-medium text-label-1">{channelLabel(channel, locale)}</span>
        {!open ? (
          <Button variant="outline" size="sm" onClick={onOpen} data-testid={`channel-link-${channel.kind}`}>
            {done ? <Check aria-hidden /> : null}
            {done ? t("channels.me.linkAnother") : t("channels.me.link")}
          </Button>
        ) : null}
      </div>
      {open ? <div className="mt-3 flex flex-col gap-3">{children}</div> : null}
    </div>
  );
}

function ChannelLinker({ channel, linked }: { channel: AvailableChannel; linked: LinkedChannel[] }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const done = linked.some((l) => l.status === "active");
  const close = () => setOpen(false);
  const body =
    channel.kind === "webpush" ? (
      <PushLinker channel={channel} onDone={close} />
    ) : channel.kind === "telegram" ? (
      <TelegramLinker onDone={close} />
    ) : channel.kind === "sms" || channel.kind === "whatsapp" ? (
      <PhoneLinker kind={channel.kind} channel={channel} onDone={close} />
    ) : null;
  if (!body) return null;
  return (
    <LinkerFrame channel={channel} open={open} onOpen={() => setOpen(true)} done={done}>
      {body}
      {/* the flows keep no state the person needs: closing is always safe */}
      <Button variant="ghost" size="sm" className="self-start" onClick={close}>
        {t("channels.me.cancel")}
      </Button>
    </LinkerFrame>
  );
}

function PushLinker({ channel, onDone }: { channel: AvailableChannel; onDone: () => void }) {
  const { t, locale } = useI18n();
  const [error, setError] = useState<string | null>(null);
  const [support, setSupport] = useState(() => pushSupport());
  useEffect(() => {
    if (support !== "ok") return;
    let live = true;
    void notificationsBlocked().then((blocked) => {
      if (live && blocked) setSupport("denied");
    });
    return () => {
      live = false;
    };
  }, [support]);
  const add = useChannelMutation(async () => {
    if (!channel.vapid_public_key) throw new PushError("unsupported");
    const sub = await subscribeThisBrowser(channel.vapid_public_key);
    return channels.pushSubscribe(sub, deviceLabel());
  }, [channelKeys.mine]);
  if (support === "ios-install") return <Alert tone="info">{t("channels.me.push.iosInstall")}</Alert>;
  if (support === "unsupported") return <Alert tone="neutral">{t("channels.me.push.unsupported")}</Alert>;
  if (support === "denied") return <Alert tone="warning">{t("channels.me.push.denied")}</Alert>;
  return (
    <>
      <p className="type-footnote text-label-2">{t("channels.me.push.lead")}</p>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <BusyButton
        busy={add.isPending}
        busyLabel={t("busy.working")}
        className="self-start"
        onClick={() => {
          setError(null);
          add.mutate(undefined, {
            onSuccess: () => {
              toast.success(t("channels.me.push.done"));
              onDone();
            },
            onError: (e) => setError(e instanceof PushError ? t(`channels.me.push.${e.reason}`) : (apiProblem(e, locale).text ?? t("channels.me.push.failed"))),
          });
        }}
        data-testid="push-subscribe"
      >
        {t("channels.me.push.action")}
      </BusyButton>
    </>
  );
}

function TelegramLinker({ onDone }: { onDone: () => void }) {
  const { t, locale } = useI18n();
  const qc = useQueryClient();
  const [link, setLink] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const make = useChannelMutation(() => channels.telegramLink());
  // effect events: the poll loop always sees the latest callbacks without restarting
  const linked = useEffectEvent(() => {
    void qc.invalidateQueries({ queryKey: channelKeys.mine });
    toast.success(t("channels.me.telegram.done"));
    onDone();
  });

  // poll while the deep link is shown (webhook mode answers from the DB; poll mode asks Telegram), at most 10 min
  useEffect(() => {
    if (!link) return;
    const started = Date.now();
    let stop = false;
    let timer = 0;
    const tick = async () => {
      if (stop) return;
      if (Date.now() - started > POLL_MAX_MS) return setLink(null);
      try {
        const out = await channels.telegramCheck();
        if (out.linked && !stop) return linked();
      } catch {
        /* keep polling: a transient error is not the person's problem */
      }
      if (!stop) timer = window.setTimeout(() => void tick(), POLL_MS);
    };
    timer = window.setTimeout(() => void tick(), POLL_MS);
    return () => {
      stop = true;
      window.clearTimeout(timer);
    };
  }, [link]);

  return (
    <>
      <p className="type-footnote text-label-2">{t("channels.me.telegram.lead")}</p>
      {error ? <Alert tone="error">{error}</Alert> : null}
      {!link ? (
        <BusyButton
          busy={make.isPending}
          busyLabel={t("busy.working")}
          className="self-start"
          onClick={() => {
            setError(null);
            make.mutate(undefined, { onSuccess: (o) => setLink(o.deep_link), onError: (e) => setError(apiProblem(e, locale).text ?? t("channels.me.telegram.failed")) });
          }}
          data-testid="telegram-start"
        >
          {t("channels.me.telegram.action")}
        </BusyButton>
      ) : (
        <>
          <a href={link} target="_blank" rel="noreferrer" className="inline-flex min-h-11 items-center gap-2 self-start rounded-full bg-tint px-4 type-callout font-medium text-tint-foreground outline-hidden focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solid focus-visible:outline-(--focus)" data-testid="telegram-deeplink">
            <Send className="size-4" aria-hidden />
            {t("channels.me.telegram.open")}
          </a>
          <p role="status" className="type-footnote text-label-2">
            {t("channels.me.telegram.waiting")}
          </p>
        </>
      )}
    </>
  );
}

function PhoneLinker({ kind, channel, onDone }: { kind: "sms" | "whatsapp"; channel: AvailableChannel; onDone: () => void }) {
  const { t, locale } = useI18n();
  const ids = { phone: useId(), code: useId(), consent: useId() };
  const [phone, setPhone] = useState("");
  const [consent, setConsent] = useState(false);
  const [code, setCode] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const send = useChannelMutation(() => channels.phoneLink(kind, phone, consent));
  const verify = useChannelMutation(() => channels.phoneVerify(kind, code), [channelKeys.mine]);
  const optIn = locale === "tr" ? channel.opt_in_tr : channel.opt_in_en;
  if (!sentTo) {
    return (
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          if (kind === "whatsapp" && !consent) return setError(t("channels.me.phone.needConsent"));
          send.mutate(undefined, { onSuccess: (o) => setSentTo(o.display_hint ?? phone), onError: (err) => setError(apiProblem(err, locale).text ?? t("channels.me.phone.failed")) });
        }}
      >
        <div className="flex flex-col gap-1.5">
          <label htmlFor={ids.phone} className="type-footnote font-medium text-label-2">
            {t("channels.me.phone.label")}
          </label>
          <Input id={ids.phone} type="tel" inputMode="tel" autoComplete="tel" placeholder="0532 111 22 33" value={phone} onChange={(e) => setPhone(e.target.value)} className="max-w-[260px]" data-testid={`${kind}-phone`} />
        </div>
        {kind === "whatsapp" && optIn ? (
          <label htmlFor={ids.consent} className="flex items-start gap-2 type-footnote text-label-1">
            <Checkbox id={ids.consent} checked={consent} onCheckedChange={(v) => setConsent(v === true)} className="mt-0.5" data-testid="whatsapp-consent" />
            <span>{optIn}</span>
          </label>
        ) : null}
        {error ? <Alert tone="error">{error}</Alert> : null}
        <BusyButton type="submit" busy={send.isPending} busyLabel={t("busy.working")} className="self-start" disabled={!phone.trim()} data-testid={`${kind}-send-code`}>
          {t("channels.me.phone.send")}
        </BusyButton>
      </form>
    );
  }
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        verify.mutate(undefined, {
          onSuccess: () => {
            toast.success(t("channels.me.phone.done"));
            onDone();
          },
          onError: (err) => setError(apiProblem(err, locale).text ?? t("channels.me.phone.failed")),
        });
      }}
    >
      <p role="status" className="type-footnote text-label-2">
        {t("channels.me.phone.sent", { to: sentTo })}
      </p>
      <div className="flex flex-col gap-1.5">
        <label htmlFor={ids.code} className="type-footnote font-medium text-label-2">
          {t("channels.me.phone.code")}
        </label>
        <Input id={ids.code} inputMode="numeric" autoComplete="one-time-code" maxLength={12} value={code} onChange={(e) => setCode(e.target.value)} className="max-w-[160px] font-mono tracking-widest" data-testid={`${kind}-code`} />
      </div>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <div className="flex flex-wrap gap-2">
        <BusyButton type="submit" busy={verify.isPending} busyLabel={t("busy.checking")} disabled={!code.trim()} data-testid={`${kind}-verify`}>
          {t("channels.me.phone.verify")}
        </BusyButton>
        <Button type="button" variant="ghost" onClick={() => (setSentTo(null), setCode(""))}>
          {t("channels.me.phone.again")}
        </Button>
      </div>
    </form>
  );
}
