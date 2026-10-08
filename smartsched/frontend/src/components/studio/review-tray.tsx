"use client";

import { Check, Pencil, X } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useRef, useState, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import type { ProposedConstraint } from "@/lib/api/schemas";
import type { StudioMeta } from "@/lib/api/studio-schemas";
import { useI18n } from "@/lib/i18n/provider";
import { RuleCard, type Candidate } from "./rule-card";
import { allowedHardness, fallbackSentence, provenanceText, ruleTokens } from "./rule-helpers";
import { writeField } from "./rule-sentence";
import { asSource } from "./source-chip";
import { useStudioData } from "./studio-data";
import type { TrayItem } from "./studio-store";

type Entity = { type?: string; text?: string; resolved_id?: number | null; candidates?: { id?: number; label?: string }[] };

/** Choose one of an unresolved entity's candidates ("Did you mean A 205 or A 206?"). */
export function resolveCandidate(p: ProposedConstraint, entityIndex: number, id: number): ProposedConstraint {
  const entities = p.entities.map((e) => ({ ...e })) as Entity[];
  const ent = entities[entityIndex];
  if (!ent) return p;
  const label = ent.candidates?.find((c) => c.id === id)?.label ?? String(id);
  const params = { ...p.params };
  const add = (key: string, v: unknown) => {
    const cur = Array.isArray(params[key]) ? (params[key] as unknown[]) : [];
    params[key] = [...cur.filter((x) => x !== v), v];
  };
  switch (ent.type) {
    case "room":
      if (p.kind === "room_closed") params.room_id = id;
      else add("room_ids", id);
      break;
    case "program":
      params.programs = [label];
      break;
    case "course":
    case "event":
    case "section":
      add("event_ids", id);
      break;
    case "instructor":
      add("instructors", label);
      break;
    case "building":
      params.building = label;
      break;
    default:
      add(`${ent.type ?? "entity"}_ids`, id);
  }
  entities[entityIndex] = { ...ent, resolved_id: id, candidates: ent.candidates };
  const unresolved = entities.some((e) => (e.candidates?.length ?? 0) > 0 && (e.resolved_id === null || e.resolved_id === undefined));
  const issues = p.issues.filter((i) => !ent.text || !i.includes(ent.text));
  return { ...p, params, entities: entities as ProposedConstraint["entities"], issues, status: unresolved || issues.length ? "needs_review" : "ok", confidence: Math.max(p.confidence, 0.8) };
}

export function unresolvedCandidates(p: ProposedConstraint): { index: number; text: string; options: { id: number; label: string }[] }[] {
  return (p.entities as Entity[])
    .map((e, index) => ({ e, index }))
    .filter(({ e }) => (e.resolved_id === null || e.resolved_id === undefined) && (e.candidates?.length ?? 0) > 0)
    .map(({ e, index }) => ({ index, text: e.text ?? "?", options: (e.candidates ?? []).filter((c) => typeof c.id === "number").map((c) => ({ id: c.id as number, label: c.label ?? String(c.id) })) }));
}

/** One proposal in the tray: dashed AI card with Accept · Edit · Dismiss. */
export function ProposalCard({ item, meta, onAccept, onReject, onChange, onKeyDown, busy }: { item: Extract<TrayItem, { type: "rule" }>; meta: StudioMeta | undefined; onAccept: () => void; onReject: () => void; onChange: (p: ProposedConstraint) => void; onKeyDown?: (e: KeyboardEvent<HTMLDivElement>) => void; busy?: boolean }) {
  const { t, locale } = useI18n();
  const { sentence, advanced } = useStudioData();
  const [editing, setEditing] = useState(false);
  const p = item.proposal;
  const { template, tokens } = ruleTokens(meta, p.kind, p.params, sentence, editing);
  const candidates: Candidate[] = unresolvedCandidates(p).map((c) => ({ text: c.text, options: c.options, onPick: (id) => onChange(resolveCandidate(p, c.index, id)) }));
  const ready = p.status === "ok";
  return (
    <div tabIndex={-1} onKeyDown={onKeyDown} data-tray-key={item.key} className="rounded-[var(--radius-md)] outline-none focus-visible:ring-3 focus-visible:ring-ring/50" data-testid="tray-item" data-status={p.status}>
      <RuleCard
        domId={`tray-${item.key}`}
        testId="proposal-card"
        tokens={tokens}
        fallback={fallbackSentence(meta, p.kind, p.title ?? p.nl_text, locale)}
        nlText={p.nl_text || null}
        provenance={provenanceText(p.source_ref, t)}
        source={asSource(item.origin === "upload" ? "UPLOAD" : p.source === "UPLOAD" ? "UPLOAD" : "AI")}
        proposal
        hardness={p.hardness}
        weight={p.weight}
        allowed={allowedHardness(meta, p.kind)}
        scale={meta?.weight_scale}
        onHardness={editing ? (h) => onChange({ ...p, hardness: h }) : undefined}
        onWeight={editing ? (w) => onChange({ ...p, weight: w }) : undefined}
        onSlotChange={(name, value) => {
          const f = template?.fields.find((x) => x.name === name);
          if (f) onChange({ ...p, params: writeField(f, p.params, value, sentence) });
        }}
        candidates={candidates}
        issues={p.issues}
        advanced={advanced}
        kind={p.kind}
        params={p.params}
        actions={
          <>
            <Button size="sm" onClick={onAccept} disabled={busy || p.status === "rejected"} data-testid="tray-accept" aria-keyshortcuts="a">
              <Check aria-hidden /> {t("studio.tray.accept")}
            </Button>
            <Button size="sm" variant="outline" onClick={() => setEditing((v) => !v)} aria-pressed={editing} aria-keyshortcuts="e">
              <Pencil aria-hidden /> {t("common.edit")}
            </Button>
            <Button size="sm" variant="ghost" onClick={onReject} disabled={busy} data-testid="tray-reject" aria-keyshortcuts="r">
              <X aria-hidden /> {t("studio.tray.dismiss")}
            </Button>
            {!ready ? <span className="text-xs text-status-warning-fg">{t("studio.tray.needsLook")}</span> : null}
          </>
        }
      />
    </div>
  );
}

/** The review tray: "7 suggestions to review · Accept all ready (5)". needs_review can't be bulk-accepted. */
export function ReviewTray({ items, meta, onAccept, onReject, onUpdate }: { items: TrayItem[]; meta: StudioMeta | undefined; onAccept: (items: TrayItem[]) => Promise<unknown> | void; onReject: (keys: string[]) => void; onUpdate: (key: string, p: ProposedConstraint) => void }) {
  const { t } = useI18n();
  const reduce = useReducedMotion();
  const heading = useRef<HTMLHeadingElement>(null);
  const [busy, setBusy] = useState(false);
  const pending = items.filter((i): i is Extract<TrayItem, { type: "rule" }> => i.type === "rule" && i.state === "pending");
  const ready = pending.filter((i) => i.proposal.status === "ok");
  if (pending.length === 0) return null;

  const focusNext = (key: string) => {
    window.requestAnimationFrame(() => {
      const rest = pending.filter((i) => i.key !== key);
      const idx = pending.findIndex((i) => i.key === key);
      const next = rest[Math.min(idx, rest.length - 1)];
      const el = next ? document.querySelector<HTMLElement>(`[data-tray-key="${CSS.escape(next.key)}"]`) : null;
      if (el) el.focus();
      else heading.current?.focus();
    });
  };
  const run = async (fn: () => Promise<unknown> | void) => {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  };
  const acceptOne = (it: TrayItem) => void run(async () => {
    await onAccept([it]);
    focusNext(it.key);
  });
  const rejectOne = (it: TrayItem) => {
    onReject([it.key]);
    focusNext(it.key);
  };

  return (
    <section aria-labelledby="tray-title" className="rounded-xl border border-dashed border-primary/40 bg-primary-tint/30 p-3 sm:p-4" data-testid="review-tray">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h3 id="tray-title" ref={heading} tabIndex={-1} className="flex-1 text-sm font-semibold outline-none">
          {t("studio.tray.title", { n: pending.length })}
        </h3>
        <Button size="sm" onClick={() => void run(() => onAccept(ready))} disabled={busy || ready.length === 0} data-testid="tray-accept-all" aria-keyshortcuts="Meta+Shift+Enter">
          <Check aria-hidden /> {t("studio.tray.acceptAll", { n: ready.length })}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => onReject(pending.map((i) => i.key))} disabled={busy}>
          {t("studio.tray.dismissAll")}
        </Button>
      </div>
      <ul className="space-y-2">
        <AnimatePresence initial={false}>
          {pending.map((it) => (
            <motion.li key={it.key} layout={!reduce} initial={reduce ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={reduce ? { opacity: 0, transition: { duration: 0.1 } } : { opacity: 0, height: 0, transition: { duration: 0.18 } }}>
              <ProposalCard
                item={it}
                meta={meta}
                busy={busy}
                onAccept={() => acceptOne(it)}
                onReject={() => rejectOne(it)}
                onChange={(p) => onUpdate(it.key, p)}
                onKeyDown={(e) => {
                  if (e.target !== e.currentTarget) return;
                  if (e.key === "a") acceptOne(it);
                  else if (e.key === "r") rejectOne(it);
                }}
              />
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>
    </section>
  );
}
