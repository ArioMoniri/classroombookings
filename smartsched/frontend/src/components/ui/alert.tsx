// SmartSched Alert — status message: glyph + text on a translucent tint (never colour alone, G4).
// Promoted from components/admin/kit.tsx by the design-system overhaul (2026-10-15) with the sign-in spec's
// additions (docs/design/v2/sign-in.md §6.2, §14): a `neutral` tone (fill-2 + label-1, for "Çıkış yaptınız",
// "Oturumunuzun süresi doldu") and an `action` slot (a link or button at the end). `role` follows the tone:
// error → alert (assertive), the rest → status (polite). kit.tsx can re-export this one when its owner migrates.
// Motion: entering is opacity + y −4 → 0 on springs.snappy where a screen animates it (sign-in.md §10).
import * as React from "react"
import { AlertTriangle, CheckCircle2, Info, XOctagon } from "lucide-react"
import { cn } from "cn"

export type AlertTone = "neutral" | "info" | "warning" | "error" | "success"

const TONE: Record<AlertTone, { icon: typeof Info; cls: string }> = {
  neutral: { icon: Info, cls: "bg-fill-2 text-label-1" },
  info: { icon: Info, cls: "bg-tint-soft text-label-1" },
  warning: { icon: AlertTriangle, cls: "bg-status-warning text-status-warning-fg" },
  error: { icon: XOctagon, cls: "bg-status-infeasible text-status-infeasible-fg" },
  success: { icon: CheckCircle2, cls: "bg-status-feasible text-status-feasible-fg" },
}

export function Alert({
  tone = "info",
  title,
  children,
  action,
  icon,
  className,
  live = tone === "error" ? "assertive" : "polite",
  "data-testid": testId,
}: {
  tone?: AlertTone
  title?: React.ReactNode
  children?: React.ReactNode
  /** trailing action (a Button size="sm" or a link) */
  action?: React.ReactNode
  /** replaces the tone's glyph (e.g. a clock for "session expired") */
  icon?: React.ReactNode
  className?: string
  live?: "polite" | "assertive" | "off"
  "data-testid"?: string
}) {
  const { icon: Icon, cls } = TONE[tone]
  return (
    <div
      data-slot="alert"
      data-tone={tone}
      role={tone === "error" ? "alert" : "status"}
      aria-live={live}
      data-testid={testId}
      className={cn("flex items-start gap-2.5 rounded-xl px-3 py-2.5 type-callout", cls, className)}
    >
      <span aria-hidden className="mt-0.5 flex shrink-0 [&_svg]:size-4 [&_svg]:stroke-[1.75]">{icon ?? <Icon />}</span>
      <div className="min-w-0 flex-1">
        {title ? <p className="font-semibold">{title}</p> : null}
        {children ? <div>{children}</div> : null}
      </div>
      {action ? <div className="ml-auto flex shrink-0 items-center self-center">{action}</div> : null}
    </div>
  )
}
