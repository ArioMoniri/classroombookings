// SmartSched Liquid Glass v2 — GlassPanel. Original work (docs/design/v2/liquid-glass.md §2, §9).
// One piece of material. Pick the level by what sits *behind* it (rule G1): ultra-thin / thin /
// regular only over the scene; thick / chrome may float over content.
import { mergeProps } from "@base-ui/react/merge-props"
import { useRender } from "@base-ui/react/use-render"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

const glassPanelVariants = cva("relative isolate text-label-1", {
  variants: {
    material: {
      "ultra-thin": "glass-ultra-thin",
      thin: "glass-thin",
      regular: "glass-regular",
      thick: "glass-thick",
      chrome: "glass-chrome",
    },
    radius: {
      none: "rounded-none",
      md: "rounded-lg",
      lg: "rounded-xl",
      xl: "rounded-2xl",
      "2xl": "rounded-3xl",
      capsule: "rounded-full",
    },
    padding: {
      none: "",
      sm: "p-2",
      md: "p-4",
      lg: "p-6",
    },
    /* Elevation by light: hover brightens the sheen and lifts the ambient shadow one step. */
    interactive: {
      true: "cursor-pointer transition-[box-shadow,filter] duration-(--dur-base) ease-out hover:brightness-[1.03] hover:shadow-(--shadow-2) active:brightness-[0.99] dark:hover:brightness-[1.12]",
      false: "",
    },
  },
  defaultVariants: { material: "regular", radius: "xl", padding: "none", interactive: false },
})

type GlassPanelProps = useRender.ComponentProps<"div"> & VariantProps<typeof glassPanelVariants>

function GlassPanel({ className, material, radius, padding, interactive, render, ...props }: GlassPanelProps) {
  return useRender({
    defaultTagName: "div",
    props: mergeProps<"div">(
      {
        className: cn(glassPanelVariants({ material, radius, padding, interactive }), className),
        // data-glass is consumed by globals.css (squircle corners, forced-colors fallback)
        ...({ "data-glass": material ?? "regular", "data-slot": "glass-panel" } as Record<string, string>),
      },
      props
    ),
    render,
  })
}

export { GlassPanel, glassPanelVariants, type GlassPanelProps }
