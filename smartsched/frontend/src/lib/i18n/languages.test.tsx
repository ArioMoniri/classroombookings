import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { OrgI18n } from "@/lib/api/crbs";
import { LocaleToggle } from "@/components/shell/locale-toggle";
import { dateFormatter } from "@/components/bookings/date-format";
import { LOCALES, LOCALE_INFO, displayLocale, formatNumber, intlLocale, isLocale, normalizeLocale, pairLang, pluralCategory, translate, type Locale } from "./index";
import { I18nProvider, orgI18nKey, useI18n } from "./provider";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));

describe("Turkish and English only (P18-LANG, owner decision 2026-10-15)", () => {
  it("offers exactly tr and en", () => {
    expect(LOCALES).toEqual(["tr", "en"]);
    expect(normalizeLocale(" EN ")).toBe("en");
    expect(normalizeLocale("de")).toBeNull(); // a CRBS language, no longer offered
    expect(isLocale("pt-br")).toBe(false);
    expect(LOCALE_INFO.tr.name).toBe("Türkçe");
    expect(LOCALE_INFO.en.name).toBe("English");
  });

  it("shows a stored legacy code (a CRBS import) in English and nothing stored as the default", () => {
    expect(displayLocale("de")).toBe("en");
    expect(displayLocale("pt-br")).toBe("en");
    expect(displayLocale("TR")).toBe("tr");
    expect(displayLocale("en")).toBe("en");
    expect(displayLocale("")).toBeNull();
    expect(displayLocale(null)).toBeNull();
  });

  it("names each language in itself, as ICU does", () => {
    for (const l of LOCALES) {
      const icu = new Intl.DisplayNames([intlLocale(l)], { type: "language" }).of(l)!;
      expect(LOCALE_INFO[l].name.toLocaleLowerCase(intlLocale(l))).toBe(icu.toLocaleLowerCase(intlLocale(l)));
    }
  });

  it("uses the CLDR plural rules and number formats of each language", () => {
    const rooms = { "crbs.news.title": "{n, plural, =0 {derslik yok} other {# derslik}}" };
    expect(translate("tr", "crbs.news.title", { n: 0 }, rooms)).toBe("derslik yok");
    expect(translate("tr", "crbs.news.title", { n: 1200 }, rooms)).toBe("1.200 derslik");
    expect(pluralCategory("en", 1)).toBe("one");
    expect(pluralCategory("en", 0)).toBe("other");
    expect(formatNumber("tr", 1234.5)).toBe("1.234,5");
    expect(formatNumber("en", 1234.5)).toBe("1,234.5");
  });

  it("shows Turkish/English pair texts in the active language", () => {
    expect(pairLang("tr")).toBe("tr");
    expect(pairLang("en")).toBe("en");
  });

  it("formats dates with SmartSched's own Turkish and English names", () => {
    expect(dateFormatter(null, "tr").long("2026-02-16")).toBe("16 Şubat 2026 Pazartesi");
    expect(dateFormatter(null, "en").long("2026-02-16")).toBe("Monday, 16 February 2026");
    expect(dateFormatter(null, "tr").short("2026-02-16")).toBe("16.02.2026");
  });
});

function bundle(language: Locale, languages: string[]): OrgI18n {
  return {
    language,
    default_language: "en",
    languages,
    language_names: {},
    messages: {},
    date_patterns: { pattern_long: null, pattern_weekday: null, pattern_time: null },
    date_defaults: { long: "EEEE, d MMMM yyyy", weekday: "d MMM yyyy", time: "HH:mm" },
  };
}

function Probe() {
  const { locale, t } = useI18n();
  return (
    <p data-testid="probe" data-locale={locale}>
      {t("days.1")}
    </p>
  );
}

function renderPicker(languages: string[], initial: Locale = "en") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  for (const l of LOCALES) qc.setQueryData(orgI18nKey(l), bundle(l, languages));
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale={initial}>
        <LocaleToggle />
        <Probe />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("language picker", () => {
  it("shows two options, Turkish and English, and switches", async () => {
    renderPicker(["tr", "en"]);
    const group = screen.getByRole("group", { name: "Language" });
    const options = within(group).getAllByRole("button");
    expect(options).toHaveLength(2);
    expect(options.map((o) => o.textContent)).toEqual(["tr", "en"]);
    // the buttons show the code but are named after the language (aria-label, T-R2-05 / R2-S-19)
    expect(screen.getByRole("button", { name: "English" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: "Türkçe" }));
    expect(screen.getByTestId("probe")).toHaveAttribute("data-locale", "tr");
    expect(screen.getByTestId("probe")).toHaveTextContent("Pazartesi");
    expect(document.cookie).toContain("NEXT_LOCALE=tr");
  });

  it("still shows only two options when the organisation's stored list has CRBS languages (de, fr)", () => {
    renderPicker(["tr", "de", "fr"]);
    const options = within(screen.getByRole("group", { name: "Language" })).getAllByRole("button");
    expect(options.map((o) => o.textContent)).toEqual(["tr", "en"]); // de / fr read as English
    expect(screen.queryByTestId("locale-option-de")).toBeNull();
  });
});
