"use client";

import { Check, Database, FileSpreadsheet, FileUp, Grid3x3, ListChecks, Loader2, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { NativeSelect } from "@/components/common/native-select";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api/endpoints";
import { useImports } from "@/lib/api/hooks";
import type { ImportJob, ImportKind } from "@/lib/api/schemas";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { formatDate } from "@/lib/time";
import { cn } from "@/lib/utils";
import { ParseWarningsTable, countBySeverity } from "./parse-warnings-table";

const KINDS: { kind: ImportKind; icon: LucideIcon; label: MessageKey; desc: MessageKey }[] = [
  { kind: "planning-list", icon: FileSpreadsheet, label: "import.planning", desc: "import.planningDesc" },
  { kind: "exam-list", icon: ListChecks, label: "import.exam", desc: "import.examDesc" },
  { kind: "weekly-grid", icon: Grid3x3, label: "import.grid", desc: "import.gridDesc" },
  { kind: "crbs", icon: Database, label: "import.crbs", desc: "import.crbsDesc" },
];

const STEPS: MessageKey[] = ["import.stepKind", "import.stepUpload", "import.stepPreview", "import.stepDone"];

function Stepper({ step }: { step: number }) {
  const { t } = useI18n();
  return (
    <ol className="mb-6 flex items-center gap-2 text-xs" aria-label="Steps">
      {STEPS.map((key, i) => (
        <li key={key} aria-current={i === step ? "step" : undefined} className="flex items-center gap-2">
          <span className={cn("flex size-6 items-center justify-center rounded-full border font-medium", i < step ? "border-primary bg-primary text-primary-foreground" : i === step ? "border-primary text-primary" : "text-muted-foreground")}>
            {i < step ? <Check className="size-3.5" aria-hidden /> : i + 1}
          </span>
          <span className={cn("hidden sm:inline", i === step ? "font-medium" : "text-muted-foreground")}>{t(key)}</span>
          {i < STEPS.length - 1 ? <span className={cn("h-px w-6 sm:w-10", i < step ? "bg-primary" : "bg-border")} aria-hidden /> : null}
        </li>
      ))}
    </ol>
  );
}

export function ImportWizard() {
  const { t, n, locale } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const kindParam = params.get("kind");
  const kind = KINDS.find((k) => k.kind === kindParam)?.kind ?? null;
  const { term, terms } = useActiveTerm();
  const [termId, setTermId] = useState<number | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dsn, setDsn] = useState("");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<ImportJob | null>(null);
  const [done, setDone] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const imports = useImports();
  const step = !kind ? 0 : job ? (done ? 3 : 2) : 1;
  const effectiveTerm = termId ?? term?.id ?? 1;

  const chooseKind = (k: ImportKind) => {
    setJob(null);
    setDone(false);
    setFile(null);
    router.replace(`/import?kind=${k}`);
  };

  const onFiles = (files: FileList | null) => {
    const f = files?.[0];
    if (!f) return;
    if (!/\.(xlsx|xlsm)$/i.test(f.name)) {
      toast.error("Yalnızca .xlsx");
      return;
    }
    setFile(f);
  };

  const start = async () => {
    if (!kind) return;
    setBusy(true);
    try {
      const j = await api.imports.upload(kind, file, effectiveTerm, kind === "crbs" ? dsn : undefined);
      setJob(j);
      void imports.refetch();
    } finally {
      setBusy(false);
    }
  };

  const canStart = kind === "crbs" ? dsn.trim().length > 3 : file !== null;
  const counts = job ? countBySeverity(job.summary.warnings) : null;

  return (
    <div data-testid="import">
      <PageHeader title={t("import.title")} subtitle={t("import.subtitle")} />
      <Stepper step={step} />

      {step === 0 ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {KINDS.map((k) => (
            <button key={k.kind} type="button" onClick={() => chooseKind(k.kind)} data-testid={`import-kind-${k.kind}`} className="flex gap-3 rounded-xl border bg-card p-4 text-left transition-colors hover:border-primary hover:bg-primary-tint focus-visible:ring-2 focus-visible:ring-ring">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted"><k.icon className="size-5" aria-hidden /></span>
              <span>
                <span className="block font-medium">{t(k.label)}</span>
                <span className="block text-xs text-muted-foreground">{t(k.desc)}</span>
              </span>
            </button>
          ))}
        </div>
      ) : null}

      {step === 1 && kind ? (
        <Card className="max-w-3xl">
          <CardHeader><CardTitle>{t(KINDS.find((k) => k.kind === kind)?.label ?? "import.title")}</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-1.5 sm:max-w-xs">
              <Label htmlFor="term">{t("import.term")}</Label>
              <NativeSelect id="term" value={String(effectiveTerm)} onChange={(e) => setTermId(Number(e.target.value))}>
                {terms.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
              </NativeSelect>
            </div>
            {kind === "crbs" ? (
              <div className="grid gap-1.5">
                <Label htmlFor="dsn">{t("import.dsn")}</Label>
                <Input id="dsn" placeholder="mysql://user:pass@host:3306/crbs" value={dsn} onChange={(e) => setDsn(e.target.value)} autoComplete="off" />
              </div>
            ) : (
              <div
                role="button"
                tabIndex={0}
                aria-label={t("import.dropzone")}
                onClick={() => inputRef.current?.click()}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); inputRef.current?.click(); } }}
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => { e.preventDefault(); setDragging(false); onFiles(e.dataTransfer.files); }}
                className={cn("flex min-h-[200px] cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-6 text-center transition-colors", dragging ? "border-primary bg-primary-tint" : "hover:border-border-strong")}
                data-testid="dropzone"
              >
                <FileUp className={cn("size-8 text-muted-foreground transition-transform", dragging && "-translate-y-1")} aria-hidden />
                {file ? (
                  <p className="text-sm font-medium">{file.name} <span className="text-muted-foreground">· {(file.size / 1024).toFixed(0)} KB</span></p>
                ) : (
                  <>
                    <p className="text-sm font-medium">{t("import.dropzone")}</p>
                    <p className="text-xs text-muted-foreground">{t("import.dropzoneHint")}</p>
                  </>
                )}
                <input ref={inputRef} type="file" accept=".xlsx,.xlsm" className="sr-only" onChange={(e) => onFiles(e.target.files)} data-testid="file-input" />
              </div>
            )}
            <div className="flex items-center justify-between">
              <Button variant="ghost" onClick={() => router.replace("/import")}>{t("common.back")}</Button>
              <Button onClick={() => void start()} disabled={!canStart || busy} data-testid="import-start">
                {busy ? <><Loader2 className="animate-spin" /> {t("import.importing")}</> : t("import.start")}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {(step === 2 || step === 3) && job && counts ? (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-4">
            {[
              ["import.rows", job.summary.rows],
              ["import.created", job.summary.created],
              ["import.skipped", job.summary.skipped],
              ["import.warnings", job.summary.warnings.length],
            ].map(([k, v]) => (
              <div key={String(k)} className="rounded-xl border bg-card p-4">
                <p className="text-xs font-medium uppercase text-muted-foreground">{t(k as MessageKey)}</p>
                <p className="text-3xl font-bold tabular-nums">{n(Number(v))}</p>
              </div>
            ))}
          </div>
          <p className="text-sm text-muted-foreground" aria-live="polite">
            {job.filename} · {n(job.summary.rows)} {t("import.rows").toLocaleLowerCase(locale)} · {counts.error} ✗ · {counts.warning} ⚠ · {counts.info} ℹ
          </p>
          <Card>
            <CardHeader><CardTitle>{t("import.warningsTable")}</CardTitle></CardHeader>
            <CardContent><ParseWarningsTable warnings={job.summary.warnings} /></CardContent>
          </Card>
          <div className="flex flex-wrap items-center gap-2">
            <Button render={<Link href="/requests?status=NEEDS_REVIEW" />} onClick={() => setDone(true)}>{t("import.goRequests")}</Button>
            <Button variant="outline" onClick={() => router.replace("/import")}>{t("import.again")}</Button>
          </div>
        </div>
      ) : null}

      {step === 0 && imports.data && imports.data.length > 0 ? (
        <Card className="mt-6">
          <CardHeader><CardTitle>{t("import.recent")}</CardTitle></CardHeader>
          <CardContent>
            <ul className="divide-y text-sm">
              {imports.data.slice(0, 6).map((j) => (
                <li key={j.id} className="flex items-center justify-between gap-3 py-2">
                  <span className="min-w-0 truncate">{j.filename}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">{t(KINDS.find((k) => k.kind === j.kind)?.label ?? "import.title")} · {n(j.summary.rows)} · {formatDate(j.created_at.slice(0, 10), locale)}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
