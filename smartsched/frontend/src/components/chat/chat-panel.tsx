"use client";

import { Loader2, Send, Sparkles, Undo2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useApplyProposal, useChat, useSendChat, useSettings, useUndoProposal } from "@/lib/api/hooks";
import type { ChatMessage, ChatProposal } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { dayName, periodRangeLabel } from "@/lib/time";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";

const STARTERS = ["BME 419'u A 204'e taşı", "Move MAT 112 to C 301 on Tuesday", "İkinci öğretim B blokta kalsın"];

function ProposalCard({ runId, proposal }: { runId: number; proposal: ChatProposal }) {
  const { t, locale } = useI18n();
  const router = useRouter();
  const apply = useApplyProposal(runId);
  const undo = useUndoProposal(runId);
  const setHighlight = useUiStore((s) => s.setHighlightAssignmentIds);
  const setChanged = useUiStore((s) => s.setChangedAssignmentIds);
  const ids = proposal.moves.map((m) => m.assignment_id);
  const onApply = async () => {
    let res;
    try {
      res = await apply.mutateAsync(proposal.id);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
      return;
    }
    setChanged(ids);
    setTimeout(() => setChanged([]), 4000);
    // the result is a child run; undo re-publishes this (parent) run
    toast.success(t("chat.appliedToast"), {
      description: res.rejected.length ? `${res.rejected.length} ✕` : undefined,
      action: { label: t("common.undo"), onClick: () => void undo.mutateAsync().then(() => { toast(t("chat.undoneToast")); router.push(`/runs/${runId}`); }) },
      duration: 8000,
    });
    if (res.child_run_id) router.push(`/runs/${res.child_run_id}`);
  };
  return (
    <div className={cn("mt-2 rounded-lg border bg-card text-sm", proposal.applied && "opacity-80")} data-testid="proposal-card" onMouseEnter={() => setHighlight(ids)} onMouseLeave={() => setHighlight([])}>
      <div className="flex items-center gap-2 border-b px-3 py-2">
        <Sparkles className="size-4 text-primary" aria-hidden />
        <span className="font-medium">{t("chat.proposal")}</span>
        {proposal.moves.length ? <Badge variant="secondary">{proposal.moves.length} {t("chat.moves").toLocaleLowerCase(locale)}</Badge> : null}
        {proposal.constraints.length ? <Badge variant="secondary">{proposal.constraints.length} {t("chat.constraints").toLocaleLowerCase(locale)}</Badge> : null}
        {proposal.applied ? <Badge variant="outline" className="ml-auto">{t("common.applied")}</Badge> : null}
      </div>
      {proposal.moves.length ? (
        <table className="w-full text-xs">
          <thead className="sr-only"><tr><th scope="col">Event</th><th scope="col">From</th><th scope="col">To</th></tr></thead>
          <tbody>
            {proposal.moves.map((m) => (
              <tr key={m.assignment_id} className="border-b last:border-0" data-assignment-id={m.assignment_id}>
                <td className="px-3 py-1.5 font-mono font-medium">{m.label}</td>
                <td className="px-2 py-1.5 text-muted-foreground line-through">{m.from.room} · {dayName(m.from.day, locale, "short")} {periodRangeLabel(m.from.start_period, m.from.end_period)}</td>
                <td className="px-2 py-1.5 text-primary">→ {m.to.room} · {dayName(m.to.day, locale, "short")} {periodRangeLabel(m.to.start_period, m.to.end_period)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {proposal.notes.length ? (
        <ul className="space-y-0.5 px-3 py-2 text-xs text-muted-foreground">{proposal.notes.map((n, i) => <li key={i}>· {n}</li>)}</ul>
      ) : null}
      {proposal.constraints.length ? (
        <ul className="space-y-1 px-3 py-2 text-xs">
          {proposal.constraints.map((c, i) => (
            <li key={i} className="flex flex-wrap items-center gap-1.5"><Badge variant={c.hardness === "hard" ? "default" : "secondary"}>{c.op} · {c.hardness}</Badge><span className="font-mono">{c.kind}</span><span className="text-muted-foreground">“{c.nl_text}”</span></li>
          ))}
        </ul>
      ) : null}
      <div className="flex gap-2 border-t px-3 py-2">
        {!proposal.applied ? (
          <Button size="sm" onClick={() => void onApply()} disabled={apply.isPending} aria-label={`${t("chat.apply")} (${proposal.moves.length + proposal.constraints.length})`} data-testid="proposal-apply">{apply.isPending ? <Loader2 className="animate-spin" /> : null} {t("chat.apply")}</Button>
        ) : (
          <Button size="sm" variant="outline" onClick={() => void undo.mutateAsync().then(() => toast(t("chat.undoneToast")))} disabled={undo.isPending} data-testid="proposal-undo"><Undo2 /> {t("chat.undo")}</Button>
        )}
      </div>
    </div>
  );
}

function Message({ m, runId }: { m: ChatMessage; runId: number }) {
  const { t } = useI18n();
  const mine = m.role === "user";
  return (
    <div className={cn("flex flex-col", mine ? "items-end" : "items-start")}>
      <span className="mb-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">{mine ? t("chat.you") : m.role === "system" ? "system" : t("chat.assistant")}</span>
      <div className={cn("max-w-[92%] rounded-lg px-3 py-2 text-sm", mine ? "bg-primary text-primary-foreground" : m.role === "system" ? "bg-muted text-muted-foreground italic" : "bg-muted")}>{m.content}</div>
      {m.proposal ? <div className="w-full"><ProposalCard runId={runId} proposal={m.proposal} /></div> : null}
    </div>
  );
}

export function ChatPanel({ runId, className }: { runId: number; className?: string }) {
  const { t, locale } = useI18n();
  const chat = useChat(runId);
  const send = useSendChat(runId, locale === "en" ? "en" : "tr");
  const settings = useSettings();
  const [text, setText] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const messages = chat.data?.messages ?? [];
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages.length, send.isPending]);
  const submit = async () => {
    const msg = text.trim();
    if (!msg) return;
    setText("");
    try {
      await send.mutateAsync(msg);
    } catch (e) {
      setText(msg); // keep the planner's text (e.g. 409: no API key configured)
      toast.error(e instanceof Error ? e.message : String(e));
    }
  };
  return (
    <div className={cn("flex min-h-0 flex-col rounded-xl border bg-card", className)} data-testid="chat-panel">
      <div className="flex items-center gap-2 border-b px-3 py-2 text-sm font-medium"><Sparkles className="size-4 text-primary" aria-hidden /> {t("chat.title")} <span className="ml-auto text-[11px] font-normal text-muted-foreground">{settings.data?.anthropic_model ?? ""}</span></div>
      <div ref={listRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3" aria-live="polite" aria-busy={send.isPending}>
        {messages.length === 0 ? <p className="text-sm text-muted-foreground">{t("chat.empty")}</p> : null}
        {messages.map((m) => <Message key={m.id} m={m} runId={runId} />)}
        {send.isPending ? <div className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="size-3.5 animate-spin" /> {t("chat.thinking")}</div> : null}
      </div>
      <div className="border-t p-2">
        <div className="mb-1.5 flex gap-1 overflow-x-auto">{STARTERS.map((s) => <button key={s} type="button" onClick={() => setText(s)} className="shrink-0 rounded-full border px-2 py-0.5 text-[11px] hover:bg-accent">{s}</button>)}</div>
        <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
          <Textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder={t("chat.placeholder")} onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); void submit(); } }} className="min-h-0 text-base sm:text-sm" aria-label={t("chat.placeholder")} data-testid="chat-input" />
          <Button type="submit" size="icon" aria-label={t("chat.send")} disabled={!text.trim() || send.isPending} data-testid="chat-send"><Send /></Button>
        </form>
        {settings.data && !settings.data.anthropic_api_key_masked ? <p className="mt-1 text-[11px] text-status-warning-fg">{t("chat.noKey")}</p> : null}
      </div>
    </div>
  );
}
