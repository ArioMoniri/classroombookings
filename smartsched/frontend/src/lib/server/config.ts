import "server-only";

export const AUTH_COOKIE = "smartsched_token";
export const COOKIE_MAX_AGE = 60 * 60 * 24 * 30; // 30 days ("keep me signed in")

export function isMockMode(): boolean {
  return process.env.NEXT_PUBLIC_API_MOCK === "1";
}

export function backendBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
}
