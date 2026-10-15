"use client";

import { Check, ChevronRight, Database, FileSpreadsheet, Grid3x3, ListChecks, Warehouse, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { NativeSelect } from "@/components/common/native-select";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { HttpError } from "@/lib/api/client";
import { uploadImportWithProgress } from "@/lib/api/shell-extra";
import { MagneticDrop, type UploadState } from "./magnetic-drop";
import { useImports } from "@/lib/api/hooks";
import type { ImportJob, ImportKind } from "@/lib/api/schemas";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { formatDate } from "@/lib/time";
import { cn } from "@/lib/utils";
import { ParseWarningsTable, countBySeverity } from "./parse-warnings-table";
import { CrbsUpgrade } from "./crbs-upgrade";
import { RoomMasterImport, type FlowStep } from "./room-master-import";

const KINDS: { kind: ImportKind; icon: LucideIcon; label: MessageKey; desc: MessageKey }[] = [
  { kind: "planning-list", icon: FileSpreadsheet, label: "import.planning", desc: "import.planningDesc" },
  { kind: "exam-list", icon: ListChecks, label: "import.exam", desc: "import.examDesc" },
  { kind: "weekly-grid", icon: Grid3x3, label: "import.grid", desc: "import.gridDesc" },
  { kind: "room-master", icon: Warehouse, label: "importFlows.roomMaster.kind", desc: "importFlows.roomMaster.kindDesc" },
  { kind: "crbs", icon: Database, label: "import.crbs", desc: "import.crbsDesc" },
];
/** kinds with their own review step before anything is written (dry run / diff, then confirm) */
const REVIEWED: readonly ImportKind[] = ["room-master", "crbs"];
const FLOW_STEP: Record<FlowStep, number> = { upload: 1, preview: 2, done: 3 };

const STEPS: MessageKey[] = ["import.stepKind", "import.stepUpload", "import.stepPreview", "import.stepDone"];

function Stepper({ step }: { step: number }) {
  const { t } = useI18n();
  return (
    <ol className="mb-6 flex items-center gap-2 text-[12px]" aria-label={t("glass.import.steps")}>
      {STEPS.map((key, i) => (
        <li key={key} aria-current={i === step ? "step" : undefined} className="flex items-center gap-2">
          <span className={cn("flex size-6 items-center justify-center rounded-full font-semibold tabular-nums", i < step ? "bg-tint text-tint-foreground" : i === step ? "bg-tint-soft text-tint-text" : "bg-fill-2 text-label-3")}>
            {i < step ? <Check className="size-3.5" aria-hidden /> : i + 1}
          </span>
          <span className={cn("hidden sm:inline", i === step ? "font-medium text-label-1" : "text-label-3")}>{t(key)}</span>
          {i < STEPS.length - 1 ? <span className={cn("h-px w-6 sm:w-10", i < step ? "bg-tint" : "bg-hairline-strong")} aria-hidden /> : null}
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
  const [upload, setUpload] = useState<UploadState>({ phase: "idle" });
  const [flow, setFlow] = useState<FlowStep>("upload");
  /** the kind the server says the file is (wrong-file refusal, admin persona M-20) */
  const [suggested, setSuggested] = useState<ImportKind | null>(null);
  const busy = upload.phase === "uploading" || upload.phase === "processing";
  const [job, setJob] = useState<ImportJob | null>(null);
  const [done, setDone] = useState(false);
  const imports = useImports();
  const reviewed = kind !== null && REVIEWED.includes(kind);
  const step = !kind ? 0 : reviewed ? FLOW_STEP[flow] : job ? (done ? 3 : 2) : 1;
  const effectiveTerm = termId ?? term?.id ?? 1;

  const chooseKindReset = () => {
    setFlow("upload");
    router.replace("/import");
  };

  const chooseKind = (k: ImportKind) => {
    setJob(null);
    setDone(false);
    setFile(null);
    setUpload({ phase: "idle" });
    setFlow("upload");
    setSuggested(null);
    router.replace(`/import?kind=${k}`);
  };

  /** keep the file and import it as the kind the server recognised */
  const switchKind = (k: ImportKind) => {
    setUpload({ phase: "idle" });
    setSuggested(null);
    router.replace(`/import?kind=${k}`);
  };

  const onFile = (f: File | null) => {
    setUpload({ phase: "idle" });
    setSuggested(null);
    if (f && !/\.(xlsx|xlsm)$/i.test(f.name)) {
      toast.error(t("glass.import.onlyXlsx"));
      return;
    }
    setFile(f);
  };

  /** Real progress: bytes from XMLHttpRequest, then the server's parse (no fake percentages). */
  const start = async () => {
    if (!kind) return;
    const t0 = terms.find((x) => x.id === effectiveTerm) ?? term;
    if (!t0) return;
    setUpload({ phase: "uploading", pct: 0 });
    try {
      const j = await uploadImportWithProgress(kind, file, t0, {
        onProgress: ({ loaded, total }) => {
          const pct = total ? Math.round((loaded / total) * 100) : 0;
          setUpload(pct >= 100 ? { phase: "processing" } : { phase: "uploading", pct });
        },
      });
      setUpload({ phase: "done" });
      setJob(j);
      void imports.refetch();
    } catch (e) {
      const status = e instanceof HttpError ? e.status : 0;
      // a FAILED job comes back as the detail: the server's reason and, for a wrong file, what it looks like
      const failed = e instanceof HttpError && e.detail && typeof e.detail === "object" && "summary" in e.detail ? (e.detail as ImportJob) : null;
      const detected = KINDS.find((k) => k.kind === failed?.summary.detected_kind && k.kind !== kind)?.kind ?? null;
      setSuggested(detected);
      setUpload({
        phase: "error",
        message: detected
          ? t("importFlows.wrongFile", { kind: t(KINDS.find((k) => k.kind === detected)!.label) })
          : status === 413
            ? t("glass.import.tooLarge")
            : status === 0
              ? t("glass.auth.offline")
              : status === 409
                ? t("importFlows.locked")
                : status === 400 || status === 422
                  ? t("glass.import.badFile")
                  : t("glass.import.failed"),
      });
    }
  };

  const canStart = file !== null;
  const counts = job ? countBySeverity(job.summary.warnings) : null;

  return (
    <div data-testid="import">
      <PageHeader title={t("import.title")} subtitle={t("import.subtitle")} />
      <Stepper step={step} />

      {step === 0 ? (
        <Card className="max-w-3xl">
          <CardContent>
            <ul>
              {KINDS.map((k) => (
                <li key={k.kind} className="[&:not(:last-child)]:hairline-b">
                  <button type="button" onClick={() => chooseKind(k.kind)} data-testid={`import-kind-${k.kind}`} className="-mx-2 flex w-[calc(100%+1rem)] items-center gap-3 rounded-xl px-2 py-3 text-left outline-hidden hover:bg-fill-3 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-[10px] bg-fill-2 text-label-1"><k.icon className="size-[18px] stroke-[1.75]" aria-hidden /></span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-[14px] font-medium text-label-1">{t(k.label)}</span>
                      <span className="block text-[12.5px] text-label-2">{t(k.desc)}</span>
                    </span>
                    <ChevronRight className="size-4 text-label-3" aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      {kind && reviewed ? (
        kind === "crbs" ? (
          <CrbsUpgrade onStep={setFlow} onBack={() => chooseKindReset()} />
        ) : (
          <RoomMasterImport term={terms.find((x) => x.id === effectiveTerm) ?? term ?? null} onStep={setFlow} onBack={() => chooseKindReset()} />
        )
      ) : null}

      {step === 1 && kind && !reviewed ? (
        <Card className="max-w-3xl">
          <CardHeader><CardTitle>{t(KINDS.find((k) => k.kind === kind)?.label ?? "import.title")}</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-1.5 sm:max-w-xs">
              <Label htmlFor="term">{t("import.term")}</Label>
              <NativeSelect id="term" value={String(effectiveTerm)} onChange={(e) => setTermId(Number(e.target.value))}>
                {terms.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
              </NativeSelect>
            </div>
            <MagneticDrop files={file ? [file] : []} onFiles={(f) => onFile(f[0] ?? null)} upload={upload} disabled={busy} />
            {suggested ? (
              <Button variant="outline" size="sm" onClick={() => switchKind(suggested)} data-testid="import-switch-kind">
                {t("importFlows.importAs", { kind: t(KINDS.find((k) => k.kind === suggested)!.label) })}
              </Button>
            ) : null}
            <div className="flex items-center justify-between">
              <Button variant="ghost" onClick={() => router.replace("/import")}>{t("common.back")}</Button>
              <Button onClick={() => void start()} {...busyProps(busy, !canStart)} data-testid="import-start">
                <BusyLabel busy={busy} label={upload.phase === "processing" ? t("glass.import.reading") : t("import.importing")}>{t("import.start")}</BusyLabel>
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {!reviewed && (step === 2 || step === 3) && job && counts ? (
        <div className="space-y-5" data-testid="import-report">
          <Card>
            <CardHeader>
              <CardTitle>{job.filename}</CardTitle>
              <p className="text-[13px] text-label-2" aria-live="polite">
                {t("glass.import.summary", { rows: n(job.summary.rows), created: n(job.summary.created), skipped: n(job.summary.skipped) })}
              </p>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
                {[
                  [t("import.rows"), job.summary.rows],
                  [t("import.created"), job.summary.created],
                  [t("import.skipped"), job.summary.skipped],
                  [t("import.warnings"), job.summary.warnings.length],
                ].map(([k, v]) => (
                  <div key={String(k)}>
                    <dt className="text-[12px] text-label-3">{k}</dt>
                    <dd className="text-[22px] leading-7 font-semibold tracking-[-0.017em] text-label-1 tabular-nums">{n(Number(v))}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-3 text-[12.5px] text-label-2">{t("glass.import.bySeverity", { e: n(counts.error), w: n(counts.warning), i: n(counts.info) })}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>{t("import.warningsTable")}</CardTitle></CardHeader>
            <CardContent><ParseWarningsTable warnings={job.summary.warnings} /></CardContent>
          </Card>
          <div className="flex flex-wrap items-center gap-2">
            <Button nativeButton={false} render={<Link href="/requests?status=NEEDS_REVIEW" />} onClick={() => setDone(true)}>{t("import.goRequests")}</Button>
            <Button variant="outline" onClick={() => router.replace("/import")}>{t("import.again")}</Button>
          </div>
        </div>
      ) : null}

      {step === 0 && imports.data && imports.data.length > 0 ? (
        <Card className="mt-6 max-w-3xl">
          <CardHeader><CardTitle>{t("import.recent")}</CardTitle></CardHeader>
          <CardContent>
            <ul className="text-[13px]">
              {imports.data.slice(0, 6).map((j) => (
                <li key={j.id} className="flex items-center justify-between gap-3 py-2 [&:not(:last-child)]:hairline-b">
                  <span className="min-w-0 truncate text-label-1">{j.filename}</span>
                  <span className="shrink-0 text-[12px] text-label-3">{t(KINDS.find((k) => k.kind === j.kind)?.label ?? "import.title")} · {n(j.summary.rows)} · {formatDate(j.created_at.slice(0, 10), locale)}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
