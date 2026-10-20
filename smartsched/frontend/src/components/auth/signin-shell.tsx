"use client";
/**
 * The institution sheet (docs/design/v2/sign-in.md §3.1, §4.1, §5, §9): a left-docked regular-glass sheet in the
 * sidebar's place (≥ 600 px: inset 8, radius 2xl, width clamp(400px, 36vw, 480px), scrolls inside); below 600 px
 * the sheet is the page (inset 0, radius 0, top-aligned, the document scrolls). Shared by /login, /login/sso and
 * /welcome. Nothing animates on first paint (§10).
 *
 * Keyboard safety (§5.4): on focus of a field the element is scrolled to the centre of the visual viewport one
 * frame later, and again on `visualViewport.resize` (iOS does not resize the layout viewport); the submit sits
 * directly under the password, never pinned.
 */
import { Monitor, Moon, Sun } from "lucide-react";
import { motion } from "motion/react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";
import { Fragment, useEffect, useRef, useSyncExternalStore, type CSSProperties, type ReactNode } from "react";
import { Logo } from "@/components/brand";
import { useCycleTheme } from "@/components/shell/theme-toggle";
import { IconButton } from "@/components/ui/button";
import { GlassPanel } from "@/components/ui/glass-panel";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { LOCALE_INFO, type Locale } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { springs, useReduce } from "@/lib/motion";
import { SignInHero } from "./signin-hero";
import { SignInShowcase, SignInValueList } from "./signin-showcase";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/** Page-local tokens (§9). Control height 44 fine / 48 coarse also drives the fields (--control-h-lg). */
// --signin-top 8vh -> 5vh (decision 2026-10-19): with Microsoft, door 2 open, an error and the passkey button (AU-B)
// the footer fell below the fold at 1440 x 900 (sign-in #25 keeps it in view)
// 5vh -> clamp(12px, 20vh - 168px, 96px) (decision 2026-10-19, pod e2e #125): that state left only 19 px to spare
// with Inter, and a host whose fallback font sets lines taller (the CI's Playwright image) pushed the footer 21 px
// below the fold. The top gap now shrinks on short screens (12 px at 900, 48 px at 1080, 72 px at 1200) and the
// gaps between the doors and above the footer tighten at ≤ 960 px tall: about 70 px back at 1440 x 900
// Showcase tokens (login-navbar-2026-10.md §2.1): column max (= the hero width, so copy and preview share a left edge), scene padding, hero width (720 at ≥ 1280, 560 at
// 1024-1279; the AUX-10 typing gate falls back to 640 if the larger frame ever costs a long frame), copy → hero gap
const SHEET_TOKENS =
  "[--signin-control-h:44px] pointer-coarse:[--signin-control-h:48px] [--control-h-lg:var(--signin-control-h)] [--signin-top:28px] min-[600px]:[--signin-top:clamp(12px,calc(20vh-168px),96px)] [--showcase-max:560px] xl:[--showcase-max:720px] [--showcase-pad:32px] xl:[--showcase-pad:clamp(32px,4vw,72px)] [--showcase-hero-w:min(100%,560px)] xl:[--showcase-hero-w:min(100%,720px)] [--showcase-gap:24px] xl:[--showcase-gap:32px]";

/**
 * `<b>…</b>` and `{var}` in a message → React nodes (the variables are inserted as text after splitting, so an
 * organisation name can never introduce markup).
 */
export function rich(template: string, vars: Record<string, ReactNode> = {}): ReactNode {
  const fill = (chunk: string, keyBase: string) =>
    chunk.split(/(\{\w+\})/g).map((part, i) => {
      const m = /^\{(\w+)\}$/.exec(part);
      return <Fragment key={`${keyBase}-${i}`}>{m && m[1]! in vars ? vars[m[1]!] : part}</Fragment>;
    });
  return template.split(/(<b>[\s\S]*?<\/b>)/g).map((seg, i) => {
    const bold = /^<b>([\s\S]*)<\/b>$/.exec(seg);
    return bold ? <strong key={i} className="font-semibold">{fill(bold[1]!, `b${i}`)}</strong> : <Fragment key={i}>{fill(seg, `t${i}`)}</Fragment>;
  });
}

/** Scroll the focused field into the middle of the visual viewport (iOS keyboard), §5.4. */
export function useKeyboardSafeFocus(root: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const center = (target: Element | null) => {
      if (!(target instanceof HTMLElement) || !el.contains(target) || !target.matches("input, textarea, select")) return;
      requestAnimationFrame(() => target.scrollIntoView({ block: "center", inline: "nearest" }));
    };
    const onFocus = (e: FocusEvent) => {
      if (!window.matchMedia("(pointer: coarse)").matches) return;
      center(e.target as Element);
    };
    const vv = window.visualViewport;
    const onResize = () => center(document.activeElement);
    el.addEventListener("focusin", onFocus);
    vv?.addEventListener("resize", onResize);
    return () => {
      el.removeEventListener("focusin", onFocus);
      vv?.removeEventListener("resize", onResize);
    };
  }, [root]);
}

/** University logo (`alt=""`: its name is in the subtitle) · hairline · the SmartSched mark + live text (§4.1). */
export function SignInBrand({ logoUrl }: { logoUrl?: string | null }) {
  return (
    <div className="flex h-12 items-center gap-3" data-testid="signin-brand">
      {logoUrl ? (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element -- uploaded by an administrator, served by the backend */}
          <img src={logoUrl} alt="" className="h-8 max-w-40 object-contain min-[600px]:h-10" data-testid="signin-org-logo" />
          <span aria-hidden className="h-7 w-px bg-(--hairline-strong)" />
        </>
      ) : null}
      <span className="flex items-center gap-2.5">
        <Logo variant="mark" size={32} decorative />
        <span className="type-title-3 font-semibold text-label-1">SmartSched</span>
      </span>
    </div>
  );
}

function ThemeButton() {
  const { t } = useI18n();
  const { theme } = useTheme();
  const cycle = useCycleTheme();
  const mounted = useSyncExternalStore(() => () => undefined, () => true, () => false);
  const mode = mounted && (theme === "light" || theme === "dark") ? theme : "system";
  const Icon = mode === "dark" ? Moon : mode === "light" ? Sun : Monitor;
  return (
    // the same height and track look as the TR/EN control beside it (44 fine, 50 touch), named by a tooltip too
    <Tooltip>
      <TooltipTrigger
        render={
          <IconButton label={`${t("nav.theme")}: ${t(`theme.${mode}`)}`} title="" onClick={cycle} className="size-11 rounded-full bg-fill-2 text-label-1 edge-hairline hover:bg-fill-1 pointer-coarse:size-[50px]" data-testid="theme-toggle">
            <Icon className="size-4" />
          </IconButton>
        }
      />
      <TooltipContent side="top">
        {t("nav.theme")}: {t(`theme.${mode}`)}
      </TooltipContent>
    </Tooltip>
  );
}

export function SignInFooter({ kvkkUrl }: { kvkkUrl?: string | null }) {
  const { t, locale, setLocale, languages } = useI18n();
  const router = useRouter();
  const reduce = useReduce();
  const langs: readonly Locale[] = languages.length ? languages : ["tr", "en"];
  return (
    // door 2 opening pushes the footer: it moves on transform only (layout="position", §10 "the column makes room")
    <motion.footer layout={reduce ? false : "position"} transition={springs.smooth} className="mt-auto flex flex-wrap items-center justify-between gap-x-4 gap-y-2 pt-6 min-[600px]:[@media(max-height:960px)]:pt-3" aria-label={t("signin.footer.region")}>
      <div className="flex min-h-11 items-center gap-4 type-footnote">
        {kvkkUrl ? (
          <a href={kvkkUrl} target="_blank" rel="noreferrer" className="inline-flex min-h-11 items-center px-1.5 text-tint-text underline-offset-4 outline-hidden hover:underline focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)" data-testid="signin-kvkk">
            {t("signin.footer.kvkk")}
          </a>
        ) : null}
      </div>
      <div className="flex items-center gap-2">
        <SegmentedControl
          semantics="radiogroup"
          size="md"
          collapse={false}
          aria-label={t("signin.footer.language")}
          value={locale}
          onValueChange={(v) => {
            if (v === locale) return;
            setLocale(v);
            router.refresh();
          }}
          options={langs.map((l) => ({ value: l, text: LOCALE_INFO[l].name, label: <span lang={l}>{l.toUpperCase()}</span>, testId: `locale-option-${l}` }))}
          data-testid="locale-toggle"
          // touch: the segments themselves are ≥ 44 px tall (track 50 = 44 + 2 × 3 px inset), sign-in.md §11 targets
          // fine pointers: a 44 px track like the theme button beside it
          className="[--control-h-md:44px] pointer-coarse:[--control-h-md:50px] [&_[role=radio]]:min-w-12 [&_[role=radio]]:px-3"
        />
        <ThemeButton />
      </div>
    </motion.footer>
  );
}

/**
 * Sheet + scene. `children` is the column content between the brand row and the footer. `hero` (only `/login`) puts
 * the decorative sign-in hero in the scene area right of the sheet (auth.md §11.3; never on the 2FA step).
 */
export function SignInShell({ children, logoUrl, kvkkUrl, labelledBy = "signin-title", testId, hero = false }: { children: ReactNode; logoUrl?: string | null; kvkkUrl?: string | null; labelledBy?: string; testId?: string; hero?: boolean }) {
  const sheet = useRef<HTMLElement>(null);
  useKeyboardSafeFocus(sheet);
  return (
    <div className={`scene relative flex min-h-dvh w-full bg-fixed ${SHEET_TOKENS}`} style={{ "--signin-sheet-w": "clamp(400px, 36vw, 480px)" } as CSSProperties}>
      <main className={`flex w-full min-[600px]:p-2 ${hero ? "md:w-auto md:shrink-0" : ""}`} data-testid={testId}>
        <GlassPanel
          material="regular"
          radius="2xl"
          render={<section ref={sheet} aria-labelledby={labelledBy} />}
          // login-navbar-2026-10.md §4: every field rests on the opaque thick surface (the grey well at rest read as
          // disabled next to the focused, white identifier); focus is the ring and halo
          // no backdrop blur on the sheet (decision 2026-10-19): it sits over the scene's smooth gradient, where a blur
          // changes nothing visible, but a CPU-only renderer re-blurred the 480 x 884 px area for every frame while the
          // person typed (50-75 ms frames; AUX-10 asks for typing under 50 ms). The material's tint stays.
          className="flex w-full flex-col [--mat-regular-filter:none] [&_[data-slot=input]]:bg-(--mat-thick) [&_[data-slot=input]:hover]:bg-(--mat-thick) max-[599px]:min-h-dvh max-[599px]:rounded-none max-[599px]:shadow-none max-[599px]:pl-[max(1rem,env(safe-area-inset-left))] max-[599px]:pr-[max(1rem,env(safe-area-inset-right))] max-[599px]:pt-[max(16px,env(safe-area-inset-top))] max-[599px]:pb-[max(8px,env(safe-area-inset-bottom))] min-[600px]:h-[calc(100dvh-16px)] min-[600px]:w-(--signin-sheet-w) min-[600px]:overflow-y-auto min-[600px]:overscroll-contain min-[600px]:pl-[max(2rem,env(safe-area-inset-left))] min-[600px]:pr-[max(2rem,env(safe-area-inset-right))] min-[600px]:pt-8 min-[600px]:[@media(max-height:960px)]:pt-5 min-[600px]:pb-4 lg:pl-[max(2.5rem,env(safe-area-inset-left))] lg:pr-[max(2.5rem,env(safe-area-inset-right))] lg:pb-5 [scroll-padding-block:24px] contrast-more:bg-(--mat-regular-solid) forced-colors:bg-[Canvas] forced-colors:border forced-colors:border-[CanvasText]"
          data-testid="signin-sheet"
        >
          <div className="flex w-full max-w-[400px] flex-1 flex-col">
            <SignInBrand logoUrl={logoUrl} />
            {/* ≥ 600 px the doors sit in the middle of the sheet (login-navbar-2026-10.md §2.2); with a full column (door 2 +
                an error + passkey) my-auto is 0, so the footer stays where sign-in #25 needs it. Phones stay top-aligned. */}
            <div className="flex flex-1 flex-col pt-(--signin-top)">
              <div className="min-[600px]:my-auto">{children}</div>
              {/* phones and narrow tablets have no showcase aside: the value lines sit quietly under the form */}
              {hero ? <SignInValueList compact className="mt-10 mb-2 md:hidden" /> : null}
            </div>
            <SignInFooter kvkkUrl={kvkkUrl} />
          </div>
        </GlassPanel>
      </main>
      {hero ? (
        <SignInShowcase
          hero={
            // the frame's width comes from --showcase-hero-w on the scene (the hero is memoised and takes no props)
            <SignInHero />
          }
        />
      ) : null}
    </div>
  );
}

