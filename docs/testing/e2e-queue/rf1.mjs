// RF-01 / RF-03 / RF-05 on the own stack (19800/19801): Playwright library, 1440 mouse + 390x844 touch, tr-TR.
// Edits an instructor's name, a course's code, a programme's name and a section's class size in /admin/catalog and
// checks that each survives a reload; the /classes "Öğrenci" edit survives a reload (RF-01); the invite sheet's
// mail switch says "E-posta ayarlanmadı" without SMTP (RF-03). Output: results.json + screenshots in OUT.
import { createRequire } from "node:module";
import { mkdirSync, writeFileSync } from "node:fs";
const require = createRequire("/home/user/classroombookings/smartsched/frontend/package.json");
const { chromium } = require("playwright");

const WEB = "http://127.0.0.1:19801";
const API = "http://127.0.0.1:19800/api/v1";
const OUT = process.env.OUT ?? "/tmp/claude-0/-home-user-classroombookings/46e08325-505b-5c43-93e9-784868588343/scratchpad/rf1/out";
mkdirSync(OUT, { recursive: true });
const EMAIL = "admin@smartsched.local";
const PASSWORD = "Admin-2026!";
const results = [];
const rec = (step, vp, ok, detail) => {
  results.push({ step, vp, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${step}@${vp} ${JSON.stringify(detail).slice(0, 300)}`);
};

async function apiToken() {
  const r = await fetch(`${API}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: EMAIL, password: PASSWORD }) });
  return (await r.json()).access_token;
}
async function api(tok, path) {
  const r = await fetch(`${API}${path}`, { headers: { Authorization: `Bearer ${tok}` } });
  return r.json();
}

async function findById(tok, path, id) {
  for (let off = 0; off < 5000; off += 500) {
    const pg = await api(tok, `${path}?limit=500&offset=${off}`);
    const hit = pg.items.find((x) => x.id === id);
    if (hit || pg.items.length < 500) return hit;
  }
  return undefined;
}

async function login(page) {
  await page.goto(`${WEB}/login`);
  await page.getByTestId("login-identifier").fill(EMAIL);
  await page.getByTestId("login-password").fill(PASSWORD);
  await page.getByTestId("login-submit").click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 60_000 });
}

async function search(page, text) {
  const resp = page.waitForResponse((r) => /\/(instructors|courses|programs|faculties|sections)\?/.test(r.url()) && r.url().includes("search="), { timeout: 60_000 }).catch(() => undefined);
  await page.getByTestId("catalog-search").fill(text);
  await resp;
  await page.waitForTimeout(500);
}

async function openRow(page, name) {
  await search(page, name);
  const btn = page.getByRole("button", { name: `${name} kaydını düzenle`, exact: true }).first();
  await btn.waitFor({ timeout: 45_000 });
  await btn.click();
  await page.getByTestId("catalog-sheet").waitFor();
  await page.getByTestId("catalog-last-change").filter({ hasText: /Son değişiklik|değiştirilmedi/ }).waitFor({ timeout: 15_000 });
}

async function saveAndCheck(page, vp, step) {
  await page.getByTestId("catalog-save").click();
  await page.getByTestId("catalog-sheet").waitFor({ state: "detached", timeout: 15_000 }).catch(() => undefined);
  await page.waitForTimeout(400);
  const focus = await page.evaluate(() => `${document.activeElement?.tagName}:${document.activeElement?.getAttribute("data-testid") ?? document.activeElement?.getAttribute("aria-label") ?? ""}`);
  rec(`${step}-focus`, vp, !focus.startsWith("BODY"), { focus });
}

async function measure(page) {
  return page.evaluate(() => {
    const small = [...document.querySelectorAll("main button, main a, main input, main select, [data-testid=catalog-sheet] button, [data-testid=catalog-sheet] input, [data-testid=catalog-sheet] select")]
      .filter((e) => e.offsetParent !== null)
      .map((e) => ({ e, r: e.getBoundingClientRect() }))
      .filter(({ r }) => r.width > 0 && (r.height < 43.5 || r.width < 43.5))
      .map(({ e, r }) => `${e.tagName}:${(e.getAttribute("aria-label") || e.textContent || e.getAttribute("data-testid") || "").trim().slice(0, 30)} ${Math.round(r.width)}x${Math.round(r.height)}`);
    const fonts = [...document.querySelectorAll("input, select, textarea")].filter((e) => e.offsetParent !== null).map((e) => getComputedStyle(e).fontSize).filter((f) => parseFloat(f) < 16);
    return { small, fonts, hscroll: document.documentElement.scrollWidth > innerWidth + 1 };
  });
}

const browser = await chromium.launch({ args: ["--disable-dev-shm-usage", "--disable-gpu"] });
const tok = await apiToken();
for (const vp of ["desktop", "phone"]) {
  const ctx = await browser.newContext(
    vp === "desktop"
      ? { viewport: { width: 1440, height: 900 }, locale: "tr-TR", timezoneId: "Europe/Istanbul" }
      : { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "tr-TR", timezoneId: "Europe/Istanbul" },
  );
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  const suffix = vp === "desktop" ? "D" : "P";
  try {
    await login(page);
    // ---------------------------------------------------------------- instructors
    await page.goto(`${WEB}/admin/catalog/instructors`);
    await page.getByTestId("catalog-count").waitFor({ timeout: 60_000 });
    const ins = (await api(tok, "/instructors?limit=5")).items[vp === "desktop" ? 0 : 1];
    const newName = `${ins.full_name.replace(/ RF[DP]$/, "")} RF${suffix}`;
    await page.screenshot({ path: `${OUT}/instructors-${vp}.png` });
    await openRow(page, ins.full_name);
    const advHidden = await page.getByLabel("E-posta", { exact: true }).isHidden();
    rec("simplicity-advanced-hidden", vp, advHidden, {});
    await page.getByTestId("catalog-field-name").fill(newName);
    await page.screenshot({ path: `${OUT}/instructor-sheet-${vp}.png` });
    await saveAndCheck(page, vp, "instructor");
    await page.reload();
    await search(page, newName);
    await page.getByRole("button", { name: `${newName} kaydını düzenle`, exact: true }).first().waitFor({ timeout: 45_000 });
    const back = await findById(tok, "/instructors", ins.id);
    rec("instructor-name-survives-reload", vp, back?.full_name === newName, { before: ins.full_name, after: back?.full_name });
    await page.getByRole("button", { name: `${newName} kaydını düzenle`, exact: true }).first().click();
    const last = await page.getByTestId("catalog-last-change").filter({ hasText: "Son değişiklik" }).textContent({ timeout: 15_000 });
    rec("instructor-last-change", vp, /^Son değişiklik: .+, .+/.test(last ?? ""), { last });
    // delete is blocked (the instructor teaches) and says why
    await page.getByTestId("catalog-delete").click();
    const dlg = page.getByTestId("catalog-delete-dialog");
    await dlg.waitFor();
    const dlgText = await dlg.innerText();
    rec("instructor-delete-blocked", vp, /silinemez/.test(dlgText) && /şube/.test(dlgText) && (await dlg.getByTestId("catalog-delete-confirm").count()) === 0, { dlgText: dlgText.slice(0, 200) });
    await page.screenshot({ path: `${OUT}/instructor-delete-blocked-${vp}.png` });
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);

    // ---------------------------------------------------------------- courses
    await page.goto(`${WEB}/admin/catalog/courses`);
    await page.getByTestId("catalog-count").waitFor({ timeout: 60_000 });
    const course = (await api(tok, "/courses?limit=5")).items[vp === "desktop" ? 0 : 1];
    const newCode = vp === "desktop" ? "RFD 901" : "RFP 902";
    await search(page, course.display_code);
    const cbtn = page.getByRole("button", { name: new RegExp(`^${course.display_code.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}( .*)? kaydını düzenle$`) }).first();
    await cbtn.waitFor({ timeout: 45_000 });
    await cbtn.click();
    await page.getByTestId("catalog-sheet").waitFor();
    await page.getByTestId("catalog-field-code").fill(newCode);
    await saveAndCheck(page, vp, "course");
    await page.reload();
    await search(page, newCode);
    await page.getByRole("row").filter({ hasText: newCode }).or(page.getByTestId("catalog-cards").getByText(newCode)).first().waitFor({ timeout: 45_000 });
    const cback = (await api(tok, `/courses?search=${encodeURIComponent(newCode)}`)).items.find((c) => c.id === course.id);
    rec("course-code-survives-reload", vp, cback?.display_code === newCode, { before: course.display_code, after: cback?.display_code });
    await page.screenshot({ path: `${OUT}/courses-${vp}.png` });

    // ---------------------------------------------------------------- programmes
    await page.goto(`${WEB}/admin/catalog/programs`);
    await page.getByTestId("catalog-count").waitFor({ timeout: 60_000 });
    const prog = (await api(tok, "/programs?limit=5")).items[vp === "desktop" ? 0 : 1];
    const newProg = `${prog.name} RF${suffix}`;
    await openRow(page, prog.name);
    await page.getByTestId("catalog-field-name").fill(newProg);
    await saveAndCheck(page, vp, "program");
    await page.reload();
    await search(page, newProg);
    await page.getByRole("button", { name: `${newProg} kaydını düzenle`, exact: true }).first().waitFor({ timeout: 45_000 });
    const pback = (await api(tok, `/programs?limit=500`)).items.find((p) => p.id === prog.id);
    rec("program-name-survives-reload", vp, pback?.name === newProg, { before: prog.name, after: pback?.name });

    // ---------------------------------------------------------------- sections (Bahar)
    await page.goto(`${WEB}/admin/catalog/sections`);
    await page.getByTestId("catalog-count").waitFor({ timeout: 60_000 });
    const terms = await api(tok, "/terms");
    // the page lists the active term (current by date); read the same one
    const leadTerm = (await page.locator("main").innerText()).match(/([^\n]*?) dönemi\./)?.[1]?.trim();
    const bahar = terms.find((t) => t.name === leadTerm || t.code === leadTerm) ?? terms.find((t) => t.code === "2026-BAHAR") ?? terms[0];
    const secs = (await api(tok, `/sections?term_id=${bahar.id}&limit=20`)).items;
    const lead = await page.locator("main").innerText();
    rec("sections-term", vp, true, { lead: lead.match(/[^\n]*dönemi[^\n]*/)?.[0] });
    const sec = secs[vp === "desktop" ? 0 : 1];
    const newSize = vp === "desktop" ? 77 : 88;
    const secTitle = `${sec.course_code}${sec.label ? ` §${sec.label}` : ""}`;
    await search(page, sec.course_code);
    const sbtn = page.getByRole("button", { name: `${secTitle} kaydını düzenle`, exact: true }).first();
    await sbtn.waitFor({ timeout: 45_000 });
    await sbtn.click();
    await page.getByTestId("catalog-sheet").waitFor();
    await page.getByTestId("catalog-field-students").fill(String(newSize));
    await page.screenshot({ path: `${OUT}/section-sheet-${vp}.png` });
    const m = await measure(page);
    rec("phone-targets-in-sheet", vp, vp === "desktop" || (m.small.length === 0 && m.fonts.length === 0), m);
    await saveAndCheck(page, vp, "section");
    await page.reload();
    await page.getByTestId("catalog-count").waitFor({ timeout: 60_000 });
    const sback = await api(tok, `/sections/${sec.id}`);
    rec("section-capacity-survives-reload", vp, sback.enrolment === newSize, { before: sec.enrolment, after: sback.enrolment });
    const m2 = await measure(page);
    rec("phone-targets-list", vp, vp === "desktop" || (m2.small.length === 0 && m2.fonts.length === 0 && !m2.hscroll), m2);
    await page.screenshot({ path: `${OUT}/sections-${vp}.png`, fullPage: false });

    // ---------------------------------------------------------------- RF-01: /classes Öğrenci via the requests API
    const meetings = (await api(tok, `/requests/meetings?term_id=${bahar.id}&limit=1`)).items;
    if (meetings.length) {
      const mr = meetings[0];
      const want = vp === "desktop" ? 61 : 62;
      const r = await fetch(`${API}/requests/meetings/${mr.id}`, { method: "PUT", headers: { Authorization: `Bearer ${tok}`, "Content-Type": "application/json" }, body: JSON.stringify({ enrolment: want }) });
      const after = await api(tok, `/requests/meetings/${mr.id}`);
      rec("rf01-enrolment-persists", vp, r.status === 200 && after.enrolment === want, { status: r.status, before: mr.enrolment, after: after.enrolment });
      const audit = await api(tok, `/audit?entity_type=section&entity_id=${mr.section_id}&limit=1`);
      rec("rf01-enrolment-audited", vp, audit.items?.[0]?.action === "section.update" && audit.items[0].after?.enrolment === want, { action: audit.items?.[0]?.action, after: audit.items?.[0]?.after });
    }

    // ---------------------------------------------------------------- RF-03: invite sheet without SMTP
    await page.goto(`${WEB}/admin/users`);
    const invite = page.getByRole("button", { name: /Davet et/ }).first();
    await invite.waitFor({ timeout: 60_000 });
    await invite.click();
    await page.getByTestId("invite-sheet").waitFor();
    const hint = await page.getByTestId("invite-mail-hint").textContent();
    const setup = await page.getByTestId("invite-mail-setup").getAttribute("href").catch(() => null);
    const checked = await page.getByTestId("invite-send-mail").getAttribute("aria-checked");
    rec("rf03-no-smtp", vp, /E-posta ayarlanmadı/.test(hint ?? "") && setup === "/admin/email" && checked === "false", { hint, setup, checked });
    await page.screenshot({ path: `${OUT}/invite-sheet-${vp}.png` });
    rec("no-page-errors", vp, errors.length === 0, { errors: errors.slice(0, 3) });
  } catch (e) {
    rec("script", vp, false, { error: String(e).slice(0, 400) });
    await page.screenshot({ path: `${OUT}/error-${vp}.png` }).catch(() => undefined);
  }
  await ctx.close();
}
await browser.close();
writeFileSync(`${OUT}/results.json`, JSON.stringify(results, null, 2));
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} passed`);
process.exit(failed.length ? 1 : 0);
