/**
 * Wave 3b, lane W3-MAIL: the guided SMTP setup and the themed e-mails (/admin/email) on a real stack, with a local
 * SMTP sink on port 2721 started by this spec (plain SMTP: the "Kurum sunucusu" preset, security none, no sign-in,
 * which is what an internal relay looks like).
 *
 *  1. Admin, desktop 1440: status "Yapılandırılmadı" + "Son değişiklik"; preset → Bağlantı (focus on the step heading)
 *     → Gönderen → Alan adı (SPF / DKIM / DMARC rows) → Deneme: the sink receives a multipart message with the themed
 *     HTML and the CID logo; the transcript shows the server's 220 and never a secret; Şablonlar: the rejection
 *     template previews in a sandboxed iframe at 640 and 390 px, a subject override shows in the preview and is saved.
 *  2. Organisation-wide: a second administrator reads the same settings and "Son değişiklik: <first admin>"; a teacher
 *     gets 403 from /mail/settings.
 *  3. Phone 390 × 844 touch (tr-TR, Europe/Istanbul): MOBILE M-01 / M-02 / M-03 on the setup and the templates tab.
 *
 *   E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:19720 PW_PORT=19721 npx playwright test w3-mail
 */
import net from "node:net";
import { expect, request as pwRequest, test, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, login } from "./helpers";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const STAMP = Date.now().toString(36);
const ADMIN2 = { email: `mail.admin2.${STAMP}@smartsched.local`, password: "Mail-2026!pw-admin2", full_name: "İkinci Yönetici" };
const TEACHER = { email: `mail.teacher.${STAMP}@smartsched.local`, password: "Mail-2026!pw-teacher", full_name: "Ayşe Yılmaz" };
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "tr-TR", timezoneId: "Europe/Istanbul" };
const SINK_PORT = Number(process.env.W3_MAIL_SINK_PORT ?? 2721);

test.describe.configure({ mode: "serial", timeout: 240_000 });
test.skip(!REAL, SKIP_REASON);

/** a minimal SMTP sink: EHLO, MAIL, RCPT, DATA, QUIT; keeps every message */
const received: { rcpt: string[]; data: string }[] = [];
let sink: net.Server | null = null;
test.beforeAll(async () => {
  sink = net.createServer((sock) => {
    let buf = "";
    let inData = false;
    let rcpt: string[] = [];
    let data = "";
    sock.write("220 w3-mail-sink ESMTP\r\n");
    sock.on("data", (chunk) => {
      buf += chunk.toString("utf8");
      let i: number;
      while ((i = buf.indexOf("\r\n")) >= 0) {
        const line = buf.slice(0, i);
        buf = buf.slice(i + 2);
        if (inData) {
          if (line === ".") {
            inData = false;
            received.push({ rcpt, data });
            sock.write("250 2.0.0 queued\r\n");
          } else data += (line.startsWith("..") ? line.slice(1) : line) + "\n";
          continue;
        }
        const cmd = line.split(" ")[0]!.toUpperCase();
        if (cmd === "EHLO" || cmd === "HELO") sock.write("250-w3-mail-sink\r\n250 8BITMIME\r\n");
        else if (cmd === "MAIL") {
          rcpt = [];
          data = "";
          sock.write("250 2.1.0 ok\r\n");
        } else if (cmd === "RCPT") {
          rcpt.push(line.replace(/^RCPT TO:\s*<?([^>]+)>?.*$/i, "$1"));
          sock.write("250 2.1.5 ok\r\n");
        } else if (cmd === "DATA") {
          inData = true;
          sock.write("354 go\r\n");
        } else if (cmd === "QUIT") {
          sock.end("221 bye\r\n");
        } else sock.write("250 ok\r\n");
      }
    });
    sock.on("error", () => undefined);
  });
  await new Promise<void>((resolve) => sink!.listen(SINK_PORT, "127.0.0.1", resolve));
  const admin = await asUser(ADMIN_EMAIL, ADMIN_PASSWORD);
  for (const u of [
    { ...ADMIN2, role: "ADMIN" },
    { ...TEACHER, role: "TEACHER" },
  ]) {
    const r = await admin.post(`${API}/users`, { data: u });
    expect(r.status(), await r.text()).toBe(201);
  }
  await admin.dispose();
});
test.afterAll(async () => {
  await new Promise<void>((resolve) => (sink ? sink.close(() => resolve()) : resolve()));
});

async function asUser(email: string, password: string) {
  const ctx = await pwRequest.newContext();
  const r = await ctx.post(`${API}/auth/login`, { data: { email, password } });
  expect(r.ok(), await r.text()).toBeTruthy();
  const t = ((await r.json()) as { access_token: string }).access_token;
  await ctx.dispose();
  return pwRequest.newContext({ extraHTTPHeaders: { Authorization: `Bearer ${t}` } });
}

/** MOBILE.md M-01, M-02 (scrolled in 0.8 × viewport steps, inside `scope` when given), M-03. */
async function mobileChecks(page: Page, scope = "body") {
  return page.evaluate(async (scope) => {
    const root = document.querySelector(scope) ?? document.body;
    const vw = document.documentElement.clientWidth;
    window.scrollTo(10000, window.scrollY);
    const scrolledX = window.scrollX;
    window.scrollTo(0, window.scrollY);
    const off: string[] = [];
    for (const el of root.querySelectorAll("*")) {
      const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
      if (!r.width || !r.height || cs.visibility === "hidden" || cs.position === "fixed") continue;
      if (r.right <= vw + 1 && r.left >= -1) continue;
      let p = el.parentElement, contained = false;
      while (p && p !== document.body) {
        if (getComputedStyle(p).overflowX !== "visible") { contained = true; break; }
        p = p.parentElement;
      }
      if (!contained) off.push(`${el.tagName}${(el as HTMLElement).dataset.testid ? `[${(el as HTMLElement).dataset.testid}]` : ""}`);
    }
    const SEL = 'a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=tab],[role=checkbox],[role=radio],[role=switch],[role=menuitem],[role=option],[tabindex]:not([tabindex="-1"])';
    const hits = (el: Element, x: number, y: number) => { const t = document.elementFromPoint(x, y); return !!t && (t === el || el.contains(t)); };
    const bad = new Set<string>();
    const scrollers = [document.scrollingElement!, ...root.querySelectorAll("*")].filter((e) => e.scrollHeight > e.clientHeight + 4 && /(auto|scroll)/.test(getComputedStyle(e).overflowY) || e === document.scrollingElement);
    const VH = document.documentElement.clientHeight;
    const maxH = Math.max(...scrollers.map((s) => s.scrollHeight));
    for (let y = 0; y <= maxH; y += Math.floor(VH * 0.8)) {
      scrollers.forEach((s) => (s.scrollTop = y));
      await new Promise((r) => setTimeout(r, 60));
      for (const el of root.querySelectorAll(SEL)) {
        const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
        if (!r.width || !r.height || cs.visibility === "hidden" || el.closest('[aria-hidden="true"],[inert]')) continue;
        if ((el as HTMLElement).checkVisibility && !(el as HTMLElement).checkVisibility()) continue;
        if (r.width <= 1 && r.height <= 1 && el !== document.activeElement) continue;
        if (el.tagName === "A" && cs.display === "inline" && /^(P|LI|TD|SPAN|DD)$/.test(el.parentElement?.tagName ?? "")) continue;
        let w = r.width, h = r.height;
        const lab = (el as HTMLInputElement).labels?.[0];
        if (lab) { const l = lab.getBoundingClientRect(); w = Math.max(w, l.width); h = Math.max(h, l.height); }
        if (w >= 44 && h >= 44) continue;
        const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
        if (!(cy > 22 && cy < VH - 22 && cx > 22 && cx < vw - 22)) continue; // measured at another scroll step
        if ([[cx - 22, cy], [cx + 21, cy], [cx, cy - 22], [cx, cy + 21]].every(([x, yy]) => hits(el, x, yy))) continue;
        bad.add(`${((el as HTMLElement).dataset.testid || el.getAttribute("aria-label") || el.textContent || el.tagName).trim().slice(0, 40)} ${Math.round(w)}×${Math.round(h)}`);
      }
    }
    scrollers.forEach((s) => (s.scrollTop = 0));
    const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: (n) => (n.nodeValue!.trim() ? 1 : 2) });
    const small: string[] = [];
    while (tw.nextNode()) {
      const el = tw.currentNode.parentElement!, cs = getComputedStyle(el), r = el.getBoundingClientRect();
      if (!r.width || r.width <= 1 || cs.visibility === "hidden" || el.closest(".sr-only,[data-allow-small-text]")) continue;
      if (parseFloat(cs.fontSize) < 11) small.push(`${el.textContent!.trim().slice(0, 30)} ${cs.fontSize}`);
    }
    const inputs = [...root.querySelectorAll("input:not([type=checkbox]):not([type=radio]):not([type=hidden]),select,textarea")]
      .filter((i) => i.getBoundingClientRect().width > 1 && !i.closest(".sr-only") && (!(i as HTMLElement).checkVisibility || (i as HTMLElement).checkVisibility()) && parseFloat(getComputedStyle(i).fontSize) < 16)
      .map((i) => (i as HTMLElement).dataset.testid || i.id);
    return { zoom: [innerWidth, vw], scrollWidth: document.scrollingElement!.scrollWidth, vw, scrolledX, offenders: off.slice(0, 15), small: small.slice(0, 15), touch: [...bad], inputsUnder16: inputs };
  }, scope);
}


test("1. admin desktop 1440: guided setup to a working test e-mail, then the themed templates", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await page.goto("/admin/email");
  await expect(page.getByTestId("mail-status")).toBeVisible();
  // 1 Sağlayıcı
  await page.getByTestId("mail-step-provider").click();
  await page.getByTestId("mail-preset-custom").click();
  await expect(page.getByTestId("mail-preset-custom")).toHaveAttribute("aria-checked", "true");
  await page.getByTestId("mail-next").click();
  // 2 Bağlantı: the step heading takes the focus (never <body>)
  await expect(page.getByRole("heading", { name: "Bağlantı" })).toBeFocused();
  await page.getByLabel("Sunucu", { exact: true }).fill("127.0.0.1");
  await page.getByLabel("Bağlantı noktası").fill(String(SINK_PORT));
  await page.getByLabel("Güvenlik", { exact: true }).selectOption("none");
  await expect(page.getByText("Bağlantı şifresiz; yalnız kurum ağı içinde kullanın.")).toBeVisible();
  await page.getByLabel("Oturum açma yöntemi").selectOption("none");
  await page.getByTestId("mail-next").click();
  // 3 Gönderen
  await expect(page.getByRole("heading", { name: "Gönderen" })).toBeFocused();
  await page.getByLabel("Gönderen adresi").fill("bildirim@uni.edu.tr");
  await page.getByLabel("Gönderen adı").fill("Örnek Üniversitesi SmartSched");
  await page.getByLabel("Yanıt adresi (önerilir)").fill("planlama@uni.edu.tr");
  await page.getByTestId("mail-next").click();
  // 4 Alan adı: three rows with a status word (the stack may be offline: "Okunamadı" is a valid answer)
  await expect(page.getByRole("heading", { name: "Alan adı" })).toBeFocused();
  await page.getByTestId("mail-dns-run").click();
  await expect(page.getByTestId("mail-dns").locator("li")).toHaveCount(3, { timeout: 30_000 });
  await expect(page.getByTestId("mail-dns")).toContainText(/SPF · (Doğru|Uyarı|Eksik|Okunamadı)/);
  await page.getByTestId("mail-next").click();
  // 5 Deneme
  await page.getByLabel("Deneme gönderilecek adres").fill("hoca@uni.edu.tr");
  await page.getByTestId("mail-test-send").click();
  await expect(page.getByTestId("mail-test-result")).toContainText("Gönderildi: sunucu iletiyi kabul etti", { timeout: 30_000 });
  await page.getByText("SMTP görüşmesi (gizli bilgiler gösterilmez)").click();
  await expect(page.getByTestId("mail-transcript")).toContainText("S: 220 w3-mail-sink");
  await expect(page.getByTestId("mail-transcript")).not.toContainText("deneme iletisidir");
  await expect.poll(() => received.length).toBeGreaterThan(0);
  const msg = received.at(-1)!;
  expect(msg.rcpt).toEqual(["hoca@uni.edu.tr"]);
  expect(msg.data).toMatch(/multipart\/alternative/);
  expect(msg.data).toMatch(/Content-Type: text\/html/);
  expect(msg.data).toMatch(/Content-ID: <logo@smartsched>/);
  expect(msg.data).toMatch(/Reply-To: planlama@uni\.edu\.tr/);
  await expect(page.getByTestId("mail-status")).toContainText("Bağlı");
  // Şablonlar
  await page.getByRole("tab", { name: "Şablonlar" }).click();
  await page.getByTestId("mail-tpl-approval_rejected").click();
  const frame = page.getByTestId("mail-tpl-frame");
  await expect(frame).toHaveAttribute("sandbox", "");
  await expect.poll(async () => (await frame.boundingBox())?.width).toBeGreaterThan(600);
  await expect(page.frameLocator('[data-testid="mail-tpl-frame"]').locator("h1")).toHaveText("Oda talebiniz reddedildi");
  await page.getByRole("radio", { name: "Telefon" }).click();
  await expect.poll(async () => Math.round((await frame.boundingBox())?.width ?? 0)).toBe(390);
  await page.getByTestId("mail-tpl-subject").fill("Talebiniz uygun bulunmadı: {what}");
  await expect(page.getByTestId("mail-tpl-preview-subject")).toContainText("Talebiniz uygun bulunmadı: A 201");
  await page.getByTestId("mail-tpl-save").click();
  await expect(page.getByTestId("mail-tpl-approval_rejected")).toContainText("Değiştirildi");
  await page.getByRole("tab", { name: "Giden kutusu" }).click();
  await expect(page.getByText("SmartSched deneme iletisi").first()).toBeVisible();
});

test("2. organisation-wide: a second admin sees the same settings and the first admin's change; a teacher gets 403", async () => {
  const other = await asUser(ADMIN2.email, ADMIN2.password);
  const r = await other.get(`${API}/mail/settings`);
  expect(r.status()).toBe(200);
  const body = (await r.json()) as { host: string; last_change: { by: string | null } | null; status: string };
  expect(body.host).toBe("127.0.0.1");
  expect(body.status).toBe("connected");
  expect(body.last_change?.by).toBeTruthy();
  await other.dispose();
  const teacher = await asUser(TEACHER.email, TEACHER.password);
  expect((await teacher.get(`${API}/mail/settings`)).status()).toBe(403);
  expect((await teacher.post(`${API}/mail/test`, { data: { to: "x@uni.edu.tr" } })).status()).toBe(403);
  await teacher.dispose();
  // a subject override from test 1 is a translations row (set "email") and reaches the next rejection mail
  const admin = await asUser(ADMIN_EMAIL, ADMIN_PASSWORD);
  const tpl = ((await (await admin.get(`${API}/mail/templates`)).json()) as { kind: string; overrides: { tr: { subject: string | null } } }[]).find((x) => x.kind === "approval_rejected")!;
  expect(tpl.overrides.tr.subject).toBe("Talebiniz uygun bulunmadı: {what}");
  await admin.put(`${API}/mail/templates/approval_rejected`, { data: { locale: "tr", subject: "" } });
  await admin.dispose();
});

test("3. phone 390 touch: M-01/02/03 on the setup and the templates", async ({ browser }) => {
  const context = await browser.newContext(PHONE);
  const page = await context.newPage();
  await login(page);
  await page.goto("/admin/email");
  await expect(page.getByTestId("mail-status")).toBeVisible();
  await expect(page.getByText(/Adım \d \/ 6/)).toBeVisible();
  for (const tab of ["Kurulum", "Şablonlar"]) {
    await page.getByRole("tab", { name: tab }).click();
    if (tab === "Şablonlar") {
      await page.getByTestId("mail-tpl-approval_rejected").tap();
      await expect(page.getByTestId("mail-tpl-frame")).toBeVisible();
    }
    const g = await mobileChecks(page, "main");
    expect({ tab, M01: g.offenders, sw: g.scrollWidth <= g.vw, x: g.scrolledX }).toEqual({ tab, M01: [], sw: true, x: 0 });
    expect(g.touch, `M-02 ${tab}`).toEqual([]);
    expect(g.small, `M-03 text ${tab}`).toEqual([]);
    expect(g.inputsUnder16, `M-03 inputs ${tab}`).toEqual([]);
  }
  await context.close();
});
