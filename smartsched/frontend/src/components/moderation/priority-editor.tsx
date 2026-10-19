"use client";
/**
 * The priority editor (priority-policy spec §5.3): three tiers as glyph + word in a segmented control, where the
 * current value came from (talep / şube / kişi / program / varsayılan), an optional note, and the level it is
 * written to: the request (an override) or the whole section. A person's or a programme's default for the term
 * is the `SubjectPriorityForm` (`PUT /moderation/people|programs/{id}/priority`). Every save is audited and
 * appears in the server's "Yayından beri değişenler" list for the next re-solve. "Kaynağa dön" clears an override.
 */
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { refusal, useSetPriority, useSetSubjectPriority, type Priority, type Subject, type TierCode } from "@/lib/api/moderation";
import { useI18n } from "@/lib/i18n/provider";
import { usePermissions } from "@/lib/permissions";
import { TIERS, tierOf } from "./moderation-model";
import { ResponsiveDialog } from "./responsive-dialog";
import { usePhone } from "./use-media";
import { TierGlyph, TierLabel } from "./verdict-badge";

/**
 * Round-2 T-R2-25 (R2-M-11 / R2-M-26): after a save, focus goes to the edited row (`data-row-id`, the ModTable grid
 * row the editor was opened from) and never falls to <body>; without a row in the document, to `fallback`.
 */
export function focusAfterSave(rowId: number | string | null, fallback: HTMLElement | null): void {
  window.requestAnimationFrame(() => {
    const row = rowId !== null ? rowElement(rowId) : null;
    const target = row ?? fallback;
    if (target && document.contains(target)) target.focus();
  });
}

/** The class row of a request as the document has it now: a Eşleşmeler / Talepler grid row or a Sınıflar row. */
export function rowElement(requestId: number | string): HTMLElement | null {
  const id = String(requestId);
  return document.querySelector<HTMLElement>(`[data-row-id="${id}"], [data-class-id="${id}"]`);
}

export { focusWhenSettled } from "@/lib/focus-when-settled";

export interface PriorityTarget {
  termId: number;
  requestId: number;
  sectionId: number;
  label: string;
  priority: Priority;
}

export function PriorityForm({ target, onDone, autoFocus = false }: { target: PriorityTarget; onDone?: () => void; autoFocus?: boolean }) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const [tier, setTier] = useState<TierCode>(tierOf(target.priority.value));
  const [level, setLevel] = useState<"request" | "section">(target.priority.source === "section" ? "section" : "request");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = useSetPriority();
  const saveBtn = useRef<HTMLButtonElement>(null);

  const submit = async (clear = false) => {
    setError(null);
    try {
      await save.mutateAsync({ kind: level, id: level === "request" ? target.requestId : target.sectionId, tier: clear ? null : tier, note });
      toast.success(t("moderation.priority.saved", { label: target.label }));
      onDone?.();
      focusAfterSave(target.requestId, saveBtn.current);
    } catch (e) {
      setError(refusal(e, lang).message);
    }
  };

  return (
    <form
      className="flex flex-col gap-3"
      aria-label={t("moderation.priority.title", { label: target.label })}
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <div className="flex flex-col gap-1">
        <span className="type-footnote font-semibold text-label-2" id={`prio-${target.requestId}`}>{t("moderation.priority.label")}</span>
        <SegmentedControl<TierCode>
          aria-label={t("moderation.priority.label")}
          value={tier}
          onValueChange={setTier}
          size="sm"
          fill
          options={TIERS.map((v) => ({ value: v, label: t(`moderation.tier.${v}`), icon: <TierGlyph tier={v} /> }))}
        />
        <p className="type-caption text-label-3">
          {t("moderation.priority.current")} <TierLabel value={target.priority.value} source={target.priority.source} />
        </p>
      </div>
      <div className="flex flex-col gap-1">
        <span className="type-footnote font-semibold text-label-2">{t("moderation.priority.level")}</span>
        <SegmentedControl<"request" | "section">
          aria-label={t("moderation.priority.level")}
          value={level}
          onValueChange={setLevel}
          size="sm"
          fill
          options={[
            { value: "request", label: t("moderation.priority.levelRequest") },
            { value: "section", label: t("moderation.priority.levelSection") },
          ]}
        />
      </div>
      <label className="flex flex-col gap-1">
        <span className="type-footnote font-semibold text-label-2">{t("moderation.priority.note")}</span>
        <Input value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} placeholder={t("moderation.priority.notePh")} autoFocus={autoFocus} />
      </label>
      <p className="type-caption text-label-2">{t("moderation.nextSolve")}</p>
      {error ? (
        <p role="alert" className="type-footnote text-status-infeasible-fg">
          {error}
        </p>
      ) : null}
      <div className="flex flex-wrap justify-end gap-2">
        {target.priority.source === "request" && level === "request" ? (
          <Button type="button" variant="ghost" size="sm" onClick={() => void submit(true)} disabled={save.isPending}>
            {t("moderation.priority.clear")}
          </Button>
        ) : null}
        <Button ref={saveBtn} type="submit" size="sm" disabled={save.isPending} data-testid="priority-save">
          {save.isPending ? t("busy.saving") : t("common.save")}
        </Button>
      </div>
    </form>
  );
}

/** the Öncelik cell / `p` key: a popover with the form; a bottom sheet on phones (M-04) */
export function PriorityPopover({ target, disabled = false, open, onOpenChange }: { target: PriorityTarget; disabled?: boolean; open?: boolean; onOpenChange?: (v: boolean) => void }) {
  const { t } = useI18n();
  const phone = usePhone();
  const [own, setOwn] = useState(false);
  const isOpen = open ?? own;
  const setOpen = onOpenChange ?? setOwn;
  if (disabled) return <TierLabel value={target.priority.value} source={target.priority.source} />;
  if (phone) {
    return (
      <>
        <Button variant="ghost" onClick={() => setOpen(true)} aria-label={t("moderation.priority.edit", { label: target.label })} data-testid="priority-trigger">
          <TierLabel value={target.priority.value} source={target.priority.source} />
        </Button>
        <ResponsiveDialog open={isOpen} onOpenChange={setOpen} title={t("moderation.priority.title", { label: target.label })} footer={null} testId="priority-sheet">
          <PriorityForm target={target} onDone={() => setOpen(false)} />
        </ResponsiveDialog>
      </>
    );
  }
  return (
    <Popover open={isOpen} onOpenChange={setOpen}>
      <PopoverTrigger render={<Button variant="ghost" size="sm" aria-label={t("moderation.priority.edit", { label: target.label })} data-testid="priority-trigger" />}>
        <TierLabel value={target.priority.value} source={target.priority.source} />
      </PopoverTrigger>
      <PopoverContent className="w-80" align="start">
        <PriorityForm target={target} onDone={() => setOpen(false)} autoFocus />
      </PopoverContent>
    </Popover>
  );
}

/**
 * A person's or a programme's default priority for one term (P19-P-04): Yüksek / Normal / Düşük + a note. Every
 * request of the subject without a more specific value inherits it (request > section > person > programme);
 * Normal clears it. Coordinators and administrators only (`planning.edit`).
 */
type SubjectPriorityProps = { subject: Subject; id: number; termId: number; label: string; current: number | null; note?: string | null; onDone?: () => void; compact?: boolean };

/** Owner decision 2026-10-17 (R2-M-08): only coordinators / administrators (`planning.admin`) set a person's priority
 * (`PUT /moderation/people/{id}/priority` answers 403 `person_priority_admin` otherwise); a programme's stays
 * `planning.edit`. */
export function SubjectPriorityForm(props: SubjectPriorityProps) {
  const { can } = usePermissions();
  if (props.subject === "person" && !can("planning.admin")) return null;
  return <SubjectPriorityFields {...props} />;
}

function SubjectPriorityFields({ subject, id, termId, label, current, note: initialNote, onDone, compact = false }: SubjectPriorityProps) {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const [tier, setTier] = useState<TierCode>(tierOf(current ?? 0));
  const [note, setNote] = useState(initialNote ?? "");
  const [error, setError] = useState<string | null>(null);
  const save = useSetSubjectPriority();
  const saveBtn = useRef<HTMLButtonElement>(null);
  // the parent passes the refetched value down after a save (no remount, so the focus stays on the form; T-R2-25):
  // the form follows the new value the React way (state adjusted while rendering, no effect)
  const [seen, setSeen] = useState({ current, initialNote });
  if (seen.current !== current || seen.initialNote !== initialNote) {
    setSeen({ current, initialNote });
    setTier(tierOf(current ?? 0));
    setNote(initialNote ?? "");
  }
  const submit = async () => {
    setError(null);
    try {
      const out = await save.mutateAsync({ subject, id, termId, tier: tier === "normal" ? null : tier, note });
      toast.success(t("moderation.subjectPriority.saved", { label, n: n(out.request_ids.length) }));
      onDone?.();
      focusAfterSave(null, saveBtn.current);
    } catch (e) {
      setError(refusal(e, lang).message);
    }
  };
  return (
    <form
      className="flex flex-col gap-2"
      aria-label={t(subject === "person" ? "moderation.subjectPriority.personTitle" : "moderation.subjectPriority.programTitle", { label })}
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
      data-testid={`${subject}-priority`}
    >
      {!compact ? <p className="type-footnote text-label-2">{t(subject === "person" ? "moderation.subjectPriority.personHint" : "moderation.subjectPriority.programHint")}</p> : null}
      <SegmentedControl<TierCode>
        aria-label={t(subject === "person" ? "moderation.subjectPriority.personTitle" : "moderation.subjectPriority.programTitle", { label })}
        value={tier}
        onValueChange={setTier}
        size="sm"
        fill
        options={TIERS.map((v) => ({ value: v, label: t(`moderation.tier.${v}`), icon: <TierGlyph tier={v} /> }))}
      />
      <label className="flex flex-col gap-1">
        <span className="type-footnote font-semibold text-label-2">{t("moderation.priority.note")}</span>
        <Input value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} placeholder={t("moderation.priority.notePh")} />
      </label>
      {error ? <p role="alert" className="type-footnote text-status-infeasible-fg">{error}</p> : null}
      <div className="flex justify-end">
        <Button ref={saveBtn} type="submit" size="sm" className="max-md:h-11" disabled={save.isPending} data-testid={`${subject}-priority-save`}>
          {save.isPending ? t("busy.saving") : t("common.save")}
        </Button>
      </div>
    </form>
  );
}
