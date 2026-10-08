"use client";

import { AlertTriangle, CheckCircle2, FileUp, Loader2, RotateCcw, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useRef, useState, type DragEvent } from "react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api/endpoints";
import { HttpError } from "@/lib/api/client";
import type { Extraction, MappingColumns, MappingProposals, MappingSpec } from "@/lib/api/studio-schemas";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { MappingStep } from "./mapping-step";
import { useStudio } from "./studio-context";
import type { TrayItem } from "./studio-store";

export const ACCEPT = [".xlsx", ".xlsm", ".csv", ".docx", ".pdf", ".txt", ".md"];
export const MAX_FILES = 10;
export const MAX_BYTES = 20 * 1024 * 1024;
const TABULAR = /\.(xlsx|xlsm|csv)$/i;

type Stage = "uploading" | "reading" | "ready" | "mapping" | "error" | "rejected";
interface FileRow {
  id: string;
  file: File;
  stage: Stage;
  percent: number;
  message?: string;
  counts?: { ready: number; look: number; unread: number };
  planningList?: boolean;
}

export function extOf(name: string): string {
  const m = /\.[^.]+$/.exec(name);
  return m ? m[0].toLowerCase() : "";
}

/** Client-side check before uploading (type and size), with a plain reason. */
export function rejectReason(file: File, t: (k: "studio.upload.badType" | "studio.upload.tooBig", v?: Record<string, string | number>) => string): string | null {
  const ext = extOf(file.name);
  if (!ACCEPT.includes(ext)) return t("studio.upload.badType", { ext: ext || "?" });
  if (file.size > MAX_BYTES) return t("studio.upload.tooBig", { mb: 20 });
  return null;
}

/** Turn an extraction (AI reader or column mapping) into review-tray items. */
export function toTrayItems(res: Pick<Extraction, "proposals" | "section_edits" | "unparsed">, file: string, prefix: string): TrayItem[] {
  return [
    ...res.proposals.filter((p) => p.status !== "rejected").map((proposal, i): TrayItem => ({ key: `${prefix}-r${i}`, origin: "upload", file, state: "pending", type: "rule", proposal })),
    ...res.section_edits.map((edit, i): TrayItem => ({ key: `${prefix}-e${i}`, origin: "upload", file, state: "pending", type: "edit", edit })),
    ...res.unparsed.map((unparsed, i): TrayItem => ({ key: `${prefix}-u${i}`, origin: "upload", file, state: "pending", type: "unparsed", unparsed })),
  ];
}

/** (c) Upload preference files: dropzone + per-file stage line (real upload %, then server reading). */
export function UploadPanel({ onClose }: { onClose: () => void }) {
  const { t, locale } = useI18n();
  const { termId, store } = useStudio();
  const [rows, setRows] = useState<FileRow[]>([]);
  const [tab, setTab] = useState<"files" | "paste">("files");
  const [paste, setPaste] = useState("");
  const [pasting, setPasting] = useState(false);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const patch = (id: string, p: Partial<FileRow>) => setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...p } : r)));

  const ingest = useCallback(
    (id: string, file: File, res: Pick<Extraction, "proposals" | "section_edits" | "unparsed"> & { warnings?: string[] }) => {
      const items = toTrayItems(res, file.name, `up-${id}`);
      store.getState().addTray(items);
      const ready = items.filter((i) => (i.type === "rule" ? i.proposal.status === "ok" : i.type === "edit" ? i.edit.status === "ok" : false)).length;
      const unread = items.filter((i) => i.type === "unparsed").length;
      const planningList = (res.warnings ?? []).some((w) => /planning list|planlama listesi|shape a/i.test(w));
      patch(id, { stage: "ready", percent: 100, counts: { ready, look: items.length - ready - unread, unread }, planningList, message: (res.warnings ?? []).join(" ") || undefined });
    },
    [store],
  );

  const upload = useCallback(
    async (id: string, file: File) => {
      patch(id, { stage: "uploading", percent: 0, message: undefined });
      try {
        const res = await api.studio.uploadPreferences(termId, file, locale, (p) => patch(id, { stage: p.stage, percent: p.percent }));
        ingest(id, file, res);
      } catch (e) {
        if (e instanceof HttpError && e.status === 409) {
          if (TABULAR.test(file.name)) patch(id, { stage: "mapping", percent: 100 });
          else patch(id, { stage: "error", message: t("studio.upload.needsAi") });
          return;
        }
        const scan = e instanceof HttpError && /no text|scan/i.test(e.message);
        patch(id, { stage: "error", message: scan ? t("studio.upload.scanned") : e instanceof Error ? e.message : String(e) });
      }
    },
    [termId, locale, ingest, t],
  );

  const addFiles = (list: FileList | File[]) => {
    const files = Array.from(list).slice(0, Math.max(0, MAX_FILES - rows.length));
    const next = files.map((file, i): FileRow => {
      const reason = rejectReason(file, t);
      return { id: `${Date.now()}-${i}`, file, stage: reason ? "rejected" : "uploading", percent: 0, message: reason ?? undefined };
    });
    setRows((rs) => [...rs, ...next]);
    for (const r of next) if (r.stage !== "rejected") void upload(r.id, r.file);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(false);
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  };

  const readPaste = async () => {
    if (!paste.trim()) return;
    setPasting(true);
    const id = `paste-${Date.now()}`;
    const file = new File([paste], t("studio.upload.pasted"), { type: "text/plain" });
    setRows((rs) => [...rs, { id, file, stage: "reading", percent: 100 }]);
    try {
      const res = await api.studio.elicit(termId, paste, locale);
      ingest(id, file, res);
      setPaste("");
    } catch (e) {
      patch(id, { stage: "error", message: e instanceof HttpError && e.status === 409 ? t("studio.write.noKey") : e instanceof Error ? e.message : String(e) });
    } finally {
      setPasting(false);
    }
  };

  const stageLabel = (r: FileRow) => {
    switch (r.stage) {
      case "uploading":
        return t("studio.upload.stage.uploading", { pct: r.percent });
      case "reading":
        return t("studio.upload.stage.reading");
      case "ready":
        return t("studio.upload.stage.ready", { ready: r.counts?.ready ?? 0, look: r.counts?.look ?? 0, unread: r.counts?.unread ?? 0 });
      case "mapping":
        return t("studio.upload.stage.mapping");
      default:
        return r.message ?? t("common.error");
    }
  };

  return (
    <section aria-labelledby="upload-title" className="space-y-3 rounded-xl border bg-card p-3 sm:p-4" data-testid="upload-panel">
      <div className="flex items-center gap-2">
        <h3 id="upload-title" className="flex-1 text-sm font-semibold">
          {t("studio.add.upload")}
        </h3>
        <Button size="icon-sm" variant="ghost" onClick={onClose} aria-label={t("common.close")}>
          <X aria-hidden />
        </Button>
      </div>
      <Tabs value={tab} onValueChange={(v) => setTab(v as "files" | "paste")}>
        <TabsList>
          <TabsTrigger value="files">{t("studio.upload.tabFiles")}</TabsTrigger>
          <TabsTrigger value="paste">{t("studio.upload.tabPaste")}</TabsTrigger>
        </TabsList>
      </Tabs>
      {tab === "files" ? (
        <div
          onDragEnter={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragOver={(e) => e.preventDefault()}
          onDragLeave={() => setDrag(false)}
          onDrop={onDrop}
          className={cn("flex flex-col items-center gap-2 rounded-[var(--radius-lg)] border-2 border-dashed p-5 text-center", drag ? "border-primary bg-tint-soft" : "border-border")}
        >
          <FileUp className="size-6 text-label-2" aria-hidden />
          <p className="text-sm">{drag ? t("studio.upload.release") : t("studio.upload.drop")}</p>
          <p className="text-xs text-label-2">{t("studio.upload.limits", { files: MAX_FILES, mb: 20 })}</p>
          <Button size="sm" variant="outline" onClick={() => input.current?.click()} data-testid="upload-choose">
            {t("studio.upload.choose")}
          </Button>
          <input
            ref={input}
            type="file"
            multiple
            accept={ACCEPT.join(",")}
            className="sr-only"
            tabIndex={-1}
            aria-hidden
            data-testid="upload-input"
            onChange={(e) => {
              if (e.target.files) addFiles(e.target.files);
              e.target.value = "";
            }}
          />
          <p className="text-xs text-label-2">{t("studio.upload.examples")}</p>
        </div>
      ) : (
        <div className="space-y-2">
          <Textarea rows={5} value={paste} onChange={(e) => setPaste(e.target.value)} placeholder={t("studio.upload.pastePlaceholder")} aria-label={t("studio.upload.tabPaste")} lang={locale} />
          <Button size="sm" onClick={() => void readPaste()} disabled={!paste.trim() || pasting}>
            {pasting ? <Loader2 className="animate-spin" aria-hidden /> : null} {t("studio.upload.readPaste")}
          </Button>
        </div>
      )}
      {rows.length ? (
        <ul className="space-y-2" aria-label={t("studio.upload.files")}>
          {rows.map((r) => (
            <li key={r.id} className="rounded-md border p-2" data-testid="upload-row" data-stage={r.stage}>
              <div className="flex items-center gap-2 text-sm">
                {r.stage === "ready" ? <CheckCircle2 className="size-4 text-status-feasible-fg" aria-hidden /> : r.stage === "error" || r.stage === "rejected" ? <AlertTriangle className="size-4 text-status-infeasible-fg" aria-hidden /> : r.stage === "mapping" ? <AlertTriangle className="size-4 text-status-warning-fg" aria-hidden /> : <Loader2 className="size-4 animate-spin text-label-2" aria-hidden />}
                <span className="min-w-0 flex-1 truncate font-medium" title={r.file.name}>
                  {r.file.name}
                </span>
                {r.stage === "error" ? (
                  <Button size="xs" variant="outline" onClick={() => void upload(r.id, r.file)}>
                    <RotateCcw aria-hidden /> {t("common.retry")}
                  </Button>
                ) : null}
                <Button size="icon-xs" variant="ghost" aria-label={t("studio.upload.remove", { file: r.file.name })} onClick={() => setRows((rs) => rs.filter((x) => x.id !== r.id))}>
                  <X aria-hidden />
                </Button>
              </div>
              <p role="status" className={cn("mt-1 text-xs", r.stage === "error" || r.stage === "rejected" ? "text-status-infeasible-fg" : "text-label-2")}>
                {stageLabel(r)}
              </p>
              {r.stage === "uploading" || r.stage === "reading" ? (
                <div role="progressbar" aria-label={r.file.name} aria-valuemin={0} aria-valuemax={100} aria-valuenow={r.stage === "reading" ? undefined : r.percent} className="mt-1 h-1 overflow-hidden rounded-full bg-fill-2">
                  <div className={cn("h-full bg-primary transition-[width] duration-[var(--dur-fast)]", r.stage === "reading" && "studio-pulse")} style={{ width: `${r.stage === "reading" ? 100 : r.percent}%` }} />
                </div>
              ) : null}
              {r.planningList ? (
                <p className="mt-1 text-xs text-status-warning-fg">
                  {t("studio.upload.looksLikePlanningList")}{" "}
                  <Link className="underline" href="/import?source=planning">
                    {t("nav.import")}
                  </Link>
                </p>
              ) : null}
              {r.stage === "mapping" ? (
                <div className="mt-2">
                  <MappingStep
                    filename={r.file.name}
                    load={() => api.studio.mapping(termId, r.file, locale) as Promise<MappingColumns>}
                    submit={(spec: MappingSpec) => api.studio.mapping(termId, r.file, locale, spec) as Promise<MappingProposals>}
                    onDone={(res) => ingest(r.id, r.file, res)}
                    onCancel={() => setRows((rs) => rs.filter((x) => x.id !== r.id))}
                  />
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
