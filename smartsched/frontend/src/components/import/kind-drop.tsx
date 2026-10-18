"use client";
/**
 * HB-23c (helper-file-router.md §8.4 "/import step 0"): "Türünü bilmiyor musunuz? Dosyayı bırakın, biz söyleyelim."
 * above the kind list. One button with a visible label (Enter / Space open the picker, T-R2-20: no nested control)
 * and an OS-file drop target with the instant tint (motion.md §3.8). The page runs the helper's classify on the file.
 */
import { FileQuestion } from "lucide-react";
import { useId, useRef, useState } from "react";
import { BareButton } from "@/components/ui/button";
import { BusyGlyph } from "@/components/ui/busy-label";
import { ROUTER_ACCEPT, isFileDrag } from "@/components/helper/file-drop";
import { CLASSIFY_MAX_MB } from "@/lib/api/helper-files";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

export function KindDrop({ onFile, busy }: { onFile: (file: File) => void; busy: boolean }) {
  const { t } = useI18n();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const titleId = useId();
  const hintId = useId();
  const inputId = useId();
  return (
    <div
      data-local-drop=""
      onDragOver={(e) => {
        if (!isFileDrag(e.dataTransfer)) return;
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        if (!isFileDrag(e.dataTransfer)) return;
        e.preventDefault();
        setOver(false);
        const f = e.dataTransfer.files?.[0];
        if (f) onFile(f);
      }}
      data-dragging={over || undefined}
      className={cn("mb-4 max-w-3xl rounded-xl edge-hairline", over && "bg-tint-soft outline-2 -outline-offset-2 outline-solid outline-tint forced-colors:outline-[Highlight]")}
    >
      <BareButton
        data-testid="import-kind-drop"
        aria-labelledby={titleId}
        aria-describedby={hintId}
        aria-busy={busy || undefined}
        disabled={busy}
        onClick={() => input.current?.click()}
        className="flex min-h-11 w-full items-center gap-3 rounded-xl p-3 text-left font-normal whitespace-normal"
      >
        <span aria-hidden className="flex size-9 shrink-0 items-center justify-center rounded-[10px] bg-fill-2 text-label-1">
          {busy ? <BusyGlyph /> : <FileQuestion className="size-[18px] stroke-[1.75]" />}
        </span>
        <span className="min-w-0 flex-1">
          <span id={titleId} className="block type-body font-medium text-label-1">
            {busy ? t("helper.file.reading") : t("helper.file.dontKnow")}
          </span>
          <span id={hintId} className="block type-footnote text-label-2">
            {t("helper.file.dontKnowHint", { mb: CLASSIFY_MAX_MB })}
          </span>
        </span>
      </BareButton>
      <p className="px-3 pb-3 type-caption text-label-2" data-testid="import-kind-drop-privacy">
        {t("helper.file.privacyRead")}
      </p>
      <label htmlFor={inputId} className="sr-only">
        {t("helper.file.dontKnow")}
      </label>
      <input
        ref={input}
        id={inputId}
        type="file"
        accept={ROUTER_ACCEPT}
        tabIndex={-1}
        className="sr-only"
        data-testid="import-kind-drop-input"
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (f) onFile(f);
        }}
      />
    </div>
  );
}
