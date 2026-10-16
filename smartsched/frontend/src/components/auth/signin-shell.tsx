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
import { useAppVersion } from "@/lib/api/crbs";
import { LOCALE_INFO, type Locale } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { springs, useReduce } from "@/lib/motion";

/** Page-local tokens (§9). Control height 44 fine / 48 coarse also drives the fields (--control-h-lg). */
const SHEET_TOKENS =
  "[--signin-control-h:44px] pointer-coarse:[--signin-control-h:48px] [--control-h-lg:var(--signin-control-h)] [--signin-top:28px] min-[600px]:[--signin-top:clamp(24px,8vh,96px)]";

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
    <div className="flex h-11 items-center gap-3" data-testid="signin-brand">
      {logoUrl ? (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element -- uploaded by an administrator, served by the backend */}
          <img src={logoUrl} alt="" className="h-8 max-w-40 object-contain min-[600px]:h-10" data-testid="signin-org-logo" />
          <span aria-hidden className="h-7 w-px bg-(--hairline-strong)" />
        </>
      ) : null}
      <span className="flex items-center gap-2">
        <Logo variant="mark" size={24} decorative />
        <span className="type-headline text-label-1">SmartSched</span>
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
    <IconButton label={`${t("nav.theme")}: ${t(`theme.${mode}`)}`} onClick={cycle} className="size-11" data-testid="theme-toggle">
      <Icon className="size-4" />
    </IconButton>
  );
}

export function SignInFooter({ kvkkUrl }: { kvkkUrl?: string | null }) {
  const { t, locale, setLocale, languages } = useI18n();
  const router = useRouter();
  const version = useAppVersion();
  const reduce = useReduce();
  const langs: readonly Locale[] = languages.length ? languages : ["tr", "en"];
  return (
    // door 2 opening pushes the footer: it moves on transform only (layout="position", §10 "the column makes room")
    <motion.footer layout={reduce ? false : "position"} transition={springs.smooth} className="mt-auto flex flex-wrap items-center justify-between gap-x-4 gap-y-2 pt-6" aria-label={t("signin.footer.region")}>
      <div className="flex min-h-11 items-center gap-4 type-footnote">
        {kvkkUrl ? (
          <a href={kvkkUrl} target="_blank" rel="noreferrer" className="inline-flex min-h-11 items-center px-1.5 text-tint-text underline-offset-4 outline-hidden hover:underline focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)" data-testid="signin-kvkk">
            {t("signin.footer.kvkk")}
          </a>
        ) : null}
        <span className="text-label-3 tabular-nums" data-testid="app-version">
          {version.data ? t("signin.footer.version", { version: version.data }) : ""}
        </span>
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
          className="pointer-coarse:[--control-h-md:50px] [&_[role=radio]]:min-w-11 [&_[role=radio]]:px-3"
        />
        <ThemeButton />
      </div>
    </motion.footer>
  );
}

/**
 * Sheet + scene. `children` is the column content between the brand row and the footer.
 */
export function SignInShell({ children, logoUrl, kvkkUrl, labelledBy = "signin-title", testId }: { children: ReactNode; logoUrl?: string | null; kvkkUrl?: string | null; labelledBy?: string; testId?: string }) {
  const sheet = useRef<HTMLElement>(null);
  useKeyboardSafeFocus(sheet);
  return (
    <div className={`scene relative flex min-h-dvh w-full bg-fixed ${SHEET_TOKENS}`} style={{ "--signin-sheet-w": "clamp(400px, 36vw, 480px)" } as CSSProperties}>
      <main className="flex w-full min-[600px]:p-2" data-testid={testId}>
        <GlassPanel
          material="regular"
          radius="2xl"
          render={<section ref={sheet} aria-labelledby={labelledBy} />}
          className="flex w-full flex-col max-[599px]:min-h-dvh max-[599px]:rounded-none max-[599px]:shadow-none max-[599px]:px-4 max-[599px]:pt-[max(16px,env(safe-area-inset-top))] max-[599px]:pb-[max(8px,env(safe-area-inset-bottom))] min-[600px]:h-[calc(100dvh-16px)] min-[600px]:w-(--signin-sheet-w) min-[600px]:overflow-y-auto min-[600px]:overscroll-contain min-[600px]:px-8 min-[600px]:pt-8 min-[600px]:pb-4 lg:px-10 lg:pb-5 [scroll-padding-block:24px] contrast-more:bg-(--mat-regular-solid) forced-colors:bg-[Canvas] forced-colors:border forced-colors:border-[CanvasText]"
          data-testid="signin-sheet"
        >
          <div className="flex w-full max-w-[400px] flex-1 flex-col">
            <SignInBrand logoUrl={logoUrl} />
            <div className="flex flex-1 flex-col pt-(--signin-top)">{children}</div>
            <SignInFooter kvkkUrl={kvkkUrl} />
          </div>
        </GlassPanel>
      </main>
    </div>
  );
}

