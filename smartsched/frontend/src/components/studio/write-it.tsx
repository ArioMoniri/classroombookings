"use client";

import { AlertTriangle, Loader2, Sparkles } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api/endpoints";
import { HttpError } from "@/lib/api/client";
import type { Unparsed } from "@/lib/api/studio-schemas";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { useStudio, useStudioStore } from "./studio-context";

const CHIPS: MessageKey[] = ["studio.write.chip.tip", "studio.write.chip.evening", "studio.write.chip.sameRoom", "studio.write.chip.fit", "studio.write.chip.pharmacy", "studio.write.chip.nursing", "studio.write.chip.a204", "studio.write.chip.examGap"];

/** (a) "Write it in your own words" (TR/EN) → POST /terms/{id}/elicit → review tray. */
export function WriteIt({ noKey }: { noKey: boolean }) {
  const { t, locale } = useI18n();
  const { termId, store, goStep } = useStudio();
  const text = useStudioStore((s) => s.nlText);
  const setNlText = useStudioStore((s) => s.setNlText);
  const setText = (v: string | ((prev: string) => string)) => setNlText(typeof v === "function" ? v(store.getState().nlText) : v);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [keyMissing, setKeyMissing] = useState(noKey);
  const [unparsed, setUnparsed] = useState<Unparsed[]>([]);
  const area = useRef<HTMLTextAreaElement>(null);

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
      const res = await api.studio.elicit(termId, text, locale);
      const stamp = Date.now();
      store.getState().addTray(res.proposals.filter((p) => p.status !== "rejected").map((proposal, i) => ({ key: `nl-${stamp}-${i}`, origin: "nl" as const, state: "pending" as const, type: "rule" as const, proposal })));
      store.getState().addTray(res.section_edits.map((edit, i) => ({ key: `nle-${stamp}-${i}`, origin: "nl" as const, state: "pending" as const, type: "edit" as const, edit })));
      setUnparsed(res.unparsed);
      if (!res.proposals.length && !res.section_edits.length && !res.unparsed.length) setError(t("studio.write.nothing"));
    } catch (e) {
      if (e instanceof HttpError && e.status === 409) setKeyMissing(true);
      else setError(t("studio.write.aiError", { reason: e instanceof Error ? e.message : String(e) }));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2" data-testid="write-it">
      <label htmlFor="studio-write" className="flex items-center gap-1.5 text-sm font-medium">
        <Sparkles className="size-4 text-label-2" aria-hidden /> {t("studio.write.label")}
      </label>
      <Textarea
        id="studio-write"
        data-testid="rule-composer-input"
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
        data-testid="nl-input"
      />
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => void analyse()} disabled={!text.trim() || busy || keyMissing} data-testid="nl-analyse" aria-keyshortcuts="Meta+Enter">
          {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Sparkles aria-hidden />}
          {busy ? t("studio.write.reading") : t("studio.write.analyse")}
        </Button>
        <span id="studio-write-hint" className="text-xs text-label-2">
          {t("studio.write.hint")}
        </span>
      </div>
      <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1" role="group" aria-label={t("studio.write.suggestions")}>
        {CHIPS.map((k) => (
          <button key={k} type="button" onClick={() => insert(t(k))} className="shrink-0 rounded-full border bg-background px-2.5 py-1 text-xs hover:bg-fill-2 pointer-coarse:min-h-11">
            {t(k)}
          </button>
        ))}
      </div>
      {keyMissing ? (
        <p role="note" className="rounded-md bg-status-warning px-2.5 py-1.5 text-xs text-status-warning-fg" data-testid="no-key">
          {t("studio.write.noKey")}
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
              {t("studio.write.unparsed", { text: u.text, reason: u.reason })}{" "}
              <span className="inline-flex flex-wrap gap-2">
                {/hafta|week/i.test(`${u.text} ${u.reason}`) ? (
                  <button type="button" className="font-medium underline underline-offset-2" onClick={() => goStep("classes")}>
                    {t("studio.write.editWeeks")}
                  </button>
                ) : null}
                <button type="button" className="font-medium underline underline-offset-2" onClick={() => setUnparsed((l) => l.filter((_, j) => j !== i))}>
                  {t("studio.write.keepNote")}
                </button>
                <button
                  type="button"
                  className="font-medium underline underline-offset-2"
                  onClick={() => {
                    setText(u.text);
                    setUnparsed((l) => l.filter((_, j) => j !== i));
                    area.current?.focus();
                  }}
                >
                  {t("studio.write.rephrase")}
                </button>
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
