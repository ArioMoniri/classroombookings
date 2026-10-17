"use client";
/**
 * Small building blocks shared by the CRBS screens (/bookings, /my-bookings, /admin/*): page titles on the
 * scene, settings rows (label + hint left, control right; references.md H21), filled native selects,
 * status alerts (glyph + word, G4) and a confirm dialog. Built on the Liquid Glass primitives only.
 */
import { Loader2 } from "lucide-react";
import { useId, type ComponentProps, type ReactNode, type SelectHTMLAttributes } from "react";
import { Alert as UiAlert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { BusyLabel } from "@/components/ui/busy-label";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { cn } from "@/lib/utils";
import { useT } from "@/lib/i18n/provider";

/** Classes of the PageTitle actions: a header row on desktop; below `lg` (the shell shows the tab bar) a capsule fixed
 *  above the tab bar (MOBILE.md M-05: the primary action of /admin/users, /admin/roles, /admin/departments, /admin/audit
 *  stays in thumb reach while the list scrolls), the same pattern as find-room's "Ara" and My bookings' bulk cancel.
 *  globals.css pads the shell's <main> for it (`main:has([data-slot="page-actions"])`). Round 2 sweeper 3. */
export const pageActionsCapsule =
  "flex flex-wrap items-center gap-2 max-lg:fixed max-lg:inset-x-4 max-lg:bottom-[calc(var(--shell-bottom-h)+0.75rem)] max-lg:z-20 max-lg:justify-end max-lg:rounded-2xl max-lg:glass-chrome max-lg:p-1.5 max-lg:shadow-elev-2";

export function PageTitle({ title, subtitle, actions, className }: { title: string; subtitle?: ReactNode; actions?: ReactNode; className?: string }) {
  return (
    <header className={cn("mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between", className)}>
      <div className="min-w-0">
        <h1 className="type-title-1 text-label-1 lg:type-large-title">{title}</h1>
        {subtitle ? <p className="mt-1 type-callout text-label-2">{subtitle}</p> : null}
      </div>
      {actions ? (
        <div data-slot="page-actions" className={pageActionsCapsule}>
          {actions}
        </div>
      ) : null}
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
      {/* phones: the row's fields take the full width (no fixed w-56 / w-72 boxes floating short of the edge) */}
      <div className="flex min-w-0 shrink-0 items-center gap-2 max-sm:w-full max-sm:flex-wrap max-sm:*:data-[slot=date-field]:w-full max-sm:*:data-[slot=input]:w-full max-sm:*:data-[slot=native-select]:w-full sm:justify-end">{children}</div>
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

/** The design-system NativeSelect (field surface, --control-h, centred chevron); 16 px text on touch phones. */
export function SelectField({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  const { size: _size, ...rest } = props;
  void _size;
  return (
    <NativeSelect {...rest} className={className}>
      {children}
    </NativeSelect>
  );
}

/** Status message (glyph + word, G4): the ui Alert, promoted from this file; `testId` kept for the CRBS callers. */
export function Alert({ testId, ...props }: ComponentProps<typeof UiAlert> & { testId?: string }) {
  return <UiAlert data-testid={testId} {...props} />;
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
      {/* T-R2-02: a confirmation is an alertdialog (modal, focus trapped by ui/dialog) */}
      <DialogContent role="alertdialog" className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        {children}
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("crbs.common.cancel")}
          </Button>
          <Button variant={destructive ? "destructive" : "default"} onClick={onConfirm} disabled={busy} aria-busy={busy || undefined}>
            <BusyLabel busy={!!busy} label={t("busy.working")}>
            {confirmLabel}</BusyLabel>
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
    <Input
      id={id ?? auto}
      aria-label={label}
      type="number"
      min={0}
      inputMode="numeric"
      placeholder={placeholder}
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value === "" ? null : Math.max(0, Number(e.target.value)))}
      // 13ch: "Unlimited" / "Sınırsız" placeholders fit (UI/UX review: "Unlimitec")
      className="w-[13ch] tnum"
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
