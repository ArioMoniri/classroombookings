import "server-only";

export const AUTH_COOKIE = "smartsched_token";
/** Fallback only: the login handler uses the backend token lifetime (`expires_in`, 12 h by default). */
export const COOKIE_MAX_AGE = 60 * 60 * 12;

export function backendBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
}
