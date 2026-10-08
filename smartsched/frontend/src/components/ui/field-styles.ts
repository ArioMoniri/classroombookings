// SmartSched Liquid Glass v2 — shared field surface (Input, Textarea, Select trigger, InputGroup).
// Original work for SmartSched (docs/design/v2/liquid-glass.md §9). Fields are filled wells, not
// outlined boxes (Apple text fields): fill-2 at rest, a lit thick surface + tint ring on focus.
export const fieldSurface =
  "t-input rounded-lg border border-transparent bg-fill-2 text-label-1 shadow-[inset_0_0_0_1px_var(--hairline)] transition-[background-color,border-color] duration-(--dur-fast) ease-out outline-none placeholder:text-label-3 hover:bg-fill-1 focus-visible:bg-(--mat-thick) focus-visible:border-(--focus) focus-visible:shadow-[0_0_0_3px_color-mix(in_oklab,var(--focus)_22%,transparent)] disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-(--status-infeasible-border) aria-invalid:shadow-[0_0_0_3px_color-mix(in_oklab,var(--status-infeasible-solid)_16%,transparent)]"
