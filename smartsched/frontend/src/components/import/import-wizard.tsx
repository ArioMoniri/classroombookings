"use client";

import { serverTermMismatch, termMismatch } from "./term-hint";
import { Check, ChevronRight, Database, FileSpreadsheet, Grid3x3, ListChecks, Warehouse, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
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
import { dropStage, helperFilesApi, isStageGone, sidOf, type FileCard, type Stage } from "@/lib/api/helper-files";
import { fileHandoffHref, handedFile, useFileHandoffStore, useHelperFileHandoff } from "@/components/helper/file-handoff";
import { KIND_KEYS } from "@/components/helper/kind-labels";
import { KindDrop } from "./kind-drop";
import { HandedFileExpired, HandedFileRow } from "@/components/helper/handed-file-row";
import { MagneticDrop, type UploadState } from "./magnetic-drop";
import { useImports } from "@/lib/api/hooks";
import type { ImportJob, ImportKind } from "@/lib/api/schemas";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { ParseWarningsTable, TruncatedWarnings, countBySeverity } from "./parse-warnings-table";
import { CrbsUpgrade } from "./crbs-upgrade";
import { RoomMasterImport, type FlowStep } from "./room-master-import";
import { BareButton } from "@/components/shell/bare-button";
import { ImportHistory } from "./import-history";
import { ImportPreview } from "./import-preview";

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
    <ol className="mb-6 flex items-center gap-2 type-footnote" aria-label={t("glass.import.steps")}>
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

/** step 0: the file and the server's params go into the hand-over slot (the same path as the helper's card) */
function handOverDetected(f: File, c: FileCard, params: Record<string, string | number | boolean>, st: Stage | null) {
  const exp = st ? Date.parse(st.expires_at) : NaN;
  useFileHandoffStore.getState().set(
    { featureId: "import", kind: c.kind ?? null, params, items: [{ token: st?.upload_token ?? null, sid: st ? sidOf(st) : null, name: f.name, size: f.size, format: st?.format ?? null, expiresAt: Number.isFinite(exp) ? exp : null }], at: Date.now() },
    [f],
  );
}

export function ImportWizard() {
  const { t, n, locale } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const kindParam = params.get("kind");
  const kind = KINDS.find((k) => k.kind === kindParam)?.kind ?? null;
  const { term, terms } = useActiveTerm();
  // HB-23c: `term` (and `year`) in the address preset the target term (the helper's card carries the file's term)
  const termParam = Number(params.get("term")) || null;
  const yearParam = Number(params.get("year")) || undefined;
  const [termId, setTermId] = useState<number | null>(null);
  /** HB-23c: the file the helper handed over (a staged token, never in the address); shown with `from=helper` only */
  const fromHelper = params.get("from") === "helper";
  const handed = useHelperFileHandoff("import", { kind });
  const handedRaw = fromHelper ? (handed.handoff?.items[0] ?? null) : null;
  // HELPER_FILE_STAGE=off: no token, the browser's File itself (gone after a reload: same as expired)
  const handedBytes = handedRaw && !handedRaw.token ? handedFile(handedRaw) : null;
  const handedLost = !!handedRaw && !handedRaw.token && !handedBytes;
  const handedItem = handedRaw && !handed.expired && !handedLost ? handedRaw : null;
  const handedExpired = !!handedRaw && (handed.expired || handedLost);
  /** HB-23c step 0: what the helper read ("Dosyanız bir planlama listesi (sütunlar: …)"), shown above the file row */
  const [detected, setDetected] = useState<{ label: string; likely: boolean; evidence: string | null; warning: string | null } | null>(null);
  const [detecting, setDetecting] = useState(false);
  /** HB-23c step 1 (M-20): the classify of the person's own file; its stage spares the second upload */
  const [probe, setProbe] = useState<{ file: File; stage: Stage | null; kind: string | null } | null>(null);
  // KVKK N2: the check's stage never outlives the page (leaving it drops the stage the person no longer needs)
  const probeRef = useRef(probe);
  useEffect(() => {
    probeRef.current = probe;
  }, [probe]);
  useEffect(() => () => dropStage(probeRef.current?.stage), []);
  const fileRef = useRef<File | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [upload, setUpload] = useState<UploadState>({ phase: "idle" });
  const [flow, setFlow] = useState<FlowStep>("upload");
  /** the kind the server says the file is (wrong-file refusal, admin persona M-20) */
  const [suggested, setSuggested] = useState<ImportKind | null>(null);
  const busy = upload.phase === "uploading" || upload.phase === "processing";
  /** RF-06: every workbook upload is a preview first (`dry_run`); `job` is the applied import */
  const [preview, setPreview] = useState<ImportJob | null>(null);
  const [job, setJob] = useState<ImportJob | null>(null);
  const reportRef = useRef<HTMLHeadingElement>(null);
  const imports = useImports();
  const reviewed = kind !== null && REVIEWED.includes(kind);
  const step = !kind ? 0 : reviewed ? FLOW_STEP[flow] : job ? 3 : preview ? 2 : 1;
  const effectiveTerm = termId ?? (termParam && terms.some((x) => x.id === termParam) ? termParam : null) ?? term?.id ?? 1;
  const focusZone = () => requestAnimationFrame(() => document.querySelector('[data-testid="import-dropzone"]')?.querySelector<HTMLElement>('button:not([disabled]), [tabindex="0"]')?.focus());
  // the handed-over file is here: the page's own primary ("Önizle") takes the focus (§10)
  const handedToken = handedItem ? (handedItem.token ?? `file:${handedItem.name}`) : null;
  useEffect(() => {
    if (!handedToken) return;
    const id = requestAnimationFrame(() => document.querySelector<HTMLElement>('[data-testid="import-start"]:not([disabled])')?.focus());
    return () => cancelAnimationFrame(id);
  }, [handedToken]);
  // the token ran out on this page: the zone comes back and takes the focus
  useEffect(() => {
    if (handedExpired) focusZone();
  }, [handedExpired]);
  const removeHanded = () => {
    setDetected(null);
    handed.remove();
    focusZone();
  };

  const chooseKindReset = () => {
    setFlow("upload");
    router.replace("/import");
  };

  const chooseKind = (k: ImportKind) => {
    setDetected(null);
    setJob(null);
    setPreview(null);
    setFile(null);
    setUpload({ phase: "idle" });
    setFlow("upload");
    setSuggested(null);
    router.replace(`/import?kind=${k}`);
  };

  /** a preview from the history that was never applied */
  const openPreview = (j: ImportJob) => {
    setJob(null);
    setPreview(j);
    setFlow("upload");
    router.replace(`/import?kind=${j.kind}`);
  };

  const cancelPreview = () => {
    setPreview(null);
    setFile(null);
    setUpload({ phase: "idle" });
    // E2EA2-F03: the preview unmounts; focus goes to the drop zone's first control, never to <body>
    requestAnimationFrame(() => document.querySelector('[data-testid="import-dropzone"]')?.querySelector<HTMLElement>('button:not([disabled]), [tabindex="0"]')?.focus());
  };

  /** keep the file and import it as the kind the server recognised */
  const switchKind = (k: ImportKind) => {
    setUpload({ phase: "idle" });
    setSuggested(null);
    router.replace(`/import?kind=${k}`);
  };

  const onFile = (f: File | null) => {
    if (handed.handoff) handed.consumed();
    if (probe && probe.file !== f) {
      dropStage(probe.stage);
      setProbe(null);
    }
    fileRef.current = f;
    setUpload({ phase: "idle" });
    setSuggested(null);
    if (f && !/\.(xlsx|xlsm)$/i.test(f.name)) {
      toast.error(t("glass.import.onlyXlsx"));
      return;
    }
    setFile(f);
    if (f) void probeFile(f);
  };

  /** classify the picked file before the upload: a different importer kind offers "… olarak içe aktar" at once */
  const probeFile = async (f: File) => {
    let out: Awaited<ReturnType<typeof helperFilesApi.classify>> | null = null;
    try {
      out = await helperFilesApi.classify(f, { lang: locale, termId: effectiveTerm, context: "import" });
    } catch {
      return; // no answer: the page uploads as before and the server's own check stays
    }
    if (fileRef.current !== f) {
      dropStage(out.stage);
      return;
    }
    const c = out.card;
    const importer = c.type === "file" && c.state === "detected" && c.primary?.feature_id === "import" ? String(c.primary.params.kind ?? "") : null;
    const known = KINDS.find((k) => k.kind === importer)?.kind ?? null;
    setProbe({ file: f, stage: out.stage ?? null, kind: known });
    if (known && known !== kind) {
      setSuggested(known);
      setUpload({ phase: "error", message: t("importFlows.wrongFile", { kind: t(KINDS.find((k) => k.kind === known)!.label) }) });
    }
  };

  /** step 0: "Türünü bilmiyor musunuz?" — a clear importer answer selects the kind and keeps the file (no sheet) */
  const detectKind = async (f: File) => {
    setDetecting(true);
    let out: Awaited<ReturnType<typeof helperFilesApi.classify>> | null = null;
    try {
      out = await helperFilesApi.classify(f, { lang: locale, termId: term?.id ?? null, context: "import" });
    } catch {
      out = null;
    } finally {
      setDetecting(false);
    }
    const c = out?.card;
    const params = c?.type === "file" && c.state === "detected" && c.primary?.feature_id === "import" ? c.primary.params : null;
    const target = params ? KINDS.find((k) => k.kind === params.kind && !REVIEWED.includes(k.kind)) : undefined;
    if (out && c?.type === "file" && params && target && (out.stage || out.resend)) {
      handOverDetected(f, c, params, out.stage ?? null);
      setDetected(detectionOf(c));
      router.replace(fileHandoffHref("import", params) ?? `/import?kind=${target.kind}`);
      return;
    }
    // ambiguous, unknown, another page, a refusal: the helper shows its card
    const { adoptClassified } = await import("@/components/helper/file-router");
    adoptClassified(f, out);
  };

  const detectionOf = (c: FileCard) => {
    const label = c.kind && KIND_KEYS[c.kind] ? t(KIND_KEYS[c.kind]!) : "";
    const lines = c.evidence[locale] ?? c.evidence.tr ?? [];
    const mismatch = c.warnings.find((w) => w.code === "term_mismatch");
    return { label: label.toLocaleLowerCase(locale === "tr" ? "tr-TR" : "en-GB"), likely: c.certainty !== "sure", evidence: lines[0] ?? null, warning: mismatch ? (locale === "tr" ? mismatch.message.tr : mismatch.message.en) : null };
  };

  /** Real progress: bytes from XMLHttpRequest, then the server's parse (no fake percentages). */
  const start = async () => {
    if (!kind) return;
    const t0 = terms.find((x) => x.id === effectiveTerm) ?? term;
    if (!t0) return;
    // the step-1 probe staged this very file for this kind: send its token, not the bytes again
    const probeToken = !handedItem && probe && probe.file === file && probe.kind === kind && probe.stage && Date.parse(probe.stage.expires_at) > Date.now() ? probe.stage.upload_token : null;
    const token = handedItem?.token ?? probeToken;
    // the bytes go this time: the check's stage is not needed any more (KVKK N2)
    if (!probeToken && probe?.stage) {
      dropStage(probe.stage);
      setProbe({ ...probe, stage: null });
    }
    // a staged file has no bytes to send: straight to "the server reads it"
    setUpload(token ? { phase: "processing" } : { phase: "uploading", pct: 0 });
    try {
      const j = await uploadImportWithProgress(kind, token ? null : (handedBytes ?? file), t0, {
        dryRun: true,
        ...(token ? { uploadToken: token, filename: handedItem?.name ?? file?.name } : {}),
        year: yearParam,
        onProgress: ({ loaded, total }) => {
          const pct = total ? Math.round((loaded / total) * 100) : 0;
          setUpload(pct >= 100 ? { phase: "processing" } : { phase: "uploading", pct });
        },
      });
      setUpload({ phase: "done" });
      if (handedItem) handed.consumed();
      if (probeToken) setProbe(null);
      setPreview(j);
      void imports.refetch();
    } catch (e) {
      if (handedItem?.token && isStageGone(e)) {
        setUpload({ phase: "idle" });
        handed.markExpired();
        return;
      }
      if (probeToken && isStageGone(e)) {
        // the probe's stage ran out: the bytes go after all
        setProbe(null);
        setUpload({ phase: "idle" });
        return;
      }
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

  const canStart = file !== null || !!handedItem;
  const counts = job ? countBySeverity(job.summary.warnings) : null;

  return (
    <div data-testid="import">
      <PageHeader title={t("import.title")} subtitle={t("import.subtitle")} />
      <Stepper step={step} />

      {step === 0 ? <KindDrop onFile={(f) => void detectKind(f)} busy={detecting} /> : null}
      {step === 0 ? (
        <Card className="max-w-3xl">
          <CardContent>
            <ul>
              {KINDS.map((k) => (
                <li key={k.kind} className="[&:not(:last-child)]:hairline-b">
                  <BareButton onClick={() => chooseKind(k.kind)} data-testid={`import-kind-${k.kind}`} className="-mx-2 flex w-[calc(100%+1rem)] items-center gap-3 rounded-xl px-2 py-3 text-left hover:bg-fill-3">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-[10px] bg-fill-2 text-label-1"><k.icon className="size-[18px] stroke-[1.75]" aria-hidden /></span>
                    <span className="min-w-0 flex-1">
                      <span className="block type-body font-medium text-label-1">{t(k.label)}</span>
                      <span className="block type-callout text-label-2">{t(k.desc)}</span>
                    </span>
                    <ChevronRight className="size-4 text-label-3" aria-hidden />
                  </BareButton>
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
            {handedItem && detected ? (
              <div className="flex flex-col gap-1 rounded-xl bg-fill-3 px-3 py-2" data-testid="import-detected" role="status">
                <p className="flex items-center gap-1.5 type-callout font-medium text-label-1">
                  <Check aria-hidden className="size-4 text-status-feasible-fg" />
                  {t(detected.likely ? "helper.file.yourFileLikely" : "helper.file.yourFile", { kind: detected.label })}
                </p>
                {detected.evidence ? <p className="type-footnote text-label-2">{detected.evidence}</p> : null}
                {detected.warning ? <p className="type-footnote text-status-warning-fg">{detected.warning}</p> : null}
              </div>
            ) : null}
            {handedItem ? (
              <HandedFileRow item={handedItem} onRemove={removeHanded} />
            ) : (
              <>
                {handedExpired ? <HandedFileExpired /> : null}
                <MagneticDrop files={file ? [file] : []} onFiles={(f) => onFile(f[0] ?? null)} upload={upload} disabled={busy} />
                <p className="type-caption text-label-2" data-testid="import-privacy">{t("helper.file.privacyRead")}</p>
              </>
            )}
            {suggested ? (
              <Button variant="outline" size="sm" onClick={() => switchKind(suggested)} data-testid="import-switch-kind">
                {t("importFlows.importAs", { kind: t(KINDS.find((k) => k.kind === suggested)!.label) })}
              </Button>
            ) : null}
            <div className="flex items-center justify-between">
              <Button variant="ghost" onClick={() => router.replace("/import")}>{t("common.back")}</Button>
              <Button onClick={() => void start()} {...busyProps(busy, !canStart)} data-testid="import-start">
                <BusyLabel busy={busy} label={upload.phase === "processing" ? t("rf.preview.reading") : t("import.importing")}>{t("rf.preview.start")}</BusyLabel>
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {step === 2 && kind && !reviewed && preview ? (
        <ImportPreview
          key={preview.id}
          job={preview}
          termWarning={serverTermMismatch(preview.summary.term_check) ?? (preview.summary.term_check ? null : termMismatch(preview.filename, terms.find((x) => x.id === effectiveTerm), terms))}
          onCancel={cancelPreview}
          onApplied={(j) => {
            setJob(j);
            void imports.refetch();
            requestAnimationFrame(() => reportRef.current?.focus());
          }}
        />
      ) : null}

      {!reviewed && step === 3 && job && counts ? (
        <div className="space-y-5" data-testid="import-report">
          <Card>
            <CardHeader>
              <CardTitle>
                <h2 ref={reportRef} tabIndex={-1} className="outline-hidden">{job.filename}</h2>
              </CardTitle>
              <p className="type-callout text-label-2" aria-live="polite">
                {/* E2EA-F08: the updated count too (an unchanged grid re-import rewrites rows without creating any) */}
                {t("glass.import.summary", { rows: n(job.summary.rows), created: n(job.summary.created), updated: n(job.summary.updated), skipped: n(job.summary.skipped) })}
              </p>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-5">
                {[
                  [t("import.rows"), job.summary.rows],
                  [t("import.created"), job.summary.created],
                  [t("import.updated"), job.summary.updated],
                  [t("import.skipped"), job.summary.skipped],
                  [t("import.warnings"), job.summary.warnings_count ?? job.summary.warnings.length],
                ].map(([k, v]) => (
                  <div key={String(k)}>
                    <dt className="type-footnote text-label-3">{k}</dt>
                    <dd className="type-title-2 leading-7 font-semibold tracking-[-0.017em] text-label-1 tabular-nums">{n(Number(v))}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-3 type-callout text-label-2">{t("glass.import.bySeverity", { e: n(counts.error), w: n(counts.warning), i: n(counts.info) })}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>{t("import.warningsTable")}</CardTitle></CardHeader>
            <CardContent className="space-y-3"><TruncatedWarnings summary={job.summary} /><ParseWarningsTable warnings={job.summary.warnings} groups={job.summary.warning_groups} /></CardContent>
          </Card>
          <div className="flex flex-wrap items-center gap-2">
            <Button nativeButton={false} render={<Link href="/requests?status=NEEDS_REVIEW" />}>{t("import.goRequests")}</Button>
            <Button variant="outline" onClick={() => (setJob(null), cancelPreview(), router.replace("/import"))}>{t("import.again")}</Button>
          </div>
        </div>
      ) : null}

      {step === 0 && imports.data ? <ImportHistory jobs={imports.data} onOpenPreview={openPreview} /> : null}
    </div>
  );
}
