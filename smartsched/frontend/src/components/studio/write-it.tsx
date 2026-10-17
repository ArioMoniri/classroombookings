"use client";

import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, PenLine, ScanText } from "lucide-react";
import { useRef, useState } from "react";
import { AiNotice } from "@/components/admin/ai/ai-kit";
import { AiUsageBanner } from "@/components/admin/ai/my-ai-usage";
import { Button } from "@/components/ui/button";
import { BusyGlyph, busyProps } from "@/components/ui/busy-label";
import { Textarea } from "@/components/ui/textarea";
import { aiKeys } from "@/lib/api/ai-admin";
import { api } from "@/lib/api/endpoints";
import { HttpError } from "@/lib/api/client";
import type { Unparsed } from "@/lib/api/studio-schemas";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { useStudio, useStudioStore } from "./studio-context";
import { pairLang } from "@/lib/i18n";
import { refusedAsDecisions, splitRefused } from "./refused";
import { BareButton } from "@/components/shell/bare-button";
import { chipPrefill } from "./chip-prefill";
import { useStudioData } from "./studio-data";
import type { BuilderPrefill } from "./template-gallery";

/** A coded AI gateway refusal (guardrail 422, limit / rate 429: `detail {code, message_tr, message_en}`) in the UI
 *  language, or null for any other error. */
export function aiRefusalText(e: unknown, lang: "tr" | "en"): string | null {
  if (!(e instanceof HttpError) || !e.detail || typeof e.detail !== "object") return null;
  const outer = e.detail as Record<string, unknown>;
  const d = (outer.detail && typeof outer.detail === "object" ? outer.detail : outer) as Record<string, unknown>;
  const text = lang === "tr" ? d.message_tr : d.message_en;
  return typeof text === "string" && text ? text : null;
}

const CHIPS: MessageKey[] = ["studio.write.chip.tip", "studio.write.chip.evening", "studio.write.chip.sameRoom", "studio.write.chip.fit", "studio.write.chip.pharmacy", "studio.write.chip.nursing", "studio.write.chip.a204", "studio.write.chip.examGap"];

/** (a) "Write it in your own words" (TR/EN) → POST /terms/{id}/elicit → review tray.
 *  Without an AI key an example chip opens its template pre-filled instead (round-1 T-R1-46): `onOpenTemplate`. */
export function WriteIt({ noKey, onOpenTemplate }: { noKey: boolean; onOpenTemplate?: (prefill: BuilderPrefill) => void }) {
  const { t, locale } = useI18n();
  const { termId, store, goStep, meta, kind, sentence } = useStudio();
  const { rooms } = useStudioData();
  const text = useStudioStore((s) => s.nlText);
  const setNlText = useStudioStore((s) => s.setNlText);
  const setText = (v: string | ((prev: string) => string)) => setNlText(typeof v === "function" ? v(store.getState().nlText) : v);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // the settings load after the first render: derive from the prop (useState(noKey) froze the first value)
  const [keyRejected, setKeyRejected] = useState(false);
  const keyMissing = noKey || keyRejected;
  const [unparsed, setUnparsed] = useState<Unparsed[]>([]);
  const area = useRef<HTMLTextAreaElement>(null);
  const qc = useQueryClient();

  const insert = (phrase: string) => {
    const el = area.current;
    if (!el) return setText((v) => `${v}${v && !/[.;\n]\s*$/.test(v) ? ". " : ""}${phrase}`);
    const start = el.selectionStart ?? text.length;
    const end = el.selectionEnd ?? text.length;
    const before = text.slice(0, start);
    const sep = before && !/[.;\n]\s*$/.test(before) ? ". " : "";
    const next = `${before}${sep}${phrase}${text.slice(end)}`;
    setText(next);
    window.requestAnimationFrame(() => {
      el.focus();
      const pos = before.length + sep.length + phrase.length;
      el.setSelectionRange(pos, pos);
    });
  };

  const analyse = async () => {
    if (!text.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.studio.elicit(termId, text, pairLang(locale));
      const stamp = Date.now();
      const { usable, refused } = splitRefused(res.proposals);
      store.getState().addTray(usable.map((proposal, i) => ({ key: `nl-${stamp}-${i}`, origin: "nl" as const, state: "pending" as const, type: "rule" as const, proposal })));
      store.getState().addTray(res.section_edits.map((edit, i) => ({ key: `nle-${stamp}-${i}`, origin: "nl" as const, state: "pending" as const, type: "edit" as const, edit })));
      // refused by the AI source policy: the planner decides, with the reason (never dropped silently)
      setUnparsed([...refusedAsDecisions(refused), ...res.unparsed]);
      if (!res.proposals.length && !res.section_edits.length && !res.unparsed.length) setError(t("studio.write.nothing"));
    } catch (e) {
      const refusal = aiRefusalText(e, pairLang(locale));
      if (refusal) setError(refusal);
      else if (e instanceof HttpError && e.status === 409) setKeyRejected(true);
      else setError(t("studio.write.aiError", { reason: e instanceof Error ? e.message : String(e) }));
    } finally {
      setBusy(false);
      void qc.invalidateQueries({ queryKey: aiKeys.me }); // the near / at-limit banner follows this call's tokens
    }
  };

  return (
    <div className="space-y-2" data-testid="write-it">
      <label htmlFor="studio-write" className="flex items-center gap-1.5 text-sm font-medium">
        <PenLine className="size-4 text-label-2" aria-hidden /> {t("studio.write.label")}
      </label>
      <Textarea
        id="studio-write"
        ref={area}
        rows={3}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
            e.preventDefault();
            e.stopPropagation();
            void analyse();
          }
        }}
        placeholder={t("studio.write.placeholder")}
        aria-describedby="studio-write-hint"
        className="field-sizing-content max-h-64 min-h-20 resize-y"
        lang={locale}
        data-testid="rule-composer-input"
      />
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => void analyse()} {...busyProps(busy, !text.trim() || keyMissing)} data-testid="nl-analyse" aria-keyshortcuts="Meta+Enter">
          {busy ? <BusyGlyph /> : <ScanText aria-hidden />}
          {busy ? t("studio.write.reading") : t("studio.write.analyse")}
        </Button>
        <span id="studio-write-hint" className="text-xs text-label-2">
          {t("studio.write.hint")}
        </span>
      </div>
      <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1" role="group" aria-label={t("studio.write.suggestions")}>
        {CHIPS.map((k) => {
          // no key: the chip opens the structured template that says the same, pre-filled from the term's data; the
          // sentence alone would be a dead end ("Kurala çevir" needs AI; round-1 R1-S-08 / R1-M-13)
          const prefill = keyMissing && onOpenTemplate ? chipPrefill(k, { templates: meta?.templates ?? [], programs: sentence.programs, rooms, kind }) : null;
          return (
            <BareButton key={k} onClick={() => (prefill ? onOpenTemplate?.(prefill) : insert(t(k)))} className="shrink-0 rounded-full border bg-background px-2.5 py-1 text-xs hover:bg-fill-2 pointer-coarse:min-h-11" data-testid="example-chip" data-opens={prefill ? "template" : "text"}>
              {t(k)}
            </BareButton>
          );
        })}
      </div>
      <AiUsageBanner />
      <AiNotice />
      {keyMissing ? (
        <p role="note" className="rounded-md bg-status-warning px-2.5 py-1.5 text-xs text-status-warning-fg" data-testid="no-key">
          {t("studio.write.noKey")} {onOpenTemplate ? t("studio.write.noKeyChips") : ""}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="flex items-center gap-1.5 text-xs text-status-infeasible-fg">
          <AlertTriangle className="size-3.5" aria-hidden /> {error}
        </p>
      ) : null}
      {unparsed.length ? (
        <ul className="space-y-1.5" aria-label={t("studio.write.unparsedTitle")}>
          {unparsed.map((u, i) => (
            <li key={`${u.text}-${i}`} className="rounded-md border border-status-warning-border bg-status-warning px-2.5 py-1.5 text-xs text-status-warning-fg" data-testid="unparsed-note">
              {u.decision ? t("studio.write.decision", { text: u.text, reason: u.reason }) : t("studio.write.unparsed", { text: u.text, reason: u.reason })}{" "}
              <span className="inline-flex flex-wrap gap-2">
                {/hafta|week/i.test(`${u.text} ${u.reason}`) ? (
                  <BareButton className="font-medium underline underline-offset-2" onClick={() => goStep("classes")}>
                    {t("studio.write.editWeeks")}
                  </BareButton>
                ) : null}
                <BareButton className="font-medium underline underline-offset-2" onClick={() => setUnparsed((l) => l.filter((_, j) => j !== i))}>
                  {t("studio.write.keepNote")}
                </BareButton>
                <BareButton
                  className="font-medium underline underline-offset-2"
                  onClick={() => {
                    setText(u.text);
                    setUnparsed((l) => l.filter((_, j) => j !== i));
                    area.current?.focus();
                  }}
                >
                  {t("studio.write.rephrase")}
                </BareButton>
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
