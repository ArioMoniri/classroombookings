"use client";
/**
 * Inline hint strip on the feature's own page, and the phone hint card at the top of a page (spec §4.5, §9). Non-modal,
 * never moves focus, `role="status"` (announced once), pushes the content down (never an overlay). 44 px buttons.
 */
import { Megaphone } from "lucide-react";
import { motion } from "motion/react";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/provider";
import { springs, useReduce } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { type ActiveHint, useHintActions, useHintText } from "./registry";

export function HintStrip({ hint, className }: { hint: ActiveHint; className?: string }) {
  const { t } = useI18n();
  const reduce = useReduce();
  const text = useHintText();
  const actions = useHintActions();
  const key = hint.def.key;
  const pathname = usePathname();
  const onPage = pathname === hint.def.href.split(/[?#]/)[0];
  return (
    <motion.div
      role="status"
      data-testid={`hint-${key}`}
      layout={!reduce}
      initial={reduce ? false : { opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reduce ? { duration: 0 } : springs.smooth}
      className={cn("mb-4 flex flex-col gap-3 rounded-2xl bg-tint-soft p-4 edge-hairline sm:flex-row sm:items-center", className)}
    >
      <Megaphone aria-hidden className="hidden size-5 shrink-0 text-tint-text sm:block" />
      <p className="min-w-0 flex-1 type-callout text-label-1">
        <strong className="font-semibold">{text.title(hint)}</strong> {text.body(hint)}{" "}
        <Button variant="link" className="h-auto min-h-11 align-baseline type-callout sm:min-h-0" onClick={() => actions.allNews(hint.def)}>
          {t("welcome.hints.allNews")}
        </Button>
      </p>
      <div className="flex shrink-0 gap-2">
        {onPage ? null : (
          <Button className="min-h-11 flex-1 sm:min-h-0 sm:flex-none" onClick={() => actions.tryIt(hint.def)} data-testid={`hint-try-${key}`}>
            {t("welcome.hints.try")}
          </Button>
        )}
        <Button variant="secondary" className="min-h-11 flex-1 sm:min-h-0 sm:flex-none" onClick={() => actions.seen(key)} data-testid={`hint-dismiss-${key}`}>
          {t("welcome.hints.dismiss")}
        </Button>
      </div>
    </motion.div>
  );
}
