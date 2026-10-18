"use client";
/**
 * HB-23c (helper-file-router.md §8.1, §8.2, §10): the helper's ways in for a file.
 *
 * - {@link useFilePicker}: one `<input type=file>` with a `<label for>` and the router's `accept` list (the setup
 *   wizard's formats plus `.sql` dumps); phones get the native picker (Files / Drive / OneDrive).
 * - {@link AttachButton}: 📎 "Dosya ekle", a 44 px IconButton (Enter / Space open the picker), in the composer and in
 *   Rehber modu. Anchor `helper-attach` for "Göster".
 * - {@link SheetDropZone}: an OS file drag over the sheet's log shows an **instant** inset 2 px tint outline + tint-soft
 *   fill and one centred line (motion.md §3.8: an OS file is not our element, no lift, no magnet). A text drag does
 *   nothing. The drop goes to the router; the composer stays visible.
 * - {@link filesFromPaste}: Ctrl/⌘+V with a file on the clipboard while the focus is in the composer; text paste is
 *   unchanged.
 */
import { Paperclip } from "lucide-react";
import { useCallback, useId, useRef, useState, type ReactNode } from "react";
import { ACCEPTED_FORMATS } from "@/components/onboarding/file-drop";
import { Button, IconButton } from "@/components/ui/button";
import { CLASSIFY_MAX_MB } from "@/lib/api/helper-files";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

/** the setup wizard's list (reused verbatim, §1.1) plus CRBS dumps */
export const ROUTER_ACCEPT = [...ACCEPTED_FORMATS, ".sql"].join(",");

/** An OS file drag (`dataTransfer.types` has `Files`); a text or in-app drag is not. */
export function isFileDrag(dt: DataTransfer | null | undefined): boolean {
  if (!dt) return false;
  return Array.from(dt.types ?? []).includes("Files");
}

/** The files of a paste event, or [] for a text paste. */
export function filesFromPaste(e: { clipboardData: DataTransfer | null }): File[] {
  return Array.from(e.clipboardData?.files ?? []);
}

export function useFilePicker(onFiles: (files: File[]) => void, opts: { testId?: string } = {}) {
  const { t } = useI18n();
  const ref = useRef<HTMLInputElement>(null);
  const id = useId();
  const open = useCallback(() => ref.current?.click(), []);
  const input: ReactNode = (
    <>
      <label htmlFor={id} className="sr-only">
        {t("helper.file.attach")}
      </label>
      <input
        ref={ref}
        id={id}
        type="file"
        multiple
        accept={ROUTER_ACCEPT}
        tabIndex={-1}
        className="sr-only"
        data-testid={opts.testId ?? "helper-file-input"}
        onChange={(e) => {
          const list = Array.from(e.target.files ?? []);
          // the same file can be picked again after a refusal
          e.target.value = "";
          if (list.length) onFiles(list);
        }}
      />
    </>
  );
  return { open, input };
}

export function AttachButton({ onFiles, className, withLabel = false }: { onFiles: (files: File[]) => void; className?: string; withLabel?: boolean }) {
  const { t } = useI18n();
  const picker = useFilePicker(onFiles);
  if (withLabel) {
    // Rehber modu: the same 📎 with its words, under the search field
    return (
      <>
        <Button variant="ghost" size="md" onClick={picker.open} data-testid="helper-attach" data-tour="helper-attach" className={cn("min-h-11 self-start", className)}>
          <Paperclip aria-hidden />
          {t("helper.file.attach")}
        </Button>
        {picker.input}
      </>
    );
  }
  return (
    <>
      <IconButton label={t("helper.file.attach")} onClick={picker.open} data-testid="helper-attach" data-tour="helper-attach" className={cn("size-11", className)}>
        <Paperclip aria-hidden />
      </IconButton>
      {picker.input}
    </>
  );
}

/** The sheet's log as a drop target (desktop; phones have no OS drag). */
export function SheetDropZone({ onFiles, children, className }: { onFiles: (files: File[]) => void; children: ReactNode; className?: string }) {
  const { t } = useI18n();
  const [over, setOver] = useState(false);
  const depth = useRef(0);
  const reset = () => {
    depth.current = 0;
    setOver(false);
  };
  return (
    <div
      className={cn("relative flex min-h-0 flex-1 flex-col", className)}
      data-local-drop=""
      onDragEnter={(e) => {
        if (!isFileDrag(e.dataTransfer)) return;
        e.preventDefault();
        depth.current += 1;
        setOver(true);
      }}
      onDragOver={(e) => {
        if (!isFileDrag(e.dataTransfer)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "copy";
      }}
      onDragLeave={(e) => {
        if (!isFileDrag(e.dataTransfer)) return;
        depth.current = Math.max(0, depth.current - 1);
        if (depth.current === 0) setOver(false);
      }}
      onDrop={(e) => {
        if (!isFileDrag(e.dataTransfer)) return;
        e.preventDefault();
        reset();
        const list = Array.from(e.dataTransfer.files ?? []);
        if (list.length) onFiles(list);
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape" && over) reset();
      }}
    >
      {children}
      {over ? (
        // instant (no transition): §9 row 1; the label announces the state ("Bırakın"), not motion
        <div
          data-testid="helper-file-drop"
          role="status"
          className="pointer-events-none absolute inset-0 z-10 flex flex-col items-center justify-center gap-1 rounded-(--radius-md) bg-tint-soft p-6 text-center outline-2 -outline-offset-2 outline-solid outline-tint forced-colors:outline-[Highlight]"
        >
          <p className="type-headline text-label-1">{t("helper.file.dropHere")}</p>
          <p className="type-footnote text-label-2">{t("helper.file.formats", { mb: CLASSIFY_MAX_MB })}</p>
          <p className="type-caption text-label-2">{t("helper.file.privacy")}</p>
        </div>
      ) : null}
    </div>
  );
}
