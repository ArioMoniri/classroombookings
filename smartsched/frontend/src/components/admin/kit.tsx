"use client";
/**
 * Small building blocks shared by the CRBS screens (/bookings, /my-bookings, /admin/*): page titles on the
 * scene, settings rows (label + hint left, control right; references.md H21), filled native selects,
 * status alerts (glyph + word, G4) and a confirm dialog. Built on the Liquid Glass primitives only.
 */
import { AlertTriangle, CheckCircle2, ChevronDown, Info, Loader2, XOctagon } from "lucide-react";
import { useId, type ReactNode, type SelectHTMLAttributes } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { fieldSurface } from "@/components/ui/field-styles";
import { cn } from "@/lib/utils";
import { useT } from "@/lib/i18n/provider";

export function PageTitle({ title, subtitle, actions, className }: { title: string; subtitle?: ReactNode; actions?: ReactNode; className?: string }) {
  return (
    <header className={cn("mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between", className)}>
      <div className="min-w-0">
        <h1 className="type-title-1 text-label-1 lg:type-large-title">{title}</h1>
        {subtitle ? <p className="mt-1 type-callout text-label-2">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function SectionTitle({ children, actions, id }: { children: ReactNode; actions?: ReactNode; id?: string }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 id={id} className="type-title-3 text-label-1">
        {children}
      </h2>
      {actions}
    </div>
  );
}

/** Settings row: label + hint on the left, the control on the right; stacks on phones. */
export function FieldRow({ label, hint, htmlFor, children, className }: { label: ReactNode; hint?: ReactNode; htmlFor?: string; children: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-6", className)}>
      <div className="min-w-0 sm:max-w-[55%]">
        <label htmlFor={htmlFor} className="type-headline text-label-1">
          {label}
        </label>
        {hint ? <p className="type-footnote text-label-3">{hint}</p> : null}
      </div>
      <div className="flex min-w-0 shrink-0 items-center gap-2 sm:justify-end">{children}</div>
    </div>
  );
}

/** Stacked form field: label above the control. */
export function Field({ label, hint, error, children, htmlFor, className }: { label: ReactNode; hint?: ReactNode; error?: string | null; children: ReactNode; htmlFor?: string; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={htmlFor} className="type-footnote font-medium text-label-2">
        {label}
      </label>
      {children}
      {error ? (
        <p className="type-footnote text-status-infeasible-fg" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="type-footnote text-label-3">{hint}</p>
      ) : null}
    </div>
  );
}

export function SelectField({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <span className={cn("relative inline-flex w-full", className)}>
      <select {...props} className={cn(fieldSurface, "h-8 w-full min-w-0 appearance-none pr-8 pl-3 text-[13px]")}>
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute top-1/2 right-2 size-4 -translate-y-1/2 text-label-3" aria-hidden />
    </span>
  );
}

type Tone = "info" | "warning" | "error" | "success";
const TONE: Record<Tone, { icon: typeof Info; cls: string }> = {
  info: { icon: Info, cls: "bg-tint-soft text-label-1" },
  warning: { icon: AlertTriangle, cls: "bg-status-warning text-status-warning-fg" },
  error: { icon: XOctagon, cls: "bg-status-infeasible text-status-infeasible-fg" },
  success: { icon: CheckCircle2, cls: "bg-status-feasible text-status-feasible-fg" },
};

/** Status message: glyph + text on a translucent tint (never colour alone). */
export function Alert({ tone = "info", title, children, className, live = tone === "error" ? "assertive" : "polite", testId }: { tone?: Tone; title?: ReactNode; children?: ReactNode; className?: string; live?: "polite" | "assertive" | "off"; testId?: string }) {
  const { icon: Icon, cls } = TONE[tone];
  return (
    <div role={tone === "error" ? "alert" : "status"} aria-live={live} data-testid={testId} className={cn("flex items-start gap-2.5 rounded-xl px-3 py-2.5 type-callout", cls, className)}>
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="min-w-0">
        {title ? <p className="font-semibold">{title}</p> : null}
        {children ? <div>{children}</div> : null}
      </div>
    </div>
  );
}

export function Loading({ label, className }: { label?: string; className?: string }) {
  const t = useT();
  return (
    <p className={cn("flex items-center gap-2 py-6 type-callout text-label-2", className)} role="status">
      <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden />
      {label ?? t("crbs.common.loading")}
    </p>
  );
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  destructive,
  busy,
  onConfirm,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  confirmLabel: string;
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  children?: ReactNode;
}) {
  const t = useT();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        {children}
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("crbs.common.cancel")}
          </Button>
          <Button variant={destructive ? "destructive" : "default"} onClick={onConfirm} disabled={busy}>
            {busy ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** A labelled numeric limit input where empty = unlimited. */
export function LimitInput({ value, onChange, label, id, placeholder }: { value: number | null | undefined; onChange: (v: number | null) => void; label: string; id?: string; placeholder?: string }) {
  const auto = useId();
  return (
    <input
      id={id ?? auto}
      aria-label={label}
      type="number"
      min={0}
      inputMode="numeric"
      placeholder={placeholder}
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value === "" ? null : Math.max(0, Number(e.target.value)))}
      className={cn(fieldSurface, "h-8 w-24 px-3 text-[13px] tabular-nums")}
    />
  );
}

/** Whether the shell (sidebar, ⌘K) should show the item; also used by AdminGate. */
export function NoAccess({ title, body }: { title: string; body: string }) {
  return (
    <section aria-labelledby="no-access" className="max-w-xl py-10">
      <h1 id="no-access" className="type-title-2 text-label-1">
        {title}
      </h1>
      <p className="mt-2 type-body text-label-2">{body}</p>
    </section>
  );
}
