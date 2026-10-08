"use client";

import { motion, useMotionValue, useSpring } from "motion/react";
import { useEffect, useRef, useState, type DragEvent } from "react";
import { FileUpload, type FileUploadItem } from "@/components/ui/beui/file-upload";
import { useI18n } from "@/lib/i18n/provider";
import { pointerSpring, springs, useReduce } from "@/lib/motion";
import { cn } from "@/lib/utils";

export type UploadState = { phase: "idle" } | { phase: "uploading"; pct: number } | { phase: "processing" } | { phase: "done" } | { phase: "error"; message: string };

/**
 * beUI file-upload (MIT) with SmartSched behaviour:
 * - one .xlsx file; the queue row shows **real** upload bytes (XMLHttpRequest), then "reading on the server";
 * - magnetic drop (motion patterns §7 + §14, no kobra code): while a file is dragged over the page the
 *   dropzone lifts (snappy), and over the zone it leans ≤ 4 px toward the pointer (pointerSpring) so the
 *   target "pulls" the file. Transform only; reduced motion keeps the outline change and nothing moves;
 * - the vendored component's English screen-reader labels are localised in place (it has no label props).
 */
export function MagneticDrop({ file, onFile, upload, disabled }: { file: File | null; onFile: (f: File | null) => void; upload: UploadState; disabled?: boolean }) {
  const { t } = useI18n();
  const reduce = useReduce();
  const root = useRef<HTMLDivElement>(null);
  const [pageDrag, setPageDrag] = useState(false);
  const [over, setOver] = useState(false);
  const px = useMotionValue(0);
  const py = useMotionValue(0);
  const x = useSpring(px, pointerSpring);
  const y = useSpring(py, pointerSpring);

  // a file dragged anywhere over the window: the zone signals where it can go
  useEffect(() => {
    let depth = 0;
    const enter = (e: globalThis.DragEvent) => {
      if (!e.dataTransfer?.types.includes("Files")) return;
      depth += 1;
      setPageDrag(true);
    };
    const leave = () => {
      depth = Math.max(0, depth - 1);
      if (depth === 0) setPageDrag(false);
    };
    const end = () => {
      depth = 0;
      setPageDrag(false);
      setOver(false);
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragleave", leave);
    window.addEventListener("drop", end);
    window.addEventListener("dragend", end);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("drop", end);
      window.removeEventListener("dragend", end);
    };
  }, []);

  const lean = (e: DragEvent<HTMLDivElement>) => {
    if (reduce) return;
    const r = e.currentTarget.getBoundingClientRect();
    px.set(((e.clientX - r.left) / r.width - 0.5) * 8);
    py.set(((e.clientY - r.top) / r.height - 0.5) * 8);
  };
  const release = () => {
    px.set(0);
    py.set(0);
  };

  const status: FileUploadItem["status"] = upload.phase === "error" ? "error" : upload.phase === "done" ? "success" : upload.phase === "idle" ? "queued" : "uploading";
  const items: FileUploadItem[] = file
    ? [{ id: `${file.name}-${file.size}`, name: file.name, size: file.size, type: file.type, file, status, progress: upload.phase === "uploading" ? upload.pct : upload.phase === "processing" || upload.phase === "done" ? 100 : 0, error: upload.phase === "error" ? upload.message : undefined }]
    : [];

  // stable test ids + Turkish/English accessible names on the vendored markup
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const input = el.querySelector<HTMLInputElement>('input[type="file"]');
    input?.setAttribute("data-testid", "file-input");
    input?.setAttribute("aria-label", t("import.dropzone"));
    el.querySelectorAll<HTMLElement>("[aria-label]").forEach((node) => {
      const label = node.getAttribute("aria-label") ?? "";
      const name = file?.name ?? "";
      if (label.startsWith("Remove ")) node.setAttribute("aria-label", t("glass.import.remove", { name }));
      else if (label.startsWith("Retry ")) node.setAttribute("aria-label", t("glass.import.retry", { name }));
      else if (label.endsWith(" upload progress")) node.setAttribute("aria-label", t("glass.import.progressOf", { name }));
    });
    el.querySelectorAll<HTMLElement>(".sr-only").forEach((node) => {
      const map: Record<string, string> = { Queued: t("glass.import.queued"), Uploading: t("glass.import.uploading"), Uploaded: t("glass.import.uploaded"), Failed: t("glass.import.failedShort") };
      const next = map[node.textContent ?? ""];
      if (next) node.textContent = next;
    });
  });

  const lifted = !reduce && (pageDrag || over);
  return (
    <div ref={root} data-testid="import-dropzone" className="relative">
      <motion.div
        onDragEnter={() => setOver(true)}
        onDragOver={lean}
        onDragLeave={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
            setOver(false);
            release();
          }
        }}
        onDrop={() => {
          setOver(false);
          release();
        }}
        style={reduce ? undefined : { x, y }}
        animate={reduce ? undefined : { scale: over ? 1.015 : lifted ? 1.006 : 1 }}
        transition={springs.snappy}
        className={cn("rounded-3xl transition-[outline-color] duration-(--dur-fast)", (pageDrag || over) && "outline-2 outline-offset-2 outline-(--focus)", !over && pageDrag && "outline-dashed")}
        data-dragging={over}
      >
        <FileUpload
          value={items}
          onValueChange={(next) => onFile(next.at(-1)?.file ?? null)}
          accept=".xlsx,.xlsm"
          multiple={false}
          disabled={disabled}
          variant="centered"
          title={over ? t("glass.import.dropNow") : t("import.dropzone")}
          description={t("import.dropzoneHint")}
          browseLabel={t("glass.import.browse")}
          classNames={{ dropzone: "border-hairline-strong bg-fill-3 data-[dragging=true]:border-(--accent) data-[dragging=true]:bg-tint-soft", item: "bg-fill-2 border-transparent" }}
        />
      </motion.div>
      {upload.phase === "processing" ? (
        <p role="status" className="mt-2 text-[12.5px] text-label-2">
          {t("glass.import.reading")}
        </p>
      ) : upload.phase === "error" ? (
        <p role="alert" className="mt-2 text-[12.5px] text-status-infeasible-fg">
          {upload.message}
        </p>
      ) : null}
    </div>
  );
}
