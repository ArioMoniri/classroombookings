"use client";
/**
 * /welcome — first Microsoft sign-in that created or bound the account (docs/design/v2/sign-in.md §6.4). Shown once:
 * /login/sso leaves a one-time flag in sessionStorage and this page consumes it on mount, so a reload (or any visit
 * without the flag) goes to the role's home. Same sheet and brand row as /login; no toast on top (the page is the
 * confirmation). Optional second step: link a notification channel the institution switched on.
 *
 * Motion (§10, "Welcome check"): "The account now exists." The 28 px disc scales .8 → 1 and the check path draws
 * (pathLength 0 → 1) once on mount on springs.bouncySubtle (≤ 32 px, overshoot allowed, < 300 ms); reduced motion:
 * the static check; reduced transparency: the same (the disc is opaque).
 */
import { ChevronDown } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { MyChannels } from "@/components/channels/my-channels";
import { Button, buttonVariants } from "@/components/ui/button";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { crbs, useCrbsMe, useDepartments, useProfile } from "@/lib/api/crbs";
import { useMyChannels } from "@/lib/api/channels";
import { useSsoMe } from "@/lib/api/identity";
import { LOCALE_INFO, type Locale } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { springs, tween, useReduce } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { MicrosoftLogo } from "./microsoft-sign-in";
import { homeFor, parseWelcomeFlag, WELCOME_KEY, type WelcomeFlag } from "./signin-model";
import { rich, SignInShell } from "./signin-shell";

export function WelcomeCheck({ label }: { label: string }) {
  const reduce = useReduce();
  return (
    <motion.span
      role="img"
      aria-label={label}
      className="flex size-7 shrink-0 items-center justify-center rounded-full bg-status-feasible text-status-feasible-fg"
      initial={reduce ? false : { scale: 0.8 }}
      animate={{ scale: 1 }}
      transition={reduce ? { duration: 0 } : springs.bouncySubtle}
      data-testid="welcome-check"
    >
      <svg viewBox="0 0 16 16" width={16} height={16} aria-hidden fill="none">
        <motion.path d="M3.5 8.5l3 3 6-7" stroke="currentColor" strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" initial={{ pathLength: reduce ? 1 : 0 }} animate={{ pathLength: 1 }} transition={reduce ? { duration: 0 } : { duration: 0.18, delay: 0.06, ease: "easeOut" }} />
      </svg>
    </motion.span>
  );
}

export function WelcomeView({ logoUrl, kvkkUrl }: { logoUrl: string | null; kvkkUrl: string | null }) {
  const { t } = useI18n();
  const router = useRouter();
  const me = useCrbsMe();
  // undefined: not read yet; null: no flag (a reload or a direct visit)
  const [flag, setFlag] = useState<WelcomeFlag | null | undefined>(undefined);
  const read = useRef(false);
  useEffect(() => {
    if (read.current) return;
    read.current = true;
    const value = parseWelcomeFlag(sessionStorage.getItem(WELCOME_KEY));
    sessionStorage.removeItem(WELCOME_KEY);
    setFlag(value);
  }, []);
  const home = homeFor(me.data?.permissions);
  useEffect(() => {
    if (flag !== null) return;
    if (me.isError) router.replace("/login");
    else if (me.data) router.replace(home);
  }, [flag, me.data, me.isError, home, router]);

  return (
    <SignInShell logoUrl={logoUrl} kvkkUrl={kvkkUrl} testId="welcome-page">
      {flag ? <WelcomeBody flag={flag} home={home} /> : <h1 id="signin-title" className="sr-only">{t("signin.welcome.title")}</h1>}
    </SignInShell>
  );
}

function WelcomeBody({ flag, home }: { flag: WelcomeFlag; home: string }) {
  const { t, locale, setLocale } = useI18n();
  const router = useRouter();
  const me = useCrbsMe();
  const profile = useProfile();
  const sso = useSsoMe();
  const departments = useDepartments();
  const name = sso.data?.display_name || me.data?.full_name || me.data?.username || "";
  const email = sso.data?.email_at_login || me.data?.email || "";
  const role = profile.data?.role_name ?? "—";
  const deptId = profile.data?.department_id ?? null;
  const dept = deptId ? (departments.data?.find((d) => d.id === deptId)?.name ?? "—") : "—";
  const subtitle = flag.kind === "self" ? t("signin.welcome.self") : flag.kind === "bound" ? t("signin.welcome.bound") : flag.inviter ? rich(t("signin.welcome.invited"), { inviter: flag.inviter }) : t("signin.welcome.invitedNoName");
  const target = flag.next ?? home;
  const setLanguage = (l: Locale) => {
    if (l === locale) return;
    setLocale(l);
    // the profile language is what every later session uses (CRBS: per user)
    void crbs.auth.putProfile({ language: l }).catch(() => undefined);
    router.refresh();
  };
  return (
    <div className="flex flex-col" data-testid={`welcome-${flag.kind}`}>
      <h1 id="signin-title" className="flex items-center gap-3 type-large-title text-label-1">
        <WelcomeCheck label={t("signin.welcome.checkLabel")} />
        <span>{flag.kind === "bound" ? t("signin.welcome.titleBound") : t("signin.welcome.title")}</span>
      </h1>
      <p className="mt-1.5 type-callout text-label-2">{subtitle}</p>

      <div className="mt-6 rounded-xl bg-(--mat-thick-solid) p-4 edge-hairline" data-testid="welcome-identity">
        <div className="flex items-start gap-3">
          <MicrosoftLogo size={16} className="mt-1" />
          <div className="min-w-0">
            <p className="type-headline text-label-1">{name || "—"}</p>
            <p className="truncate type-footnote text-label-2">{email || t("signin.welcome.identity")}</p>
          </div>
        </div>
        <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 type-callout">
          <dt className="text-label-2">{t("signin.welcome.role")}</dt>
          <dd className="font-semibold text-label-1" data-testid="welcome-role">{role}</dd>
          <dt className="text-label-2">{t("signin.welcome.department")}</dt>
          <dd className="text-label-1">{dept}</dd>
        </dl>
      </div>
      <p className="mt-3 type-footnote text-label-2" data-testid="welcome-note">
        {flag.kind === "self" ? t("signin.welcome.noteSelf") : t("signin.welcome.noteInvited")}
      </p>

      <div className="mt-6 flex flex-col gap-2">
        <span id="welcome-lang" className="type-callout font-semibold text-label-1">
          {t("signin.welcome.language")}
        </span>
        <SegmentedControl
          semantics="radiogroup"
          aria-labelledby="welcome-lang"
          collapse={false}
          value={locale}
          onValueChange={setLanguage}
          options={(["tr", "en"] as const).map((l) => ({ value: l, label: <span lang={l}>{LOCALE_INFO[l].name}</span>, text: LOCALE_INFO[l].name, testId: `welcome-lang-${l}` }))}
          className="self-start [&_[role=radio]]:min-w-24"
        />
      </div>

      <WelcomeChannels />

      <div className="mt-6 flex flex-wrap items-center gap-x-4 gap-y-2">
        <Button size="lg" shape="rect" onClick={() => (router.replace(target), router.refresh())} data-testid="welcome-continue">
          {t("signin.welcome.continue")}
        </Button>
        <Link href="/profile" className={cn(buttonVariants({ variant: "link" }), "min-h-11 type-callout")} data-testid="welcome-profile">
          {t("signin.welcome.profile")}
        </Link>
      </div>
    </div>
  );
}

/** The optional "link a notification channel" step: only when the institution switched a channel on. */
function WelcomeChannels() {
  const { t } = useI18n();
  const reduce = useReduce();
  const q = useMyChannels();
  const [open, setOpen] = useState(false);
  if (!q.data?.available.some((a) => a.link !== "department")) return null;
  return (
    <div className="mt-6 pt-2 hairline-t" data-testid="welcome-channels">
      <Button type="button" variant="ghost" shape="rect" size="lg" aria-expanded={open} aria-controls="welcome-channels-body" onClick={() => setOpen((o) => !o)} className={cn("-mx-2 w-[calc(100%+16px)] justify-between px-2 text-left type-callout font-semibold whitespace-normal active:scale-100")}>
        <span>{t("signin.welcome.channelsTitle")}</span>
        <motion.span aria-hidden className="flex" animate={{ rotate: open ? 180 : 0 }} transition={reduce ? { duration: 0 } : springs.snappy}>
          <ChevronDown className="size-4" />
        </motion.span>
      </Button>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div id="welcome-channels-body" key="body" initial={{ opacity: 0 }} animate={{ opacity: 1, transition: reduce ? tween.reduced : tween.fadeIn }} exit={{ opacity: 0, transition: reduce ? tween.reduced : tween.exit }} className="pt-2">
            <p className="mb-3 type-footnote text-label-2">{t("signin.welcome.channelsLead")}</p>
            <MyChannels compact />
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
