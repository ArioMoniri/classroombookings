"use client";
/**
 * The /login provider buttons when more than the Microsoft provider is on (wave 3b W3-IDP; design
 * docs/design/v3/integrations.md §6, which amends sign-in.md §7): every identity-provider button has the same size and
 * weight, in the administrators' order; at most three are visible, the rest open in place under
 * "Diğer giriş yolları (n)"; an invite link shows only the invited method's button.
 *
 * - Microsoft: the existing branded button (sign-in.md §7, unchanged).
 * - Google: Google's sign-in button rules (light #FFFFFF, 1 px #747775 edge, #1F1F1F text; dark #131314 / #8E918F /
 *   #E3E3E3), the four-colour G, "Google ile oturum açın".
 * - OIDC / SAML: neutral material fill, the provider's text monogram, "{name} ile giriş yap".
 *
 * Each button is a real navigation (`<a href>`) to the backend start route; the pressed one shows
 * "{name} sayfasına yönlendiriliyor…" and a second click is ignored.
 */
import { ChevronDown } from "lucide-react";
import { useEffect, useId, useState, type MouseEvent } from "react";
import { MicrosoftSignIn } from "@/components/auth/microsoft-sign-in";
import { BusyGlyph, useBusyDelay } from "@/components/ui/busy-label";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { buttonLayout, type ButtonLike } from "./providers-model";

export interface SignInProvider extends ButtonLike {
  label_en?: string;
  badge?: string;
  self_signup?: boolean;
}

function withQuery(
  base: string,
  q: {
    next?: string | null;
    invite?: string | null;
    loginHint?: string | null;
  },
): string {
  const safe = base.startsWith("/") && !base.startsWith("//") ? base : "/login";
  const params = new URLSearchParams();
  if (q.next) params.set("next", q.next);
  if (q.invite) params.set("invite", q.invite);
  if (q.loginHint) params.set("login_hint", q.loginHint);
  const s = params.toString();
  return s ? `${safe}?${s}` : safe;
}

export function GoogleG({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden focusable="false" className="shrink-0 [forced-color-adjust:none]" data-testid="google-logo">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}

function ProviderLink({ p, href, label, busyLabel, onNavigate }: { p: SignInProvider; href: string; label: string; busyLabel: string; onNavigate?: () => void }) {
  const [busy, setBusy] = useState(false);
  const shown = useBusyDelay(busy);
  useEffect(() => {
    const reset = (e: PageTransitionEvent) => e.persisted && setBusy(false);
    window.addEventListener("pageshow", reset);
    return () => window.removeEventListener("pageshow", reset);
  }, []);
  const onClick = (e: MouseEvent<HTMLAnchorElement>) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) return;
    if (busy) return e.preventDefault();
    setBusy(true);
    onNavigate?.();
  };
  const google = p.kind === "google_workspace";
  return (
    <>
      <a
        href={href}
        onClick={onClick}
        aria-disabled={busy || undefined}
        data-testid={`login-sso-${p.name}`}
        data-kind={p.kind}
        style={
          google
            ? {
                fontFamily: "Roboto, var(--font-inter), system-ui, sans-serif",
                fontSize: 14,
                boxShadow: "inset 0 0 0 1px var(--g-edge)",
              }
            : undefined
        }
        className={cn(
          "relative isolate flex h-(--signin-control-h,44px) w-full items-center justify-center gap-3 overflow-hidden rounded-lg px-3 leading-5 no-underline",
          "transition-transform duration-(--dur-fast) ease-(--spring-snappy) active:scale-[0.97] aria-disabled:cursor-progress pointer-coarse:min-h-12",
          "outline-hidden focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solid focus-visible:outline-(--focus)",
          "after:pointer-events-none after:absolute after:inset-0 after:rounded-[inherit] after:bg-black/[0.04] after:opacity-0 after:transition-opacity hover:after:opacity-100 dark:after:bg-white/[0.07]",
          google
            ? "[--g-bg:#ffffff] [--g-fg:#1f1f1f] [--g-edge:#747775] dark:[--g-bg:#131314] dark:[--g-fg:#e3e3e3] dark:[--g-edge:#8e918f] bg-(--g-bg) text-(--g-fg) font-medium"
            : "bg-(--mat-thick) text-label-1 type-callout font-semibold shadow-(--edge-control)",
          "forced-colors:border forced-colors:border-[ButtonText] forced-colors:bg-[ButtonFace] forced-colors:text-[ButtonText]",
        )}
      >
        {shown ? (
          <BusyGlyph className="size-[18px] shrink-0" />
        ) : google ? (
          <GoogleG />
        ) : (
          <span aria-hidden className="grid h-5 min-w-5 place-items-center rounded-[5px] bg-fill-2 px-1 type-caption font-bold tracking-tight text-label-2">
            {p.badge ?? "SSO"}
          </span>
        )}
        <span className="relative">{shown ? busyLabel : label}</span>
      </a>
      <span role="status" className="sr-only">
        {shown ? busyLabel : ""}
      </span>
    </>
  );
}

export function ProviderButtons({
  providers,
  invited = null,
  next = null,
  inviteToken = null,
  loginHint = null,
  onNavigate,
}: {
  providers: SignInProvider[];
  /** the slug of the invited method (``?invite=`` banner), else ``null`` */
  invited?: string | null;
  next?: string | null;
  inviteToken?: string | null;
  loginHint?: string | null;
  onNavigate?: (p: SignInProvider) => void;
}) {
  const { t, locale } = useI18n();
  const [open, setOpen] = useState(false);
  const moreId = useId();
  const layout = buttonLayout(providers, invited);
  const name = (p: SignInProvider) => (locale === "en" ? p.label_en || p.label : p.label);
  const href = (p: SignInProvider) =>
    withQuery(p.start_url, {
      next,
      invite: invited ? inviteToken : null,
      loginHint: invited ? loginHint : null,
    });
  const one = (p: SignInProvider) =>
    p.kind === "entra" ? (
      <MicrosoftSignIn key={p.name} href={href(p)} label={t("signin.microsoft.label")} busyLabel={t("signin.microsoft.busy")} onNavigate={() => onNavigate?.(p)} />
    ) : (
      <ProviderLink
        key={p.name}
        p={p}
        href={href(p)}
        label={p.kind === "google_workspace" ? t("identity.signin.google") : t("identity.signin.with", { name: name(p) })}
        busyLabel={t("identity.signin.busy", { name: name(p) })}
        onNavigate={() => onNavigate?.(p)}
      />
    );
  if (!layout.visible.length) return null;
  return (
    <div className="flex flex-col gap-3" data-testid="signin-providers" data-count={providers.length}>
      {layout.visible.map(one)}
      {layout.more.length ? (
        <>
          <Button
            type="button"
            variant="ghost"
            shape="rect"
            size="lg"
            aria-expanded={open}
            aria-controls={moreId}
            onClick={() => setOpen((o) => !o)}
            className="justify-between px-2 type-callout"
            data-testid="signin-more-providers"
          >
            <span>
              {t("identity.signin.more", {
                n: layout.more.length,
              })}
            </span>
            <ChevronDown aria-hidden className={cn("size-4 transition-transform", open && "rotate-180")} />
          </Button>
          {open ? (
            <div id={moreId} className="flex flex-col gap-3">
              {layout.more.map(one)}
            </div>
          ) : null}
        </>
      ) : null}
      {invited ? null : providers.some((p) => p.self_signup) ? <p className="type-footnote text-label-2">{t("identity.signin.footnote")}</p> : null}
    </div>
  );
}
