import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Large title in the content, left-aligned (Apple "content-anchored titles", references A16; A5, A10). */
export function PageHeader({ title, subtitle, actions, className }: { title: string; subtitle?: ReactNode; actions?: ReactNode; className?: string }) {
  return (
    <div className={cn("mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between lg:mb-6", className)}>
      <div className="min-w-0">
        <h1 tabIndex={-1} className="type-title-1 text-label-1 outline-none lg:type-large-title">
          {title}
        </h1>
        {subtitle ? <p className="mt-1 text-[13px] text-label-2">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
