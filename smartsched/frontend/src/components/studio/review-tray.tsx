"use client";

import { Check, Pencil, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useRef, useState, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { BusyButton, busyProps } from "@/components/ui/busy-label";
import type { ProposedConstraint } from "@/lib/api/schemas";
import type { StudioMeta } from "@/lib/api/studio-schemas";
import { pairLang } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { springs, tween, useReduce } from "@/lib/motion";
import { RuleCard, type Candidate } from "./rule-card";
import { allowedHardness, detectTextLang, fallbackSentence, provenanceText, ruleTokens } from "./rule-helpers";
import { writeField } from "./rule-sentence";
import { asSource } from "./source-chip";
import { useStudioData } from "./studio-data";
import type { TrayItem } from "./studio-store";
import { TRAY_ANIMATE_MAX, trayTravelId } from "./tray-travel";

export { TRAVEL_MAX, TRAY_ANIMATE_MAX, trayTravelId, travelPairs } from "./tray-travel";

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
export function ProposalCard({ item, meta, onAccept, onReject, onChange, onKeyDown, busy, accepting = false }: { item: Extract<TrayItem, { type: "rule" }>; meta: StudioMeta | undefined; onAccept: () => void; onReject: () => void; onChange: (p: ProposedConstraint) => void; onKeyDown?: (e: KeyboardEvent<HTMLDivElement>) => void; busy?: boolean; /** this card's Accept is running */ accepting?: boolean }) {
  const { t, locale } = useI18n();
  const { sentence, advanced } = useStudioData();
  const [editing, setEditing] = useState(false);
  const p = item.proposal;
  const { template, tokens } = ruleTokens(meta, p.kind, p.params, sentence, editing);
  const candidates: Candidate[] = unresolvedCandidates(p).map((c) => ({ text: c.text, options: c.options, onPick: (id) => onChange(resolveCandidate(p, c.index, id)) }));
  const ready = p.status === "ok";
  // the planner's own words stay as written; a small tag names their language when it is not the UI one
  const lang = p.nl_text ? detectTextLang(p.nl_text) : null;
  return (
    <div tabIndex={-1} onKeyDown={onKeyDown} data-tray-key={item.key} className="rounded-[var(--radius-md)] outline-hidden focus-visible:ring-3 focus-visible:ring-ring/50" data-testid="tray-item" data-status={p.status}>
      <RuleCard
        domId={`tray-${item.key}`}
        testId="proposal-card"
        tokens={tokens}
        fallback={fallbackSentence(meta, p.kind, p.title ?? p.nl_text, locale)}
        nlText={p.nl_text || null}
        writtenIn={lang && lang !== pairLang(locale) ? lang : null}
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
<span className="inline-flex" data-testid="rule-accept">
            {/* busy keeps focus on the pressed button (aria-disabled), so keyboard users never land on <body> */}
            <BusyButton size="sm" onClick={onAccept} busy={accepting} busyLabel={t("studio.tray.accepting")} icon={<Check aria-hidden />} disabled={busy || p.status === "rejected"} focusableWhenDisabled data-testid="tray-accept" aria-keyshortcuts="a">
              {" "}{t("studio.tray.accept")}
            </BusyButton>
            </span>
            <Button size="sm" variant="outline" onClick={() => setEditing((v) => !v)} aria-pressed={editing} aria-keyshortcuts="e">
              <Pencil aria-hidden /> {t("common.edit")}
            </Button>
            <Button size="sm" variant="ghost" onClick={onReject} {...busyProps(false, Boolean(busy))} focusableWhenDisabled data-testid="tray-reject" aria-keyshortcuts="r">
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
  const reduce = useReduce();
  const heading = useRef<HTMLHeadingElement>(null);
  /** the tray key whose Accept runs, "*" for Accept all, null when idle */
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const busy = busyKey !== null;
  const [announce, setAnnounce] = useState("");
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
  const run = async (key: string, fn: () => Promise<unknown> | void) => {
    if (busy) return;
    setBusyKey(key);
    try {
      await fn();
    } finally {
      setBusyKey(null);
    }
  };
  const acceptOne = (it: TrayItem) => void run(it.key, async () => {
    await onAccept([it]);
    setAnnounce(t("studio.history.accepted", { n: 1 }));
    focusNext(it.key);
  });
  const acceptAll = () => void run("*", async () => {
    await onAccept(ready);
    setAnnounce(t("studio.history.accepted", { n: ready.length }));
    heading.current?.focus();
  });
  const rejectOne = (it: TrayItem) => {
    if (busy) return;
    onReject([it.key]);
    setAnnounce(t("studio.tray.dismissedLive", { n: 1 }));
    focusNext(it.key);
  };
  // > 40 cards: no insert / remove animation; reduced motion: no layout, no travel (motion_designer §4, §8)
  const animate = !reduce && pending.length <= TRAY_ANIMATE_MAX;

  return (
    <section aria-labelledby="tray-title" className="rounded-xl border border-dashed border-primary/40 bg-tint-soft/30 p-3 sm:p-4" data-testid="review-tray">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h3 id="tray-title" ref={heading} tabIndex={-1} className="flex-1 text-sm font-semibold outline-hidden">
          {t("studio.tray.title", { n: pending.length })}
        </h3>
        <BusyButton size="sm" onClick={acceptAll} busy={busyKey === "*"} busyLabel={t("studio.tray.accepting")} icon={<Check aria-hidden />} disabled={busy || ready.length === 0} data-testid="tray-accept-all" aria-keyshortcuts="Meta+Shift+Enter">
          {" "}{t("studio.tray.acceptAll", { n: ready.length })}
        </BusyButton>
        <Button size="sm" variant="ghost" onClick={() => { if (busy) return; onReject(pending.map((i) => i.key)); setAnnounce(t("studio.tray.dismissedLive", { n: pending.length })); heading.current?.focus(); }} {...busyProps(false, busy)} focusableWhenDisabled>
          {t("studio.tray.dismissAll")}
        </Button>
      </div>
      <p role="status" className="sr-only">{announce}</p>
      <ul className="space-y-2">
        <AnimatePresence initial={false} mode="popLayout">
          {pending.map((it) => {
            const card = (
              <ProposalCard
                item={it}
                meta={meta}
                busy={busy}
                accepting={busyKey === it.key}
                onAccept={() => acceptOne(it)}
                onReject={() => rejectOne(it)}
                onChange={(p) => onUpdate(it.key, p)}
                onKeyDown={(e) => {
                  if (e.target !== e.currentTarget) return;
                  if (e.key === "a") acceptOne(it);
                  else if (e.key === "r") rejectOne(it);
                }}
              />
            );
            if (!animate) {
              // reduced motion: a 100 ms fade out; > 40 cards: instant (no AnimatePresence work per card)
              return reduce && pending.length <= TRAY_ANIMATE_MAX ? (
                <motion.li key={it.key} data-testid="tray-li" data-animate="off" initial={false} animate={{ opacity: 1 }} exit={{ opacity: 0, transition: tween.reduced }}>
                  {card}
                </motion.li>
              ) : (
                <li key={it.key} data-testid="tray-li" data-animate="off">
                  {card}
                </li>
              );
            }
            // transform / opacity only: siblings reflow by FLIP (layout), the card leaves with a fade + 2 % scale,
            // and an accepted card hands its box to the new rule card (layoutId) so it travels into its group
            return (
              <motion.li
                key={it.key}
                data-testid="tray-li"
                data-animate="on"
                data-travel-id={trayTravelId(it.key)}
                layout
                layoutId={trayTravelId(it.key)}
                transition={springs.smooth}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.98, transition: tween.fadeOut }}
              >
                {card}
              </motion.li>
            );
          })}
        </AnimatePresence>
      </ul>
    </section>
  );
}
