"use client";
/**
 * The priority editor (priority-policy spec §5.3): three tiers as glyph + word in a segmented control, where the
 * current value came from (talep / şube / varsayılan), an optional note, and the level it is written to: the
 * request (an override) or the whole section. Every save is audited server-side and staged for the next
 * re-solve. "Kaynağa dön" clears a request override.
 */
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { refusal, useSetPriority, type Priority, type TierCode } from "@/lib/api/moderation";
import { useI18n } from "@/lib/i18n/provider";
import { TIERS, tierOf } from "./moderation-model";
import { useStagedStore } from "./staged-store";
import { TierGlyph, TierLabel } from "./verdict-badge";

export interface PriorityTarget {
  termId: number;
  requestId: number;
  sectionId: number;
  label: string;
  priority: Priority;
  /** every request of the section (a section-level change stages them all) */
  sectionRequestIds?: number[];
}

export function PriorityForm({ target, onDone, autoFocus = false }: { target: PriorityTarget; onDone?: () => void; autoFocus?: boolean }) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const [tier, setTier] = useState<TierCode>(tierOf(target.priority.value));
  const [level, setLevel] = useState<"request" | "section">(target.priority.source === "section" ? "section" : "request");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = useSetPriority();
  const stage = useStagedStore((s) => s.add);

  const submit = async (clear = false) => {
    setError(null);
    try {
      await save.mutateAsync({ kind: level, id: level === "request" ? target.requestId : target.sectionId, tier: clear ? null : tier, note });
      stage(target.termId, {
        requestIds: level === "section" ? (target.sectionRequestIds?.length ? target.sectionRequestIds : [target.requestId]) : [target.requestId],
        label: t("moderation.staged.priority", { label: target.label, tier: t(`moderation.tier.${clear ? "normal" : tier}`) }),
        at: new Date().toISOString(),
      });
      toast.success(t("moderation.priority.saved", { label: target.label }));
      onDone?.();
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
        <Button type="submit" size="sm" disabled={save.isPending} data-testid="priority-save">
          {save.isPending ? t("busy.saving") : t("common.save")}
        </Button>
      </div>
    </form>
  );
}

/** the Öncelik cell / `p` key: a popover with the form */
export function PriorityPopover({ target, disabled = false, open, onOpenChange }: { target: PriorityTarget; disabled?: boolean; open?: boolean; onOpenChange?: (v: boolean) => void }) {
  const { t } = useI18n();
  const [own, setOwn] = useState(false);
  const isOpen = open ?? own;
  const setOpen = onOpenChange ?? setOwn;
  if (disabled) return <TierLabel value={target.priority.value} source={target.priority.source} />;
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
