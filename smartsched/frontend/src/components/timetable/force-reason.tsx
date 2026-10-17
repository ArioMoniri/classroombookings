"use client";
/**
 * Forcing a move that breaks a hard rule (2026-10-15 backend contract, persona M-02 / M-09): administrators only,
 * with a written reason (≥ 3 characters) that the run report lists under "forced moves". The 422 answer names the
 * broken rules and conflicts ("80 öğrenci 30 kişilik C 606'ya sığmaz"); they are shown here verbatim.
 * `askForceReason()` opens the dialog from anywhere (the move toast action) and resolves with the reason or null.
 */
import { AlertTriangle } from "lucide-react";
import { useId, useState } from "react";
import { create } from "zustand";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/lib/i18n/provider";

type Ask = { conflicts: string[]; rules: string[]; resolve: (reason: string | null) => void };
const useForce = create<{ ask: Ask | null; set: (a: Ask | null) => void }>((set) => ({ ask: null, set: (ask) => set({ ask }) }));

export function askForceReason(conflicts: string[], rules: string[] = []): Promise<string | null> {
  return new Promise((resolve) => useForce.getState().set({ conflicts, rules, resolve }));
}

/** 422 body of a forced move without a (valid) reason: `{detail: {message, rules, conflicts}}`. */
export function forceRefusal(detail: unknown): { rules: string[]; conflicts: string[] } | null {
  const d = detail && typeof detail === "object" ? (detail as Record<string, unknown>) : null;
  const inner = d && typeof d.detail === "object" && d.detail ? (d.detail as Record<string, unknown>) : d;
  if (!inner || !Array.isArray(inner.rules)) return null;
  return { rules: inner.rules.map(String), conflicts: Array.isArray(inner.conflicts) ? inner.conflicts.map(String) : [] };
}

export function ForceReasonHost() {
  const { locale } = useI18n();
  const tr = locale === "tr";
  const ask = useForce((s) => s.ask);
  const set = useForce((s) => s.set);
  const [reason, setReason] = useState("");
  const id = useId();
  const close = (value: string | null) => {
    ask?.resolve(value);
    set(null);
    setReason("");
  };
  const ok = reason.trim().length >= 3;
  return (
    <Dialog open={ask !== null} onOpenChange={(o) => !o && close(null)}>
      <DialogContent className="sm:max-w-md" data-testid="force-reason">
        <DialogHeader>
          <DialogTitle>{tr ? "Kurala rağmen taşı" : "Move despite the rules"}</DialogTitle>
          <DialogDescription>{tr ? "Bu taşıma zorunlu bir kuralı bozuyor. Yalnız yöneticiler yapabilir; gerekçe çalıştırma raporunda listelenir." : "This move breaks a hard rule. Only administrators can do it; the reason is listed in the run report."}</DialogDescription>
        </DialogHeader>
        {ask && (ask.conflicts.length || ask.rules.length) ? (
          <ul className="grid gap-1 rounded-lg bg-status-warning px-3 py-2 type-callout text-status-warning-fg" data-testid="force-rules">
            {(ask.conflicts.length ? ask.conflicts : ask.rules).map((c) => (
              <li key={c} className="flex items-start gap-1.5">
                <AlertTriangle aria-hidden className="mt-0.5 size-3.5 shrink-0" />
                <span className="text-label-1">{c}</span>
              </li>
            ))}
          </ul>
        ) : null}
        <label htmlFor={id} className="type-callout font-medium text-label-1">{tr ? "Gerekçe" : "Reason"}</label>
        <Textarea id={id} value={reason} onChange={(e) => setReason(e.target.value)} placeholder={tr ? "Ör. bölüm başkanı onayladı, öğrenciler iki gruba bölünecek" : "e.g. approved by the head of department, students split in two groups"} rows={3} autoFocus data-testid="force-reason-input" />
        <DialogFooter>
          <Button variant="outline" onClick={() => close(null)}>{tr ? "Vazgeç" : "Cancel"}</Button>
          <Button variant="destructive" disabled={!ok} onClick={() => close(reason.trim())} data-testid="force-reason-confirm">{tr ? "Gerekçeyle taşı" : "Move with this reason"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
