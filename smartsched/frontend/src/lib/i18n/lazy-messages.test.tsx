/**
 * F-CH-1 (fix-c-2026-10-18): the message dictionaries are not in the root layout chunk. Only the active language
 * is fetched (one chunk per locale, `import()`), the provider waits for it before its first render, and a
 * language switch loads the other one first. Before: index.ts imported en.json and tr.json statically, so every
 * route's first load carried both (~250 kB gz, the 249 kB root layout chunk).
 */
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import path from "node:path";
import { Suspense } from "react";
import { describe, expect, it, vi } from "vitest";

const SRC = path.resolve(import.meta.dirname, "index.ts");

describe("message dictionaries are code-split per language", () => {
  it("index.ts has no static import of a messages file, and one import() per shipped language", () => {
    const text = readFileSync(SRC, "utf8");
    expect(text).not.toMatch(/^import\s+(?!type\b)[^;]*messages\/(tr|en)\.json/m);
    expect(text).toMatch(/import\(\s*"\.\.\/\.\.\/\.\.\/messages\/tr\.json"\s*\)/);
    expect(text).toMatch(/import\(\s*"\.\.\/\.\.\/\.\.\/messages\/en\.json"\s*\)/);
  });

  it("a fresh module knows no texts until a language is loaded, then notifies subscribers", async () => {
    vi.resetModules();
    const i18n = await import("./index");
    expect(i18n.hasMessages("tr")).toBe(false);
    expect(i18n.translate("tr", "crbs.news.title")).toBe("crbs.news.title");
    const seen = vi.fn();
    const off = i18n.subscribeMessages(seen);
    await i18n.loadMessages("tr");
    off();
    expect(i18n.hasMessages("tr")).toBe(true);
    expect(i18n.hasMessages("en")).toBe(false);
    expect(i18n.translate("tr", "crbs.news.title")).toBe("Yenilikler");
    expect(seen).toHaveBeenCalled();
    // the same promise while loading or loaded (one request per language)
    expect(i18n.loadMessages("tr")).toBe(i18n.loadMessages("tr"));
  });

  it("the provider renders once the active language is in, and loads English before switching to it", async () => {
    vi.resetModules();
    const i18n = await import("./index");
    const { I18nProvider, useI18n } = await import("./provider");
    function Probe() {
      const { t, setLocale, locale } = useI18n();
      return (
        <>
          <p data-testid="title">{t("crbs.news.title")}</p>
          <p data-testid="locale">{locale}</p>
          <button type="button" onClick={() => setLocale("en")}>
            en
          </button>
        </>
      );
    }
    await act(async () => {
      render(
        <Suspense fallback={<p>loading</p>}>
          <I18nProvider initialLocale="tr">
            <Probe />
          </I18nProvider>
        </Suspense>,
      );
    });
    expect(await screen.findByText("Yenilikler")).toBeInTheDocument();
    expect(i18n.hasMessages("en")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "en" }));
    expect(await screen.findByText("What's new")).toBeInTheDocument();
    expect(screen.getByTestId("locale")).toHaveTextContent("en");
    expect(i18n.hasMessages("en")).toBe(true);
    await act(async () => undefined);
  });

  it("role names match their shipped Turkish and English names with only one language loaded", async () => {
    vi.resetModules();
    const i18n = await import("./index");
    const roles = await import("./roles");
    await i18n.loadMessages("en");
    expect(i18n.hasMessages("tr")).toBe(false);
    const en = (k: Parameters<typeof i18n.translate>[1]) => i18n.translate("en", k);
    expect(roles.roleLabel(en, { code: "TEACHER", name: "Öğretim elemanı" })).toBe("Teacher");
    expect(roles.roleDescription(en, { code: "VIEWER", description: "Planları ve rezervasyonları yalnızca görüntüler" })).toBe("Read-only access to plans and bookings");
  });

  it("the shipped role texts in roles.ts are the ones in messages/*.json", async () => {
    const roles = await import("./roles");
    for (const lang of ["tr", "en"] as const) {
      const glass = (JSON.parse(readFileSync(path.resolve(import.meta.dirname, `../../../messages/${lang}.json`), "utf8")) as { glass: { role: Record<string, string>; roleDescription: Record<string, string> } }).glass;
      for (const code of roles.BUILTIN_ROLES) {
        expect(roles.SHIPPED_ROLE_TEXTS[lang].name[code]).toBe(glass.role[code]);
        expect(roles.SHIPPED_ROLE_TEXTS[lang].description[code]).toBe(glass.roleDescription[code]);
      }
    }
  });
});
