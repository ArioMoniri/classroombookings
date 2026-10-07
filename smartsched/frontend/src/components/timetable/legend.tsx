"use client";

import { Info } from "lucide-react";
import { STATUS_ICON } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { STATUS_EVENT_CLASS } from "./grid-event";
import { STATUS_TO_KIND, type GridEvent } from "./use-grid-model";

const ORDER: { status: GridEvent["status"]; key: MessageKey }[] = [
  { status: "ok", key: "grid.ok" },
  { status: "locked", key: "grid.locked" },
  { status: "conflict", key: "grid.conflict" },
  { status: "warning", key: "grid.capacityWarning" },
  { status: "block", key: "grid.block" },
  { status: "tip", key: "grid.tip" },
  { status: "pc", key: "grid.pc" },
];

export function Legend() {
  const { t } = useI18n();
  return (
    <Popover>
      <PopoverTrigger render={<Button variant="ghost" size="sm" aria-label={t("grid.legend")}><Info /> {t("grid.legend")}</Button>} />
      <PopoverContent align="end" className="w-64">
        <ul className="space-y-1.5 text-sm">
          {ORDER.map(({ status, key }) => {
            const Icon = STATUS_ICON[STATUS_TO_KIND[status]];
            return (
              <li key={status} className="flex items-center gap-2">
                <span className={`inline-flex size-6 items-center justify-center rounded border ${STATUS_EVENT_CLASS[status]}`}><Icon className="size-3.5" aria-hidden /></span>
                {t(key)}
              </li>
            );
          })}
        </ul>
        <p className="mt-2 text-xs text-muted-foreground">{t("grid.dragHint")}</p>
      </PopoverContent>
    </Popover>
  );
}
