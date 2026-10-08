"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Sparkles, Undo2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { roomLabel } from "@/components/runs/diagnosis-format";
import { DiffTable, type DiffTableRow } from "@/components/ui/beautifului/diff-table";
import { PromptComposer } from "@/components/ui/beautifului/prompt-composer";
import { Button } from "@/components/ui/button";
import { useChat, useSendChat, useSettings, useUndoProposal } from "@/lib/api/hooks";
import type { ChatMessage, ChatProposal } from "@/lib/api/schemas";
import { applyProposalSubset, usePermissions } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";
import { useReduce } from "@/lib/motion";
import { PERIODS, dayName } from "@/lib/time";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";
import { pairLang } from "@/lib/i18n";

const STARTERS = { tr: ["BME 419'u A 204'e taşı", "MAT 112'yi salı öğleden sonraya al", "İkinci öğretim B blokta kalsın"], en: ["Move BME 419 to A 204", "Move MAT 112 to Tuesday afternoon", "Keep evening classes in building B"] };

type Slot = ChatProposal["moves"][number]["from"];

function useSlot() {
  const { locale } = useI18n();
  return (s: Slot) => `${roomLabel(s.room)} · ${dayName(s.day, locale, "short")} ${PERIODS[s.start_period - 1]?.start ?? ""}–${PERIODS[s.end_period - 1]?.end ?? ""}`;
}

/** Proposed changes as a beautifului DiffTable: each move is a row the planner can untick before applying. */
export function ProposalDiff({ runId, proposal }: { runId: number; proposal: ChatProposal }) {
  const { t, n } = useI18n();
  const router = useRouter();
  const qc = useQueryClient();
  const undo = useUndoProposal(runId);
  const slot = useSlot();
  const setHighlight = useUiStore((s) => s.setHighlightAssignmentIds);
  const setChanged = useUiStore((s) => s.setChangedAssignmentIds);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);
  const ids = proposal.moves.map((m) => m.assignment_id);
  const rows: DiffTableRow[] = proposal.moves.map((m) => ({
    key: String(m.assignment_id),
    change: "added",
    cells: [m.label, <span key="from" className="line-through decoration-label-3">{slot(m.from)}</span>, slot(m.to)],
    label: t("glass.chat.moveLabel", { label: m.label, from: slot(m.from), to: slot(m.to) }),
  }));
  useEffect(() => {
    // stable ids for the recording pipeline (the vendored DiffTable has no test-id props)
    wrapRef.current?.querySelector<HTMLElement>('[data-slot="diff-table"] [data-slot="button"]')?.setAttribute("data-testid", "chat-apply");
  });
  const apply = async (keys: string[]) => {
    setBusy(true);
    try {
      const res = await applyProposalSubset(runId, proposal.id, keys.map(Number), ids);
      await qc.invalidateQueries({ queryKey: ["chat", runId] });
      void qc.invalidateQueries({ queryKey: ["runs"] });
      void qc.invalidateQueries({ queryKey: ["grid", runId] });
      setChanged(keys.map(Number));
      setTimeout(() => setChanged([]), 4000);
      toast.success(t("glass.chat.applied", { n: n(keys.length) }), {
        action: { label: t("common.undo"), onClick: () => void undo.mutateAsync().then(() => { toast(t("chat.undoneToast")); router.push(`/runs/${runId}`); }) },
        duration: 8000,
      });
      if (res.child_run_id) router.push(`/runs/${res.child_run_id}`);
    } catch {
      toast.error(t("glass.chat.applyFailed"));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div ref={wrapRef} className="mt-2 w-full space-y-2" data-testid="proposal-card" onMouseEnter={() => setHighlight(ids)} onMouseLeave={() => setHighlight([])} aria-busy={busy}>
      {rows.length ? (
        <DiffTable
          // inside the glass chat panel: a well, not a second glass (G2 / A8)
          className="![background:var(--fill-3)] ![backdrop-filter:none] ![-webkit-backdrop-filter:none] !shadow-[inset_0_0_0_1px_var(--hairline)]"
          title={proposal.summary || t("chat.proposal")}
          columns={[
            { key: "class", label: t("glass.chat.colClass"), width: "28%" },
            { key: "from", label: t("glass.chat.colFrom") },
            { key: "to", label: t("glass.chat.colTo") },
          ]}
          rows={rows}
          applied={proposal.applied}
          onApply={(keys) => void apply(keys)}
          labels={{
            hint: t("glass.chat.diffHint"),
            summary: (_r, a) => t("glass.chat.diffSummary", { n: n(a) }),
            apply: (c) => t("glass.chat.applyN", { n: n(c) }),
            applied: (c) => t("glass.chat.appliedN", { n: n(c) }),
          }}
        />
      ) : null}
      {proposal.constraints.length ? (
        <ul className="rounded-xl bg-fill-3 px-3 py-2 text-[12.5px] shadow-[inset_0_0_0_1px_var(--hairline)]">
          {proposal.constraints.map((c, i) => (
            <li key={i} className="py-0.5 text-label-1">
              {c.nl_text} <span className="text-label-3">· {c.hardness === "hard" ? t("glass.report.must") : t("glass.report.try")}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {proposal.notes.length ? (
        <ul className="space-y-0.5 px-1 text-[12px] text-label-3">
          {proposal.notes.map((note, i) => (
            <li key={i}>{note}</li>
          ))}
        </ul>
      ) : null}
      {proposal.applied ? (
        <Button size="sm" variant="ghost" onClick={() => void undo.mutateAsync().then(() => toast(t("chat.undoneToast")))} disabled={undo.isPending} data-testid="proposal-undo">
          <Undo2 /> {t("chat.undo")}
        </Button>
      ) : !rows.length && proposal.constraints.length ? (
        <Button size="sm" onClick={() => void apply([])} disabled={busy} data-testid="chat-apply">
          {t("glass.chat.applyRules")}
        </Button>
      ) : null}
    </div>
  );
}

function Message({ m, runId }: { m: ChatMessage; runId: number }) {
  const mine = m.role === "user";
  return (
    <div className={cn("flex flex-col gap-1", mine ? "items-end" : "items-start")}>
      <div className={cn("max-w-[92%] text-[13.5px] leading-5 whitespace-pre-wrap", mine ? "rounded-2xl rounded-br-md bg-fill-1 px-3 py-2 text-label-1" : m.role === "system" ? "text-label-3 italic" : "text-label-1")}>{m.content}</div>
      {m.proposal ? <ProposalDiff runId={runId} proposal={m.proposal} /> : null}
    </div>
  );
}

/** "Thinking" label: one looping indicator of real ongoing work (pattern §17); static under reduced motion. */
function Thinking() {
  const { t } = useI18n();
  const reduce = useReduce();
  const [secs, setSecs] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <p role="status" className={cn("text-[13px] text-label-2", !reduce && "animate-pulse")}>
      {t("chat.thinking")}
      {secs >= 5 ? <span className="ml-1 text-label-3 tabular-nums">{t("glass.chat.elapsed", { s: secs })}</span> : null}
    </p>
  );
}

export function ChatPanel({ runId, className }: { runId: number; className?: string }) {
  const { t, locale } = useI18n();
  const chat = useChat(runId);
  const send = useSendChat(runId, locale === "en" ? "en" : "tr");
  const settings = useSettings();
  const { can } = usePermissions();
  const listRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLDivElement>(null);
  const messages = chat.data?.messages ?? [];
  const noKey = settings.data ? !settings.data.anthropic_api_key_masked : false;
  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight });
  }, [messages.length, send.isPending]);
  useEffect(() => {
    const root = composerRef.current;
    root?.querySelector("textarea")?.setAttribute("data-testid", "chat-input");
    root?.querySelector(`button[aria-label="${CSS.escape(t("chat.send"))}"]`)?.setAttribute("data-testid", "chat-send");
  });
  const submit = async (msg: string) => {
    try {
      await send.mutateAsync(msg);
    } catch {
      toast.error(noKey ? t("glass.chat.noKeyToast") : t("glass.chat.sendFailed"));
    }
  };
  return (
    <section className={cn("glass-regular flex min-h-0 flex-col overflow-hidden rounded-2xl", className)} data-glass="regular" data-testid="chat-panel" aria-label={t("chat.title")}>
      <div className="flex items-center gap-2 px-4 py-3 hairline-b">
        <Sparkles className="size-4 text-label-2" aria-hidden />
        <h2 className="type-headline text-label-1">{t("chat.title")}</h2>
        {!noKey && settings.data ? <span className="ml-auto truncate text-[11px] text-label-3">{settings.data.anthropic_model}</span> : null}
      </div>
      <div ref={listRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-3" aria-live="polite" aria-busy={send.isPending}>
        {messages.length === 0 ? <p className="text-[13px] text-label-2">{t("chat.empty")}</p> : null}
        {messages.map((m) => (
          <Message key={m.id} m={m} runId={runId} />
        ))}
        {send.isPending ? <Thinking /> : null}
      </div>
      <div ref={composerRef} className="p-3 hairline-t">
        {noKey ? (
          <p className="mb-2 text-[12.5px] text-status-warning-fg">
            {t("glass.chat.noKey")}{" "}
            {can(["planning.admin", "setup.settings"]) ? (
              <Link href="/settings?tab=ai" className="font-medium text-tint-text hover:underline">
                {t("glass.chat.openSettings")}
              </Link>
            ) : (
              t("glass.chat.askAdmin")
            )}
          </p>
        ) : null}
        <PromptComposer
          className="[&_.glass-thick]:![backdrop-filter:none] [&_.glass-thick]:![-webkit-backdrop-filter:none]"
          onSend={(text) => void submit(text)}
          disabled={noKey || send.isPending}
          placeholder={t("chat.placeholder")}
          label={t("chat.placeholder")}
          sendLabel={t("chat.send")}
          suggestions={messages.length === 0 && !noKey ? STARTERS[pairLang(locale)] : undefined}
        />
      </div>
    </section>
  );
}
