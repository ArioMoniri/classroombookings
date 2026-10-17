/**
 * Pin the interface language of a spec file instead of depending on defaults (e2e-stabilisation 2026-10-16).
 *
 * A session's language is the signed-in user's profile language, else the organisation's `default_language`
 * (applied on the first page of a session by useProfileLanguage); before sign-in it is the NEXT_LOCALE cookie,
 * else Turkish. Specs ran in whatever language the previous spec left behind (languages.spec.ts writes the seeded
 * admin's profile language; the product default moved from English to Turkish), so `pinLanguage("en")` at the top
 * of a spec file:
 *   beforeAll  sets the organisation default and the seeded admin's profile language (users the spec creates
 *              without a language follow the organisation default), remembering both;
 *   beforeEach adds the NEXT_LOCALE cookie to the test's browser context, so the first render is already right;
 *   afterAll   puts the organisation default and the admin's profile language back.
 * Contexts a test opens itself (`browser.newContext()`) get the language from the profile once signed in; give
 * them the cookie with `languageCookie(context, lang, baseURL)` when they assert before signing in.
 */
import { test, type BrowserContext } from "@playwright/test";
import { adminApi, API } from "./identity";

export type Lang = "tr" | "en";

export async function languageCookie(context: BrowserContext, lang: Lang, baseURL: string | undefined): Promise<void> {
  await context.addCookies([{ name: "NEXT_LOCALE", value: lang, url: baseURL ?? "http://127.0.0.1:3100" }]);
}

/** Set the organisation default and the seeded admin's profile language; returns what to put back. */
export async function setLanguage(lang: Lang): Promise<{ orgDefault: string; adminLanguage: string | null }> {
  const admin = await adminApi();
  try {
    const pub = (await (await admin.ctx.get(`${API}/org/public`)).json()) as { default_language: string };
    const me = await admin.get<{ language: string | null }>("/auth/profile");
    const org = await admin.send("PUT", "/org/settings", { default_language: lang });
    if (org.status >= 300) throw new Error(`PUT /org/settings default_language=${lang}: ${org.status} ${JSON.stringify(org.body)}`);
    const prof = await admin.send("PUT", "/auth/profile", { language: lang });
    if (prof.status >= 300) throw new Error(`PUT /auth/profile language=${lang}: ${prof.status} ${JSON.stringify(prof.body)}`);
    return { orgDefault: pub.default_language, adminLanguage: me.language };
  } finally {
    await admin.dispose();
  }
}

async function restoreLanguage(saved: { orgDefault: string; adminLanguage: string | null }): Promise<void> {
  const admin = await adminApi();
  try {
    await admin.send("PUT", "/org/settings", { default_language: saved.orgDefault });
    await admin.send("PUT", "/auth/profile", { language: saved.adminLanguage ?? "" });
  } finally {
    await admin.dispose();
  }
}

/** Call once at the top level of a spec file (after `test.skip(!REAL, …)`). */
export function pinLanguage(lang: Lang): void {
  let saved: { orgDefault: string; adminLanguage: string | null } | null = null;
  test.beforeAll(async () => {
    if (process.env.E2E_REAL !== "1") return;
    saved = await setLanguage(lang);
  });
  test.beforeEach(async ({ context, baseURL }) => {
    await languageCookie(context, lang, baseURL);
  });
  test.afterAll(async () => {
    if (saved) await restoreLanguage(saved);
    saved = null;
  });
}
