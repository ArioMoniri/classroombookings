"use client";
/**
 * A local-password invitation on /login?invite=<token> (wave 3b W3-IDP): the invited person sets a password and is
 * signed in. Shown only when the invite's provider is ``local`` (read client side from
 * ``GET /auth/sso/invites/{token}``; the identity-provider invites keep the provider button flow).
 * AUX-05 / ask A3 (docs/design/v3/auth.md §4.5): the form is `SetPasswordForm` (one field with show/hide, no repeat
 * field, the length rule, the hidden username for password managers); `POST /auth/sso/invites/{token}/password`
 * answers a session through the route handler, so a second step or the enrolment follows when the policy needs it.
 */
import { useQuery } from "@tanstack/react-query";
import { SetPasswordForm } from "@/components/auth/set-password-form";
import { idp } from "./providers-api";

export function useInviteProvider(token: string | null) {
  return useQuery({
    queryKey: ["identity", "invite-provider", token],
    queryFn: () => idp.publicInvite(token ?? ""),
    enabled: !!token,
    retry: false,
    staleTime: 60_000,
  });
}

export function LocalInviteAccept({ token, org = null, next = null }: { token: string; org?: string | null; next?: string | null }) {
  const invite = useInviteProvider(token);
  return (
    <div data-testid="local-invite-form">
      <SetPasswordForm mode="invite" token={token} username={invite.data?.login_hint ?? null} org={org} next={next} />
    </div>
  );
}
