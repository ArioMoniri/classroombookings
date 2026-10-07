import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function PageHeader({ title, subtitle, actions, className }: { title: string; subtitle?: string; actions?: ReactNode; className?: string }) {
  return (
    <div className={cn("mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between lg:mb-6", className)}>
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-[-0.01em] lg:text-2xl">{title}</h1>
        {subtitle ? <p className="mt-0.5 text-sm text-muted-foreground">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
