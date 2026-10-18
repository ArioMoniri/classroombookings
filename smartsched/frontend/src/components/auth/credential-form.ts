/**
 * HB18-F02 (security): the `<form>` attributes of every form that holds a credential (sign-in, second step, set /
 * change / reset password). With no `method`, a submit that happens before React hydrates is a native GET and puts
 * `?username=…&password=…` in the address bar, the history and every proxy log. `method="post"` keeps the fields out
 * of the URL, and `/api/auth/no-script` never reads the body: it only sends the browser back (303). The forms also
 * keep their submit disabled until hydrated (`useHydrated`), which blocks the button and Enter alike.
 */
export const CREDENTIAL_FORM = { method: "post", action: "/api/auth/no-script" } as const;

/** Query parameters that must never ride in a URL (the forms' field names). */
export const CREDENTIAL_PARAMS = ["password", "new-password", "new_password", "current-password", "current_password", "recovery_code", "otp"] as const;

/** `search` without credential parameters (and without `username` when one was there); `null` when nothing leaked. */
export function stripCredentialParams(search: URLSearchParams): URLSearchParams | null {
  if (!CREDENTIAL_PARAMS.some((k) => search.has(k))) return null;
  const out = new URLSearchParams(search);
  for (const k of [...CREDENTIAL_PARAMS, "username"]) out.delete(k);
  return out;
}
