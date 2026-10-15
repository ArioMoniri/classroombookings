"use client";

import { FileUp, Loader2, X } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

export interface DropOptions {
  forceGeneral: boolean;
  useAi: boolean;
}

/** Any number of files, any format: the council decides what each one is. */
export function FileDrop({ busy, onStart }: { busy: boolean; onStart: (files: File[], opts: DropOptions) => void }) {
  const { t, n } = useI18n();
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [forceGeneral, setForceGeneral] = useState(false);
  const [useAi, setUseAi] = useState(true);
  const inputRef = useRef<HTMLInputElement>(null);

  const add = (list: FileList | null) => {
    if (!list) return;
    const incoming = Array.from(list);
    setFiles((prev) => [...prev, ...incoming.filter((f) => !prev.some((p) => p.name === f.name && p.size === f.size))]);
  };

  return (
    <Card data-testid="onboarding-drop">
      <CardContent className="space-y-4 p-4">
        <div
          role="button"
          tabIndex={0}
          aria-label={t("onboarding.drop")}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
          }}
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
          className={cn("flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed p-8 text-center", dragging ? "border-primary bg-primary-tint" : "border-border")}
        >
          <FileUp className="size-8 text-muted-foreground" aria-hidden />
          <p className="font-medium">{t("onboarding.drop")}</p>
          <p className="max-w-prose text-xs text-muted-foreground">{t("onboarding.dropHint")}</p>
          <input ref={inputRef} type="file" multiple className="sr-only" data-testid="onboarding-input" onChange={(e) => add(e.target.files)} />
        </div>

        {files.length ? (
          <ul className="divide-y rounded-lg border text-sm" aria-label={t("onboarding.filesSelected", { count: files.length })}>
            {files.map((f) => (
              <li key={`${f.name}:${f.size}`} className="flex items-center justify-between gap-2 px-3 py-2">
                <span className="min-w-0 truncate">{f.name}</span>
                <span className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
                  {n(Math.ceil(f.size / 1024))} KB
                  <Button variant="ghost" size="icon-xs" aria-label={`${t("onboarding.remove")} ${f.name}`} onClick={() => setFiles((prev) => prev.filter((p) => p !== f))}>
                    <X aria-hidden />
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        ) : null}

        <div className="flex flex-col gap-2 text-sm sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-col gap-1">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} />
              {t("onboarding.useAi")}
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={forceGeneral} onChange={(e) => setForceGeneral(e.target.checked)} />
              {t("onboarding.forceGeneral")}
            </label>
          </div>
          <Button data-testid="onboarding-start" disabled={!files.length || busy} onClick={() => onStart(files, { forceGeneral, useAi })}>
            {busy ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {t("onboarding.start", { count: files.length })}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
