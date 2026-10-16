"use client";
/**
 * "Karşılaştır" on the runs list: a two-run picker (A baseline, B scenario; the runs of the active term) that opens
 * `/runs/compare?a=&b=`. A dialog on tablets and desktops, a bottom sheet on phones.
 */
import { GitCompareArrows } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ResponsiveDialog } from "@/components/moderation/responsive-dialog";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { Button } from "@/components/ui/button";
import { useRunOptions } from "@/lib/api/analytics";
import { useI18n } from "@/lib/i18n/provider";
import { defaultPair } from "./compare-model";
import { RunPairPicker } from "./run-pair-picker";

export function CompareEntry() {
  const { t } = useI18n();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const { term } = useActiveTerm();
  const runs = useRunOptions(term?.id ?? null);
  const pair = useMemo(() => (runs.data ? defaultPair(runs.data) : null), [runs.data]);
  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)} data-testid="runs-compare">
        <GitCompareArrows aria-hidden />
        {t("compare.entry")}
      </Button>
      <ResponsiveDialog
        open={open}
        onOpenChange={setOpen}
        title={t("compare.entryTitle")}
        description={t("compare.entryBody")}
        testId="compare-entry-dialog"
        footer={<Button variant="ghost" className="max-md:h-11" onClick={() => setOpen(false)}>{t("common.cancel")}</Button>}
      >
        <RunPairPicker
          compact
          runs={runs.data}
          loading={runs.isLoading}
          a={pair?.a ?? null}
          b={pair?.b ?? null}
          onApply={(a, b) => {
            setOpen(false);
            router.push(`/runs/compare?a=${a}&b=${b}`);
          }}
        />
      </ResponsiveDialog>
    </>
  );
}
