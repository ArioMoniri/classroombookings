import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Large title in the content, left-aligned (Apple "content-anchored titles", references A16; A5, A10).
 *  Always `type-large-title`: fluid 28 → 34 px (tokens.md §A.4), the same title on every page. */
export function PageHeader({ title, subtitle, actions, className }: { title: string; subtitle?: ReactNode; actions?: ReactNode; className?: string }) {
  return (
    <div className={cn("mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between lg:mb-6", className)}>
      <div className="min-w-0">
        <h1 tabIndex={-1} className="type-large-title text-label-1 outline-hidden">
          {title}
        </h1>
        {subtitle ? <p className="mt-1 type-callout text-label-2">{subtitle}</p> : null}
      </div>
      {/* F-MB-1: below lg a page-actions capsule is fixed above the tab bar; its wrapper must not add the column's
          12 px gap when the actions arrive with the data (it pushed the page down, /exams/invigilation at 390) */}
      {actions ? <div className="flex flex-wrap items-center gap-2 max-lg:has-[>[data-slot=page-actions]]:contents">{actions}</div> : null}
    </div>
  );
}
