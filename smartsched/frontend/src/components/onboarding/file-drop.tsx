"use client";
/**
 * Files step (phase19-intake R7, review 2026-10-15 §3 Onboarding): a LEFT-aligned dropzone row with a real
 * `<label for>` on the file input (axe: the input[multiple] had no name, and the dropzone was a role=button
 * around it, a nested-interactive), then a files table (Ad · Tür · Boyut · Yol · ✕) with the predicted
 * Doğrudan / YZ route. The start action appears only once there are files, and says "YZ ile oku ve başlat"
 * when a file will take the AI route. References: AWS upload status (R7), Attio import (R1).
 *
 * T-R1-23: the AI switch follows the administrator's AI policy (GET /ai/policy `intake_enabled`). When it is off,
 * the switch is unticked and disabled ("Yönetici kapattı"), PDF / DOCX / TXT rows read "YZ kapalı" (only their
 * tables are read on the server) and the button says "Başlat · N dosya". A policy that cannot be read leaves the
 * switch as it was: the server applies the policy either way.
 */
import { FolderInput, X } from "lucide-react";
import { useId, useRef, useState } from "react";
import { Button, IconButton } from "@/components/ui/button";
import { BusyGlyph } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { useAiPolicy } from "@/lib/api/ai-policy";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { predictedRoute, useOnboardingCopy } from "./copy";
import { MethodBadge } from "./method-badge";

export interface DropOptions {
  forceGeneral: boolean;
  useAi: boolean;
}

function ext(name: string): string {
  const m = /\.([a-z0-9]+)$/i.exec(name);
  return m ? m[1].toUpperCase() : "—";
}

export function FileDrop({ busy, onStart }: { busy: boolean; onStart: (files: File[], opts: DropOptions) => void }) {
  const { t, n } = useI18n();
  const c = useOnboardingCopy();
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [forceGeneral, setForceGeneral] = useState(false);
  const [wantAi, setUseAi] = useState(true);
  const policy = useAiPolicy();
  const aiOff = policy.data?.intake_enabled === false;
  const useAi = wantAi && !aiOff;
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();
  const aiNoteId = useId();

  const add = (list: FileList | null) => {
    if (!list) return;
    const incoming = Array.from(list);
    setFiles((prev) => [...prev, ...incoming.filter((f) => !prev.some((p) => p.name === f.name && p.size === f.size))]);
  };
  const anyAi = useAi && files.some((f) => predictedRoute(f.name) === "ai");

  return (
    <Card className="gap-0 p-0" data-testid="onboarding-drop">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          add(e.dataTransfer.files);
        }}
        data-dragging={dragging || undefined}
        className={cn("flex flex-wrap items-center gap-x-4 gap-y-3 p-4 transition-colors duration-(--dur-fast)", dragging && "bg-tint-soft")}
      >
        <span aria-hidden className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-fill-2 text-label-2">
          <FolderInput className="size-5 stroke-[1.75]" />
        </span>
        <div className="min-w-0 flex-1 basis-64">
          <label htmlFor={inputId} className="type-headline text-label-1">
            {c.dropTitle}
          </label>
          <p className="type-footnote text-label-2">{c.dropHint}</p>
        </div>
        <input ref={inputRef} id={inputId} type="file" multiple className="sr-only" data-testid="onboarding-input" onChange={(e) => add(e.target.files)} />
        <Button variant="outline" onClick={() => inputRef.current?.click()}>
          {c.choose}
        </Button>
      </div>

      {files.length ? (
        <>
          <div className="overflow-x-auto edge-hairline-t">
            <table className="w-full type-callout" aria-label={t("onboarding.filesSelected", { count: files.length })}>
              <thead>
                <tr className="text-left type-footnote text-label-2 edge-hairline-b">
                  <th scope="col" className="px-4 py-2 font-semibold">{c.colName}</th>
                  <th scope="col" className="px-2 py-2 font-semibold">{c.colType}</th>
                  <th scope="col" className="px-2 py-2 text-right font-semibold">{c.colSize}</th>
                  <th scope="col" className="px-2 py-2 font-semibold">{c.colRoute}</th>
                  <th scope="col" className="w-12 px-2 py-2"><span className="sr-only">{t("onboarding.remove")}</span></th>
                </tr>
              </thead>
              <tbody>
                {files.map((f) => (
                  <tr key={`${f.name}:${f.size}`} className="edge-hairline-b">
                    <td className="max-w-0 truncate px-4 py-1.5 text-label-1">{f.name}</td>
                    <td className="px-2 py-1.5 text-label-2">{ext(f.name)}</td>
                    <td className="px-2 py-1.5 text-right text-label-2">{n(Math.max(1, Math.ceil(f.size / 1024)))} KB</td>
                    <td className="px-2 py-1.5"><MethodBadge method={predictedRoute(f.name) === "ai" ? (useAi ? "ai" : "off") : "direct"} /></td>
                    <td className="px-2 py-1">
                      <IconButton size="sm" label={c.remove(f.name)} onClick={() => setFiles((prev) => prev.filter((p) => p !== f))}>
                        <X aria-hidden />
                      </IconButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3 p-4">
            <div className="flex flex-col gap-2">
              <label className={cn("flex items-center gap-2 type-callout", aiOff ? "text-label-2" : "text-label-1")}>
                <Checkbox checked={useAi} disabled={aiOff} aria-describedby={aiOff ? aiNoteId : undefined} onCheckedChange={(v) => setUseAi(Boolean(v))} />
                {t("onboarding.useAi")}
                {aiOff ? (
                  <span id={aiNoteId} className="type-footnote text-label-2" data-testid="onboarding-ai-off" title={c.aiOffHint}>
                    · {c.aiOffByAdmin}
                  </span>
                ) : null}
              </label>
              <label className="flex items-center gap-2 type-callout text-label-1">
                <Checkbox checked={forceGeneral} onCheckedChange={(v) => setForceGeneral(Boolean(v))} />
                {t("onboarding.forceGeneral")}
              </label>
            </div>
            <Button className="ml-auto" data-testid="onboarding-start" disabled={busy} onClick={() => onStart(files, { forceGeneral, useAi })}>
              {busy ? <BusyGlyph /> : null}
              {anyAi ? c.startAi : c.start(files.length)}
            </Button>
          </div>
        </>
      ) : null}
    </Card>
  );
}
