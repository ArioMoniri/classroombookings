"use client";
/**
 * "Sign in with Microsoft" (docs/design/v2/sign-in.md §7). Not a ui/ primitive: it carries Microsoft's branding,
 * followed literally (https://learn.microsoft.com/en-us/entra/identity-platform/howto-add-branding-in-apps):
 * the official four-square logo (21 × 21, unaltered), Segoe UI 15 px semibold, 12 px paddings and logo gap,
 * light #FFFFFF / #5E5E5E with a 1 px #8C8C8C edge, dark #2F2F2F / #FFFFFF (plus the same edge, so the shape reads
 * on dark glass). Height is the page's control height (44 fine / 48 coarse, both ≥ the 41 px redline); the corners
 * are 12 px like the fields beside it. Never themed by the accent.
 *
 * It is a real navigation (`<a href>`) to the backend start route. Motion (§10, "Microsoft button pressed"): press
 * scale .97 on the snappy CSS spring (removed under reduced motion by the global rule); the busy label appears after
 * 150 ms so an instant redirect shows nothing; a second click is ignored.
 */
import { useEffect, useState, type MouseEvent } from "react";
import { BusyGlyph, useBusyDelay } from "@/components/ui/busy-label";
import { cn } from "@/lib/utils";

/** Microsoft's redline font (Segoe UI), then the platform UI fonts. */
const MS_FONT = '"Segoe UI", -apple-system, BlinkMacSystemFont, var(--font-inter), Inter, system-ui, sans-serif';

/** The official Microsoft logo: four 9 × 9 squares in a 21 × 21 box. */
export function MicrosoftLogo({ size = 21, className }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 21 21" aria-hidden focusable="false" className={cn("shrink-0 [forced-color-adjust:none]", className)} data-testid="microsoft-logo">
      <rect x="1" y="1" width="9" height="9" fill="#f25022" />
      <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
      <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
      <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
    </svg>
  );
}

export function MicrosoftSignIn({ href, label, busyLabel, describedBy, onNavigate, className }: { href: string; label: string; busyLabel: string; describedBy?: string; onNavigate?: () => void; className?: string }) {
  const [busy, setBusy] = useState(false);
  const shown = useBusyDelay(busy);
  // back/forward cache: a page restored after Microsoft must not stay busy
  useEffect(() => {
    const reset = (e: PageTransitionEvent) => e.persisted && setBusy(false);
    window.addEventListener("pageshow", reset);
    return () => window.removeEventListener("pageshow", reset);
  }, []);
  const onClick = (e: MouseEvent<HTMLAnchorElement>) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) return; // a new tab: this page stays as it is
    if (busy) {
      e.preventDefault();
      return;
    }
    setBusy(true);
    onNavigate?.();
  };
  return (
    <>
      <a
        href={href}
        onClick={onClick}
        aria-disabled={busy || undefined}
        aria-describedby={describedBy}
        data-testid="login-sso-microsoft"
        data-busy={busy || undefined}
        style={{ fontFamily: MS_FONT, fontSize: 15, boxShadow: "inset 0 0 0 1px var(--ms-btn-edge)" }}
        className={cn(
          // Microsoft's colours, never the accent; light first, dark via the .dark class (next-themes)
          "[--ms-btn-bg:#ffffff] [--ms-btn-fg:#5e5e5e] [--ms-btn-edge:#8c8c8c] dark:[--ms-btn-bg:#2f2f2f] dark:[--ms-btn-fg:#ffffff]",
          "relative isolate flex h-(--signin-control-h,44px) w-full items-center justify-center gap-3 overflow-hidden rounded-lg px-3",
          "bg-(--ms-btn-bg) text-(--ms-btn-fg)",
          "leading-5 font-semibold tracking-normal no-underline",
          // hover / pressed veil (light: black 4 %, dark: white 7 %) and press scale on the snappy spring
          "after:pointer-events-none after:absolute after:inset-0 after:-z-0 after:rounded-[inherit] after:bg-black/[0.04] after:opacity-0 after:transition-opacity after:duration-(--dur-fast) hover:after:opacity-100 dark:after:bg-white/[0.07]",
          "transition-transform duration-(--dur-fast) ease-(--spring-snappy) active:scale-[0.97] aria-disabled:cursor-progress",
          "outline-hidden focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solid focus-visible:outline-(--focus)",
          "forced-colors:bg-[ButtonFace] forced-colors:text-[ButtonText] forced-colors:shadow-none forced-colors:border forced-colors:border-[ButtonText]",
          className,
        )}
      >
        {shown ? <BusyGlyph className="size-[21px] shrink-0" /> : <MicrosoftLogo />}
        <span className="relative">{shown ? busyLabel : label}</span>
      </a>
      {/* one polite echo of the busy state (§11 live regions) */}
      <span role="status" className="sr-only">
        {shown ? busyLabel : ""}
      </span>
    </>
  );
}
