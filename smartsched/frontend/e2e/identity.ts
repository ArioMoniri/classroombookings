/**
 * Helpers for the identity specs (sign-in.spec.ts, channels.spec.ts) against the REAL backend.
 *
 * The login page renders its doors from `GET /org/public` on the Next server, so `page.route` cannot fake them:
 * the specs switch Microsoft sign-in on through the admin API with a syntactically valid but fake app
 * registration (random GUIDs; nothing ever reaches Microsoft: the specs only read the start link and the
 * backend's 302) and switch it off again afterwards, so the other specs keep the password form.
 */
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { request, type APIRequestContext } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD } from "./helpers";

export const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";

export interface Admin {
  ctx: APIRequestContext;
  get<T>(path: string): Promise<T>;
  send<T>(method: "POST" | "PUT" | "DELETE", path: string, body?: unknown): Promise<{ status: number; body: T }>;
  dispose(): Promise<void>;
}

export async function adminApi(): Promise<Admin> {
  const ctx = await request.newContext();
  const login = await ctx.post(`${API}/auth/login`, { data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD } });
  if (!login.ok()) throw new Error(`admin login failed: ${login.status()}`);
  const { access_token: token } = (await login.json()) as { access_token: string };
  const headers = { Authorization: `Bearer ${token}` };
  return {
    ctx,
    async get<T>(path: string) {
      const r = await ctx.get(`${API}${path}`, { headers });
      if (!r.ok()) throw new Error(`GET ${path} → ${r.status()} ${await r.text()}`);
      return (await r.json()) as T;
    },
    async send<T>(method: "POST" | "PUT" | "DELETE", path: string, body?: unknown) {
      const r = await ctx.fetch(`${API}${path}`, { method, headers, data: body });
      const text = await r.text();
      return { status: r.status(), body: (text ? JSON.parse(text) : null) as T };
    },
    dispose: () => ctx.dispose(),
  };
}

/** A public URL is required to enable Microsoft sign-in (the redirect URI is built from it). */
export async function ensurePublicUrl(admin: Admin, baseURL: string): Promise<string | null> {
  const s = await admin.get<{ public_url: string | null; public_url_source: string | null }>("/calendar/admin/settings");
  if (s.public_url) return null;
  const origin = new URL(baseURL).origin;
  const r = await admin.send("PUT", "/calendar/admin/settings", { public_url: origin });
  if (r.status >= 400) throw new Error(`public_url: ${r.status} ${JSON.stringify(r.body)}`);
  return ""; // restore to empty afterwards
}

export async function enableMicrosoft(admin: Admin, over: Record<string, unknown> = {}): Promise<void> {
  // a fake registration: GUID-shaped ids and a placeholder secret built at run time (never a real credential)
  const secret = ["e2e", "placeholder", randomUUID().slice(0, 8)].join("-");
  const r = await admin.send("PUT", "/auth/sso/admin/entra", { tenant_id: randomUUID(), client_id: randomUUID(), client_secret: secret, domain_hint: "ornek.edu.tr", self_signup: true, oidc_only_non_admins: false, enabled: true, ...over });
  if (r.status >= 400) throw new Error(`enable Microsoft: ${r.status} ${JSON.stringify(r.body)}`);
}

export async function configureMicrosoft(admin: Admin, body: Record<string, unknown>): Promise<void> {
  const r = await admin.send("PUT", "/auth/sso/admin/entra", body);
  if (r.status >= 400) throw new Error(`configure Microsoft: ${r.status} ${JSON.stringify(r.body)}`);
}

export async function disableMicrosoft(admin: Admin): Promise<void> {
  await admin.send("PUT", "/auth/sso/admin/entra", { oidc_only_non_admins: false, enabled: false });
}

/**
 * Mint a one-time Microsoft sign-in ticket exactly as the callback does (e2e/tools/mint_sso_ticket.py). Needs
 * `E2E_SSO_MINT`: a command that runs that tool with the e2e backend's environment and prints the URL. `null`
 * when unavailable (pod CI runs the backend in another container).
 */
export function mintTicket(email: string, welcome: "" | "self" | "invited" | "bound", inviter = "", next = ""): string | null {
  const cmd = process.env.E2E_SSO_MINT;
  if (!cmd) return null;
  const out = execFileSync(cmd, [email, welcome, inviter, next], { encoding: "utf8", timeout: 60_000 }).trim();
  const url = new URL(out.split("\n").pop() ?? "");
  return `${url.pathname}${url.search}`;
}

export const MINT_SKIP = "set E2E_SSO_MINT to a command that runs e2e/tools/mint_sso_ticket.py with the backend's environment (the Microsoft round trip itself needs a real tenant)";

/** WCAG contrast of two sRGB colours (`rgb()` / `rgba()` over an opaque background). */
export function contrast(fg: [number, number, number], bg: [number, number, number]): number {
  const lum = ([r, g, b]: [number, number, number]) => {
    const c = [r, g, b].map((v) => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * c[0]! + 0.7152 * c[1]! + 0.0722 * c[2]!;
  };
  const [a, b] = [lum(fg), lum(bg)].sort((x, y) => y - x) as [number, number];
  return (a + 0.05) / (b + 0.05);
}

export function parseColor(text: string): { rgb: [number, number, number]; a: number } {
  const m = /rgba?\(([^)]+)\)/.exec(text);
  if (!m) throw new Error(`not a colour: ${text}`);
  const p = m[1]!.split(/[ ,/]+/).filter(Boolean).map(Number);
  return { rgb: [p[0]!, p[1]!, p[2]!], a: p.length > 3 ? p[3]! : 1 };
}

export function over(fg: { rgb: [number, number, number]; a: number }, bg: [number, number, number]): [number, number, number] {
  return [0, 1, 2].map((i) => Math.round(fg.rgb[i]! * fg.a + bg[i]! * (1 - fg.a))) as [number, number, number];
}
