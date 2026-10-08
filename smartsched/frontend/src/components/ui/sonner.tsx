"use client"
// Source: shadcn/ui sonner (style base-nova, https://ui.shadcn.com) on sonner (MIT, emilkowalski/sonner) — Licence: MIT
// Modified: yes — Liquid Glass v2 toasts: thick material, specular edge, status-tinted icons, max 3 visible; motion retimed
// to springs.smooth in globals.css ([data-sonner-toast]). API unchanged.

import { useTheme } from "next-themes"
import { Toaster as Sonner, type ToasterProps } from "sonner"
import { CircleCheckIcon, InfoIcon, TriangleAlertIcon, OctagonXIcon, Loader2Icon } from "lucide-react"

const Toaster = ({ ...props }: ToasterProps) => {
  const { theme = "system" } = useTheme()

  return (
    <Sonner
      theme={theme as ToasterProps["theme"]}
      className="toaster group"
      icons={{
        success: <CircleCheckIcon className="size-4 text-status-feasible-fg" />,
        info: <InfoIcon className="size-4 text-tint-text" />,
        warning: <TriangleAlertIcon className="size-4 text-status-warning-fg" />,
        error: <OctagonXIcon className="size-4 text-status-infeasible-fg" />,
        loading: <Loader2Icon className="size-4 animate-spin text-label-2" />,
      }}
      style={
        {
          "--normal-bg": "var(--mat-thick)",
          "--normal-text": "var(--label-1)",
          "--normal-border": "var(--hairline)",
          "--border-radius": "var(--radius-2xl)",
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          toast:
            "cn-toast !shadow-(--shadow-3) backdrop-blur-[32px] backdrop-saturate-[1.8] !text-[13px] !gap-2.5 !px-4 !py-3",
          title: "!font-semibold !text-label-1",
          description: "!text-label-2",
          actionButton: "!rounded-full !bg-tint !text-tint-foreground !font-medium",
          cancelButton: "!rounded-full !bg-fill-2 !text-label-1",
        },
      }}
      visibleToasts={3}
      {...props}
    />
  )
}

export { Toaster }
