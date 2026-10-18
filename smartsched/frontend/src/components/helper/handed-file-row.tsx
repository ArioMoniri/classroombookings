"use client";
/**
 * HB-23c (helper-file-router.md §6.5, §9, §10): the file the helper handed over, on the target page (/import, the setup
 * wizard, Kullanıcılar › İçe aktar): icon · name · size · "Yardımcıdan geldi" · ✕ "Dosyayı kaldır" (44 px). It sits
 * where the empty drop zone was. One tint highlight fades after 2 s ("your file is already here"; reduced motion: the
 * highlight stays still for 2 s, then goes). Expired (10 minutes, or the server said 410): "Dosyanın süresi doldu
 * (10 dakika). Yeniden seçin." and the page's zone comes back.
 */
import { FileSpreadsheet, X } from "lucide-react";
import { useEffect, useState } from "react";
import { IconButton } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/provider";
import { useReduce } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { formatSize } from "./cards/file-size";
import type { HandedItem } from "./file-handoff";

export function HandedFileRow({ item, onRemove, testId = "import-handed-file" }: { item: Pick<HandedItem, "name" | "size">; onRemove: () => void; testId?: string }) {
  const { t, locale } = useI18n();
  const reduce = useReduce();
  const [fresh, setFresh] = useState(true);
  useEffect(() => {
    const id = window.setTimeout(() => setFresh(false), 2000);
    return () => window.clearTimeout(id);
  }, []);
  return (
    <div
      data-testid={testId}
      data-fresh={fresh || undefined}
      role="group"
      aria-label={t("helper.file.handedRow", { name: item.name })}
      className={cn(
        "flex min-h-11 min-w-0 items-center gap-3 rounded-xl px-3 py-2 edge-hairline forced-colors:border forced-colors:border-[CanvasText]",
        !reduce && "transition-colors duration-(--dur-base)",
        fresh ? "bg-tint-soft" : "bg-fill-3",
      )}
    >
      <FileSpreadsheet aria-hidden className="size-5 shrink-0 stroke-[1.75] text-label-2" />
      <span className="min-w-0 flex-1">
        <span className="block truncate type-body font-medium text-label-1" title={item.name}>
          {item.name}
        </span>
        <span className="block type-footnote text-label-2">{formatSize(item.size, locale)}</span>
      </span>
      <span className="inline-flex h-6 shrink-0 items-center rounded-full bg-fill-2 px-2 type-caption text-label-1" data-testid="handed-file-chip">
        {t("helper.file.handed")}
      </span>
      <IconButton label={t("helper.file.removeName", { name: item.name })} onClick={onRemove} className="size-11" data-testid={`${testId}-remove`}>
        <X aria-hidden />
      </IconButton>
    </div>
  );
}

/** "Dosyanın süresi doldu (10 dakika). Yeniden seçin." */
export function HandedFileExpired({ testId = "import-handed-expired" }: { testId?: string }) {
  const { t } = useI18n();
  return (
    <p className="type-callout text-status-warning-fg" role="status" data-testid={testId}>
      {t("helper.file.expiredPage")}
    </p>
  );
}
