"use client";
/**
 * HX-08 (helper.md §5.1, `helper-states.svg` C): Profil › Yardımcı — what the helper remembers, all of it visible and
 * deletable. The person's switch "Yardımcı notlarımı kullansın" (`PUT /helper/memory`), the notes (≤ 20 × ≤ 200
 * characters; "Sil" per note, "Not ekle"; the server refuses a person's name and says so), the conversation history
 * ("Son 30 günün konuşmaları saklanır", "Geçmişi sil" with a confirmation) and the plain notice. A note exists only
 * after the person adds it here or taps "Hatırla"; the institution's switch (admin) can turn notes off for everyone.
 */
import { Trash2 } from "lucide-react";
import { useId, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Alert, SectionTitle } from "@/components/admin/kit";
import { Button, IconButton } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { helperRefusal, useAddHelperNote, useDeleteAllHelperNotes, useDeleteHelperNote, useHelperMemory, useHelperNotes, useSetHelperMemory } from "@/lib/api/helper";
import type { Locale } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";

function refusalText(err: unknown, locale: Locale, fallback: string): string {
  const r = helperRefusal(err);
  return (locale === "en" ? r.en : r.tr) ?? r.tr ?? r.en ?? fallback;
}

export function HelperMemorySection() {
  const { t, locale } = useI18n();
  const memory = useHelperMemory();
  const notes = useHelperNotes();
  const setMemory = useSetHelperMemory();
  const add = useAddHelperNote();
  const del = useDeleteHelperNote();
  const delAll = useDeleteAllHelperNotes();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [confirmHistory, setConfirmHistory] = useState(false);
  const [live, setLive] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const switchId = useId();
  const fieldId = useId();
  const m = memory.data;
  const max = m?.max_chars ?? 200;
  const institutionOff = m ? !m.institution_enabled : false;
  const list = notes.data ?? [];
  const full = m ? list.length >= m.max_notes : false;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const value = text.trim();
    if (!value) return;
    setError(null);
    try {
      await add.mutateAsync({ text: value, source: "user_confirmed" });
      setText("");
      setLive(t("helper.memory.added"));
      inputRef.current?.focus();
    } catch (err) {
      setError(refusalText(err, locale, t("helper.error.provider")));
      inputRef.current?.focus();
    }
  };

  const remove = async (id: number, at: number) => {
    try {
      await del.mutateAsync(id);
      setLive(t("helper.memory.deleted"));
      // the next note's delete button, else the field (focus never falls to <body>)
      requestAnimationFrame(() => {
        const rest = document.querySelectorAll<HTMLElement>("[data-testid^='helper-note-delete-']");
        (rest[Math.min(at, rest.length - 1)] ?? inputRef.current)?.focus();
      });
    } catch (err) {
      setError(refusalText(err, locale, t("helper.error.provider")));
    }
  };

  const deleteHistory = async () => {
    try {
      await delAll.mutateAsync({ history: true });
      setConfirmHistory(false);
      toast(t("helper.memory.historyDeleted"));
      setLive(t("helper.memory.historyDeleted"));
      requestAnimationFrame(() => headingRef.current?.focus());
    } catch (err) {
      setError(refusalText(err, locale, t("helper.error.provider")));
      setConfirmHistory(false);
    }
  };

  return (
    <section id="helper" aria-labelledby="pf-helper" className="scroll-mt-20" data-testid="helper-memory" data-tour="profile-helper-memory">
      <SectionTitle id="pf-helper">
        <span ref={headingRef} tabIndex={-1} className="outline-hidden">
          {t("helper.memory.title")}
        </span>
      </SectionTitle>
      <Card variant="glass" className="gap-4 px-4">
        <p className="sr-only" role="status" aria-live="polite">
          {live}
        </p>
        {memory.isLoading ? (
          <div className="flex flex-col gap-2" aria-busy="true">
            <Skeleton className="h-6 w-64" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : memory.isError ? (
          <Alert tone="error" action={<Button size="sm" variant="secondary" onClick={() => void memory.refetch()}>{t("helper.retry")}</Button>}>
            {t("helper.memory.loadError")}
          </Alert>
        ) : (
          <>
            <div className="flex items-center justify-between gap-3">
              <Label htmlFor={switchId} className="type-body">
                {t("helper.memory.switch")}
              </Label>
              <Switch id={switchId} checked={!!m?.enabled} disabled={institutionOff || setMemory.isPending} onCheckedChange={(v) => setMemory.mutate(v)} data-testid="helper-memory-switch" />
            </div>
            {institutionOff ? <p className="type-footnote text-label-2">{t("helper.memory.switchOffInstitution")}</p> : null}

            <div className="flex flex-col gap-2">
              <h3 className="type-headline text-label-1">{t("helper.memory.notes")}</h3>
              {notes.isLoading ? (
                <Skeleton className="h-10 w-full" />
              ) : list.length === 0 ? (
                <p className="type-callout text-label-2" data-testid="helper-notes-empty">{t("helper.memory.emptyNotes")}</p>
              ) : (
                <ul className="flex flex-col">
                  {list.map((n, i) => (
                    <li key={n.id} className="flex items-center justify-between gap-2 py-1.5 not-last:edge-hairline-b" data-testid={`helper-note-${n.id}`}>
                      <span className="min-w-0 break-words type-callout text-label-1">{n.text}</span>
                      <IconButton label={t("helper.memory.deleteNote", { text: n.text })} onClick={() => void remove(n.id, i)} data-testid={`helper-note-delete-${n.id}`} className="shrink-0">
                        <Trash2 aria-hidden />
                      </IconButton>
                    </li>
                  ))}
                </ul>
              )}
              {!institutionOff ? (
                <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-1.5" noValidate>
                  <Label htmlFor={fieldId}>{t("helper.memory.noteLabel")}</Label>
                  <div className="flex gap-2 max-sm:flex-col">
                    <Input
                      ref={inputRef}
                      id={fieldId}
                      value={text}
                      maxLength={max}
                      disabled={full}
                      onChange={(e) => {
                        setText(e.target.value);
                        setError(null);
                      }}
                      placeholder={t("helper.memory.notePlaceholder")}
                      aria-invalid={error ? true : undefined}
                      aria-describedby={`${fieldId}-hint`}
                      className="text-base sm:type-callout"
                      data-testid="helper-note-input"
                    />
                    <Button type="submit" disabled={!text.trim() || full || add.isPending} data-testid="helper-note-add">
                      {t("helper.memory.addNote")}
                    </Button>
                  </div>
                  <p id={`${fieldId}-hint`} className="type-footnote text-label-3">
                    {full ? t("helper.memory.noteLimit", { max: m?.max_notes ?? 20 }) : t("helper.memory.noteCount", { n: text.length, max })}
                  </p>
                  {error ? (
                    <p role="alert" className="type-footnote text-status-infeasible-fg" data-testid="helper-note-error">
                      {error}
                    </p>
                  ) : null}
                </form>
              ) : null}
              <p className="type-footnote text-label-3">{t("helper.memory.retention", { days: m?.retention_days ?? 180 })}</p>
            </div>

            <div className="flex flex-col gap-2">
              <h3 className="type-headline text-label-1">{t("helper.memory.historyTitle")}</h3>
              <p className="type-callout text-label-2">{t("helper.memory.history", { days: m?.history_days ?? 30 })}</p>
              <Button variant="secondary" className="self-start" onClick={() => setConfirmHistory(true)} data-testid="helper-history-delete">
                {t("helper.memory.deleteHistory")}
              </Button>
            </div>
            <p className="type-footnote text-label-2">{t("helper.memory.notice", { days: m?.history_days ?? 30 })}</p>
          </>
        )}
      </Card>
      <Dialog open={confirmHistory} onOpenChange={setConfirmHistory}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("helper.memory.deleteHistoryTitle")}</DialogTitle>
            <DialogDescription>{t("helper.memory.deleteHistoryBody", { days: m?.history_days ?? 30 })}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmHistory(false)}>
              {t("helper.card.cancel")}
            </Button>
            <Button variant="destructive" onClick={() => void deleteHistory()} disabled={delAll.isPending} data-testid="helper-history-confirm">
              {t("helper.memory.deleteHistory")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
