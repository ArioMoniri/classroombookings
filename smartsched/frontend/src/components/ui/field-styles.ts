// SmartSched shared field surface (Input, Textarea, Select trigger, NativeSelect, DateField, InputGroup).
// Original work for SmartSched (docs/design/v2/liquid-glass.md §9, docs/design/tokens.md §A.1/§A.2/§A.5).
// Filled well + the 3:1 control edge (--edge-control, WCAG 1.4.11): fill-2 alone was 1.15:1 light / 1.34:1 dark
// against the card. Focus = 2 px --focus outline at offset 0 + a soft 3 px halo (the halo is decoration only).
// Height comes from --control-h (32 fine / 44 coarse); a field never sets its own pixel height.
export const fieldSurface =
  "t-input rounded-lg border border-transparent bg-fill-3 text-label-1 shadow-(--edge-control) transition-[background-color,border-color] duration-(--dur-fast) ease-out not-in-data-[slot=input-group]:focus-visible:outline-2 not-in-data-[slot=input-group]:focus-visible:outline-offset-0 not-in-data-[slot=input-group]:focus-visible:outline-(--focus) placeholder:text-label-3 hover:bg-fill-2 focus-visible:bg-(--mat-thick) focus-visible:shadow-[var(--edge-control),0_0_0_3px_color-mix(in_oklab,var(--focus)_22%,transparent)] disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:shadow-[inset_0_0_0_1px_var(--status-infeasible-border),0_0_0_3px_color-mix(in_oklab,var(--status-infeasible-solid)_16%,transparent)]"

/** Height + horizontal padding + type of a single-line field at each control size. */
export const fieldSize = {
  sm: "h-(--control-h-sm) px-2.5 type-footnote",
  md: "h-(--control-h-md) px-3 type-callout",
  lg: "h-(--control-h-lg) px-3.5 type-body",
} as const
export type FieldSize = keyof typeof fieldSize
