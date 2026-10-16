/**
 * docs/design/v2/sign-in.md §15 — the 30 acceptance checks, against the REAL backend (E2E_REAL=1).
 *
 * Microsoft sign-in is switched on with a fake app registration through the admin API (e2e/identity.ts) and off
 * again at the end. The Microsoft round trip itself needs a real tenant; the specs check the start link and the
 * backend's 302 instead, the error pages via `?error=`, and the ticket exchange with a ticket minted by the
 * backend's own function (E2E_SSO_MINT, e2e/tools/mint_sso_ticket.py; skipped with the reason when unset).
 */
import { expect, test, type Page } from "@playwright/test";
import { REAL, SKIP_REASON } from "./helpers";
import { adminApi, contrast, disableMicrosoft, enableMicrosoft, configureMicrosoft, ensurePublicUrl, mintTicket, MINT_SKIP, over, parseColor, type Admin } from "./identity";
import path from "node:path";
import { pinLanguage } from "./language";

const AXE = path.resolve(process.cwd(), "node_modules/axe-core/axe.min.js");
const SIGNUP = /kaydol|kayıt ol|sign ?up|register|hesap oluştur|create account/i;
const START = "/api/v1/auth/sso/entra/start";

// alerts are read inside <main>: Next adds its own role="alert" route announcer to every page
test.describe.configure({ mode: "serial" });
test.skip(!REAL, SKIP_REASON);
// the assertions read Turkish (the product default): pin it, whatever the previous spec left behind
pinLanguage("tr");

let admin: Admin;
let restorePublicUrl: string | null = null;

test.beforeAll(async ({ baseURL }) => {
  admin = await adminApi();
  restorePublicUrl = await ensurePublicUrl(admin, baseURL ?? "http://127.0.0.1:3100");
  await enableMicrosoft(admin);
});

test.afterAll(async () => {
  await disableMicrosoft(admin);
  await admin.send("PUT", "/org/settings", { maintenance_mode: false });
  if (restorePublicUrl !== null) await admin.send("PUT", "/calendar/admin/settings", { public_url: restorePublicUrl || null });
  await admin.dispose();
});

async function open(page: Page, path: string, locale: "tr" | "en" = "tr") {
  const base = test.info().project.use.baseURL ?? "http://127.0.0.1:3100";
  await page.context().addCookies([{ name: "NEXT_LOCALE", value: locale, url: base }]);
  await page.goto(path);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
}

test.describe("doors and branding", () => {
  test("#1 Microsoft link: name, start route, next from the page URL (TR + EN)", async ({ page }) => {
    await open(page, "/login?next=/timetable");
    const ms = page.getByRole("link", { name: "Microsoft ile giriş yap" });
    await expect(ms).toBeVisible();
    const href = (await ms.getAttribute("href")) ?? "";
    expect(href.startsWith(START)).toBe(true);
    expect(new URL(href, "http://h").searchParams.get("next")).toBe("/timetable");
    await open(page, "/login", "en");
    await expect(page.getByRole("link", { name: "Sign in with Microsoft" })).toBeVisible();
  });

  test("#1b the start route answers with a real redirect to Microsoft (no fetch)", async ({ request, baseURL }) => {
    const res = await request.get(`${baseURL}${START}?next=/timetable`, { maxRedirects: 0 });
    expect(res.status()).toBe(302);
    expect(res.headers()["location"]).toMatch(/^https:\/\/login\.microsoftonline\.com\/[0-9a-f-]{36}\/oauth2\/v2\.0\/authorize\?/);
  });

  test("#2 official logo: four rects in Microsoft's colours at 21 × 21", async ({ page }) => {
    await open(page, "/login");
    const svg = page.getByTestId("microsoft-logo");
    const fills = await svg.locator("rect").evaluateAll((els) => els.map((e) => e.getAttribute("fill")));
    expect(fills).toEqual(["#f25022", "#7fba00", "#00a4ef", "#ffb900"]);
    const box = await svg.boundingBox();
    expect(Math.round(box!.width)).toBe(21);
    expect(Math.round(box!.height)).toBe(21);
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`#3 button colours, weight and size (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await open(page, "/login");
      const s = await page.getByTestId("login-sso-microsoft").evaluate((el) => {
        const c = getComputedStyle(el);
        return { bg: c.backgroundColor, fg: c.color, weight: c.fontWeight, size: c.fontSize, shadow: c.boxShadow };
      });
      expect(s.weight).toBe("600");
      expect(s.size).toBe("15px");
      expect(s.shadow).toContain("rgb(140, 140, 140)");
      expect(s.shadow).toContain("inset");
      if (scheme === "light") {
        expect(s.bg).toBe("rgb(255, 255, 255)");
        expect(s.fg).toBe("rgb(94, 94, 94)");
      } else {
        expect(s.bg).toBe("rgb(47, 47, 47)");
        expect(s.fg).toBe("rgb(255, 255, 255)");
      }
    });
  }

  test("#4 height ≥ 44 (fine), logo padding ≥ 12, logo-to-text gap 12", async ({ page }) => {
    await open(page, "/login");
    const m = await page.getByTestId("login-sso-microsoft").evaluate((el) => {
      const r = el.getBoundingClientRect();
      const logo = el.querySelector("svg")!.getBoundingClientRect();
      const label = el.querySelector("span")!.getBoundingClientRect();
      return { h: r.height, left: logo.left - r.left, gap: label.left - logo.right };
    });
    expect(m.h).toBeGreaterThanOrEqual(44);
    expect(m.left).toBeGreaterThanOrEqual(12);
    expect(Math.round(m.gap)).toBe(12);
  });

  test("#5 Microsoft disabled: no link, no disclosure, primary submit, ask-an-administrator", async ({ page }) => {
    await configureMicrosoft(admin, { enabled: false });
    try {
      await open(page, "/login");
      await expect(page.getByTestId("login-sso-microsoft")).toHaveCount(0);
      await expect(page.getByTestId("login-disclosure")).toHaveCount(0);
      await expect(page.getByTestId("login-submit")).toHaveAttribute("data-primary", "true");
      await expect(page.getByTestId("login-no-account")).toHaveText("Hesabınız yoksa bir yöneticiye başvurun.");
    } finally {
      await configureMicrosoft(admin, { enabled: true });
    }
  });

  test("#6 #7 no sign-up control; hint names the work or school account and the role; no Azure words", async ({ page }) => {
    const invite = await admin.send<{ link: string }>("POST", "/auth/sso/admin/invites", { email: `e2e.hint.${Date.now()}@ornek.edu.tr`, role: "TEACHER" });
    const token = new URL(invite.body.link).searchParams.get("invite") ?? "";
    for (const url of ["/login", `/login?invite=${token}`]) {
      await open(page, url);
      const texts = await page.locator("a, button").allInnerTexts();
      expect(texts.filter((x) => SIGNUP.test(x))).toEqual([]);
    }
    await open(page, "/login");
    const hints = page.getByTestId("signin-hints");
    await expect(hints).toContainText("iş veya okul hesab");
    const role = (await admin.get<{ auth: { self_signup_role_name: string } }>("/auth/sso/providers")).auth.self_signup_role_name;
    await expect(hints).toContainText(role);
    expect(await page.locator("body").innerText()).not.toMatch(/Azure|Active Directory|Entra|Office 365/);
    await open(page, "/login", "en");
    await expect(page.getByTestId("signin-hints")).toContainText("work or school account");
  });
});

test.describe("door 2", () => {
  test("#8 starts closed; fields out of the tree; Tab from the disclosure leaves the sheet's form", async ({ page }) => {
    await open(page, "/login");
    const d = page.getByTestId("login-disclosure");
    await expect(d).toHaveAttribute("aria-expanded", "false");
    await expect(page.locator("#identifier")).toHaveCount(0);
    await d.focus();
    await page.keyboard.press("Tab");
    const next = await page.evaluate(() => ({ inFooter: !!document.activeElement?.closest("footer"), testid: document.activeElement?.getAttribute("data-testid") }));
    expect(next.inFooter).toBe(true); // the KVKK link when the institution set one, else the language radiogroup
  });

  test("#9 #11 opening sets aria-expanded and focuses the identifier within 400 ms; reset link only in door 2", async ({ page }) => {
    await open(page, "/login");
    await expect(page.getByTestId("forgot-password")).toHaveCount(0);
    await page.getByTestId("login-disclosure").click();
    await expect(page.getByTestId("login-disclosure")).toHaveAttribute("aria-expanded", "true");
    await expect(page.locator("#identifier")).toBeFocused({ timeout: 400 });
    await expect(page.getByTestId("forgot-password")).toBeVisible();
  });

  test("#10 ?method=local opens it; with local sign-in off the disclosure is gone, the reset link too", async ({ page }) => {
    await open(page, "/login?method=local");
    await expect(page.getByTestId("login-disclosure")).toHaveAttribute("aria-expanded", "true");
    await configureMicrosoft(admin, { oidc_only_non_admins: true });
    try {
      await open(page, "/login");
      await expect(page.getByTestId("login-disclosure")).toHaveCount(0);
      await open(page, "/login?method=local");
      await expect(page.locator("#identifier")).toBeVisible();
      await expect(page.getByTestId("forgot-password")).toHaveCount(0);
    } finally {
      await configureMicrosoft(admin, { oidc_only_non_admins: false });
    }
  });

  async function failLogin(page: Page, identifier: string, password: string): Promise<string> {
    await open(page, "/login?method=local");
    await page.locator("#identifier").fill(identifier);
    await page.locator("#password").fill(password);
    await page.getByTestId("login-submit").click();
    const alert = page.getByRole("main").getByRole("alert");
    await expect(alert).toBeVisible();
    return (await alert.textContent()) ?? "";
  }

  test("#12 401: one generic alert, both fields invalid, password cleared, identifier kept, focus on the alert", async ({ page }) => {
    const text = await failLogin(page, "e2e-nobody", "wrong-password");
    expect(text).toContain("Kullanıcı adı, e-posta veya parola yanlış.");
    await expect(page.getByRole("main").getByRole("alert")).toHaveCount(1);
    await expect(page.locator("#identifier")).toHaveAttribute("aria-invalid", "true");
    await expect(page.locator("#password")).toHaveAttribute("aria-invalid", "true");
    await expect(page.locator("#password")).toHaveValue("");
    await expect(page.locator("#identifier")).toHaveValue("e2e-nobody");
    await expect(page.getByTestId("login-error")).toBeFocused();
  });

  test("#13 disabled, unknown and Microsoft-only accounts read byte-identical", async ({ page }) => {
    const stamp = Date.now();
    const pw = ["E2e", "pass", String(stamp)].join("-");
    await admin.send("POST", "/users", { username: `e2e-off-${stamp}`, email: `e2e.off.${stamp}@ornek.edu.tr`, role: "TEACHER", password: pw, is_active: false });
    await admin.send("POST", "/auth/sso/admin/invites", { email: `e2e.sso.${stamp}@ornek.edu.tr`, role: "TEACHER" });
    const disabled = await failLogin(page, `e2e-off-${stamp}`, pw);
    const unknown = await failLogin(page, `e2e-unknown-${stamp}`, pw);
    const ssoOnly = await failLogin(page, `e2e.sso.${stamp}@ornek.edu.tr`, pw);
    expect(unknown).toBe(disabled);
    expect(ssoOnly).toBe(disabled);
  });

  test("#14 429 shows the minutes and disables submit; offline shows the offline string", async ({ page }) => {
    await page.route("**/api/v1/auth/login", (r) => r.fulfill({ status: 429, headers: { "retry-after": "180", "content-type": "application/json" }, body: "{}" }));
    expect(await failLogin(page, "e2e-rate", "x")).toContain("3 dakika sonra");
    await expect(page.getByTestId("login-submit")).toBeDisabled();
    await page.unroute("**/api/v1/auth/login");
    await page.route("**/api/v1/auth/login", (r) => r.abort("internetdisconnected"));
    expect(await failLogin(page, "e2e-offline", "x")).toContain("Sunucuya ulaşılamıyor.");
  });
});

test.describe("SSO states", () => {
  const CODES: [string, string, string][] = [
    ["failed", "Giriş yapılamadı.", "We couldn't sign you in."],
    ["unavailable", "Microsoft'a şu anda ulaşılamıyor.", "Microsoft can't be reached right now."],
    ["tenant", "Bu hesapla giriş yapılamıyor.", "This account can't be used here."],
    ["signup_closed", "Hesabınız yok.", "No account yet."],
    ["invite_expired", "Davetin süresi doldu.", "This invitation has expired."],
    ["invite_invalid", "Bu davet artık geçerli değil.", "This invitation is no longer valid."],
    ["invite_mismatch", "Davet başka bir adres için.", "The invitation is for another address."],
  ];
  for (const [code, trText, enText] of CODES) {
    test(`#15 ?error=${code}: alert, focused, TR + EN`, async ({ page }) => {
      await open(page, `/login?error=${code}&ref=S-7`);
      await expect(page.getByRole("main").getByRole("alert")).toContainText(trText);
      await expect(page.getByTestId("signin-error-focus")).toBeFocused();
      await open(page, `/login?error=${code}&ref=S-7`, "en");
      await expect(page.getByRole("main").getByRole("alert")).toContainText(enText);
    });
  }

  test("#15b /profile?error=already_linked", async ({ page }) => {
    await page.goto("/login?method=local");
    await page.locator("#identifier").fill(process.env.E2E_ADMIN_EMAIL ?? "admin@smartsched.local");
    await page.locator("#password").fill(process.env.E2E_ADMIN_PASSWORD ?? "Admin-2026!");
    await page.getByTestId("login-submit").click();
    await page.waitForURL((u) => !u.pathname.startsWith("/login"));
    await page.goto("/profile?error=already_linked");
    await expect(page.getByTestId("profile-sso-error")).toContainText(/Microsoft/);
  });

  test("#16 failed and an unknown code render identical text", async ({ page }) => {
    await open(page, "/login?error=failed&ref=7F3A-21C");
    const a = await page.getByRole("main").getByRole("alert").textContent();
    await open(page, "/login?error=nonsense&ref=7F3A-21C");
    expect(await page.getByRole("main").getByRole("alert").textContent()).toBe(a);
    expect(a).toContain("7F3A-21C");
  });

  test("#17 tenant and mismatch restart with select_account (+ login_hint)", async ({ page }) => {
    await open(page, "/login?error=tenant");
    const t1 = new URL((await page.getByTestId("signin-try-another").getAttribute("href"))!, "http://h");
    expect(t1.pathname).toBe(START);
    expect(t1.searchParams.get("prompt")).toBe("select_account");
    const inv = await admin.send<{ link: string }>("POST", "/auth/sso/admin/invites", { email: `e2e.mm.${Date.now()}@ornek.edu.tr`, role: "TEACHER" });
    const token = new URL(inv.body.link).searchParams.get("invite") ?? "";
    await open(page, `/login?error=invite_mismatch&invite=${token}&invited_masked=e2•••@ornek.edu.tr&signed_in=ba•••@ornek.edu.tr`);
    await expect(page.getByRole("main").getByRole("alert")).toContainText("e2•••@ornek.edu.tr");
    const t2 = new URL((await page.getByTestId("signin-switch-account").getAttribute("href"))!, "http://h");
    expect(t2.searchParams.get("prompt")).toBe("select_account");
    expect(t2.searchParams.get("login_hint")).toMatch(/^e2e\.mm\.\d+@ornek\.edu\.tr$/);
  });

  test("#18 cancelled is a status and does not take focus", async ({ page }) => {
    await open(page, "/login?error=cancelled");
    await expect(page.getByRole("main").getByRole("alert")).toHaveCount(0);
    await expect(page.getByTestId("signin-notice-cancelled")).toHaveAttribute("role", "status");
    expect(await page.evaluate(() => document.activeElement === document.body)).toBe(true);
  });

  test("#19 ?reason=expired&next=/timetable: notice; both doors carry next; an external next is dropped", async ({ page }) => {
    await open(page, "/login?reason=expired&next=/timetable");
    await expect(page.getByTestId("login-session-notice")).toContainText("Oturumunuzun süresi doldu.");
    expect(await page.getByTestId("login-sso-microsoft").getAttribute("href")).toContain("next=%2Ftimetable");
    // the password door: a successful sign-in lands on next
    await page.getByTestId("login-disclosure").click();
    await page.locator("#identifier").fill(process.env.E2E_ADMIN_EMAIL ?? "admin@smartsched.local");
    await page.locator("#password").fill(process.env.E2E_ADMIN_PASSWORD ?? "Admin-2026!");
    await page.getByTestId("login-submit").click();
    await page.waitForURL((u) => u.pathname === "/timetable", { timeout: 30_000 });
    // leave the app first: with the cookies gone the timetable would bounce to /login itself mid-navigation
    await page.goto("about:blank");
    await page.context().clearCookies();
    await open(page, "/login?next=//evil.example");
    expect(await page.getByTestId("login-sso-microsoft").getAttribute("href")).toBe(START);
  });

  test("#20 maintenance: warning notice with glyph and the message; sign-in still offered", async ({ page }) => {
    await admin.send("PUT", "/org/settings", { maintenance_mode: true, maintenance_mode_message: "Rezervasyonlar 18:00'e kadar durduruldu." });
    try {
      await open(page, "/login");
      const n = page.getByTestId("login-maintenance");
      await expect(n).toContainText("Rezervasyonlar bakımda.");
      await expect(n).toContainText("18:00");
      await expect(n.locator("svg").first()).toBeVisible();
      await expect(page.getByTestId("login-sso-microsoft")).toBeVisible();
    } finally {
      await admin.send("PUT", "/org/settings", { maintenance_mode: false });
    }
  });
});

test.describe("invite and welcome", () => {
  test("#21 invite banner (inviter, role, masked address, days), no disclosure, start link with invite + login_hint", async ({ page }) => {
    const email = `e2e.inv.${Date.now()}@ornek.edu.tr`;
    const inv = await admin.send<{ link: string }>("POST", "/auth/sso/admin/invites", { email, role: "TEACHER" });
    const token = new URL(inv.body.link).searchParams.get("invite") ?? "";
    await open(page, `/login?invite=${token}`);
    const banner = page.getByTestId("signin-invite");
    await expect(banner).toContainText("sizi SmartSched'e davet etti.");
    await expect(banner).toContainText("e2•••@ornek.edu.tr");
    await expect(banner).toContainText("gün geçerli");
    await expect(page.getByTestId("login-disclosure")).toHaveCount(0);
    const u = new URL((await page.getByTestId("login-sso-microsoft").getAttribute("href"))!, "http://h");
    expect(u.searchParams.get("invite")).toBe(token);
    expect(u.searchParams.get("login_hint")).toBe(email);
  });

  test("#22 first-login welcome; reload without the flag redirects; invited names the inviter", async ({ page }) => {
    const self = mintTicket(process.env.E2E_ADMIN_EMAIL ?? "admin@smartsched.local", "self");
    test.skip(!self, MINT_SKIP);
    await page.goto(self!);
    await page.waitForURL(/\/welcome$/);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Hesabınız oluşturuldu");
    await expect(page.getByTestId("welcome-role")).not.toHaveText("—");
    await expect(page.getByTestId("welcome-note")).toContainText("Rolünüzü yalnızca bir yönetici değiştirebilir.");
    expect((await page.locator("a, button").allInnerTexts()).filter((x) => SIGNUP.test(x))).toEqual([]);
    await page.reload();
    await page.waitForURL((u) => u.pathname !== "/welcome");
    const invited = mintTicket(process.env.E2E_ADMIN_EMAIL ?? "admin@smartsched.local", "invited", "Fatih Demir");
    await page.goto(invited!);
    await page.waitForURL(/\/welcome\?invited=1$/);
    await expect(page.getByTestId("welcome-invited")).toContainText("Fatih Demir");
    await page.getByTestId("welcome-continue").click();
    await page.waitForURL((u) => u.pathname === "/dashboard" || u.pathname === "/bookings");
  });

  test("#22b a used ticket lands on the generic failure", async ({ page }) => {
    const url = mintTicket(process.env.E2E_ADMIN_EMAIL ?? "admin@smartsched.local", "");
    test.skip(!url, MINT_SKIP);
    await page.goto(url!);
    await page.waitForURL((u) => !u.pathname.startsWith("/login"));
    await page.context().clearCookies();
    await page.goto(url!);
    await page.waitForURL(/\/login\?error=failed/);
    await expect(page.getByRole("main").getByRole("alert")).toContainText("Giriş yapılamadı.");
  });
});

test.describe("layout, keyboard, a11y", () => {
  for (const vp of [
    { name: "390", width: 390, height: 844, isMobile: true },
    { name: "768", width: 768, height: 1024, isMobile: false },
  ]) {
    test.describe(`touch ${vp.name}`, () => {
      test.use({ viewport: { width: vp.width, height: vp.height }, hasTouch: true, isMobile: vp.isMobile });
      test(`#23 no horizontal overflow; every control ≥ 44 × 44 (${vp.name})`, async ({ page }) => {
        await open(page, "/login?method=local");
        const m = await page.evaluate(() => {
          const small = [...document.querySelectorAll<HTMLElement>("main a, main button, main input, main [role=radio]")]
            .filter((el) => el.offsetParent !== null)
            .map((el) => ({ el, r: el.getBoundingClientRect() }))
            .filter(({ r }) => r.width < 44 - 0.5 || r.height < 44 - 0.5)
            .map(({ el, r }) => `${el.tagName}#${el.id || el.getAttribute("data-testid") || el.textContent?.trim().slice(0, 20)} ${Math.round(r.width)}×${Math.round(r.height)}`);
          return { overflow: document.documentElement.scrollWidth - window.innerWidth, small };
        });
        expect(m.overflow).toBeLessThanOrEqual(0);
        expect(m.small).toEqual([]);
      });
    });
  }

  test.describe("keyboard at 390", () => {
    test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
    test("#24 with the keyboard open the password and the submit stay in view", async ({ page }) => {
      await open(page, "/login?method=local");
      await page.locator("#password").focus();
      await page.setViewportSize({ width: 390, height: 508 });
      await page.locator("#password").evaluate((el) => el.scrollIntoView({ block: "center" }));
      await page.waitForTimeout(150);
      for (const sel of ["#password", "[data-testid=login-submit]"]) {
        const b = (await page.locator(sel).boundingBox())!;
        expect(b.y).toBeGreaterThanOrEqual(0);
        expect(b.y + b.height).toBeLessThanOrEqual(508);
      }
    });
  });

  test("#25 1440 × 900, door 2 open with an error: the footer is visible without scrolling", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await open(page, "/login?method=local");
    await page.locator("#identifier").fill("e2e-nobody");
    await page.locator("#password").fill("wrong");
    await page.getByTestId("login-submit").click();
    await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
    await expect(page.locator("footer").first()).toBeInViewport({ ratio: 1 });
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`#26 field boundary ≥ 3:1 against the sheet's solid fallback (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await open(page, "/login?method=local");
      const v = await page.evaluate(() => {
        const cs = getComputedStyle(document.documentElement);
        const probe = document.createElement("div");
        document.body.append(probe);
        probe.style.color = cs.getPropertyValue("--border-control");
        const border = getComputedStyle(probe).color;
        probe.style.color = cs.getPropertyValue("--mat-regular-solid");
        const sheet = getComputedStyle(probe).color;
        probe.remove();
        return { border, sheet };
      });
      const bg = parseColor(v.sheet).rgb;
      expect(contrast(over(parseColor(v.border), bg), bg)).toBeGreaterThanOrEqual(3);
    });
  }

  test("#27 placeholders differ from their labels", async ({ page }) => {
    await open(page, "/login?method=local");
    const label = (await page.locator("label[for=identifier]").textContent())?.trim();
    expect(await page.locator("#identifier").getAttribute("placeholder")).not.toBe(label);
    expect(await page.locator("#password").getAttribute("placeholder")).toBeNull();
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`#28 axe: 0 violations in the main states (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      const found: string[] = [];
      for (const url of ["/login", "/login?method=local", "/login?error=tenant", "/login?error=cancelled&reason=expired"]) {
        await open(page, url);
        await page.addScriptTag({ path: AXE });
        const v = await page.evaluate(async () => {
          // @ts-expect-error injected axe-core
          const r = await window.axe.run(document, { runOnly: ["color-contrast", "label", "target-size", "region", "heading-order", "nested-interactive"], resultTypes: ["violations"] });
          return (r.violations as { id: string; nodes: { target: string[] }[] }[]).map((x) => `${x.id}: ${x.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(" | ")}`);
        });
        for (const x of v) found.push(`${url} ${x}`);
      }
      expect(found).toEqual([]);
    });
  }

  test("#29 reduced motion: door 2 has no animation over 100 ms; no shake after a 401", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await open(page, "/login");
    await page.getByTestId("login-disclosure").click();
    const long = await page.evaluate(() => document.getAnimations().filter((a) => Number(a.effect?.getComputedTiming().duration ?? 0) > 100).length);
    expect(long).toBe(0);
    await page.locator("#identifier").fill("e2e-nobody");
    await page.locator("#password").fill("wrong");
    await page.getByTestId("login-submit").click();
    await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
    const shaking = await page.evaluate(() => document.getAnimations().some((a) => (a as CSSAnimation).animationName === "t-input-shake"));
    expect(shaking).toBe(false);
  });

  test("#30 visual baselines of the rendered states", async ({ page }) => {
    test.skip(process.env.VISUAL_BASELINE !== "1", "set VISUAL_BASELINE=1 to compare screenshots (baselines are renderer-specific; generate them on the CI image)");
    for (const url of ["/login", "/login?method=local", "/login?error=tenant", "/login?reason=expired"]) {
      await open(page, url);
      await expect(page).toHaveScreenshot(`signin_${url.replace(/\W+/g, "_")}.png`, { maxDiffPixelRatio: 0.01, mask: [page.getByTestId("app-version")] });
    }
  });
});

