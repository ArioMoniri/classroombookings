"use client";
/**
 * HB-23c (helper-file-router.md §8.4 "Empty states"): the one-line link "Elinizde bir dosya mı var? Bırakın, ne olduğunu
 * söyleyelim" on an empty page (/import history, /admin/rooms with no rooms, /admin/users with only the admin, a fresh
 * /dashboard). One link-styled button (44 px on touch) that opens the file picker; the picked file goes to the helper's
 * router and the sheet opens with its card. Never a second drop zone.
 */
import { Paperclip } from "lucide-react";
import { Button } from "@/components/ui/button";
import { usePermissions } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { useFilePicker } from "./file-drop";
import { attachFiles } from "./file-router";
import { useHelperStore } from "./helper-store";

export function HelperFileLink({ className }: { className?: string }) {
  const { t, locale } = useI18n();
  const { can } = usePermissions();
  const picker = useFilePicker(
    (list) => {
      const st = useHelperStore.getState();
      if (!st.open) st.openSheet();
      attachFiles(list, { can, lang: locale });
    },
    { testId: "helper-file-link-input" },
  );
  return (
    <>
      <Button variant="link" onClick={picker.open} data-testid="helper-file-link" className={cn("h-auto min-h-11 justify-start gap-1.5 text-left whitespace-normal", className)}>
        <Paperclip aria-hidden className="size-4" />
        {t("helper.file.emptyLink")}
      </Button>
      {picker.input}
    </>
  );
}
