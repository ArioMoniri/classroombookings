import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { OrgI18n } from "@/lib/api/crbs";
import { LocaleToggle } from "@/components/shell/locale-toggle";
import { dateFormatter, formatPattern } from "@/components/bookings/date-format";
import en from "../../../messages/en.json";
import de from "../../../messages/de.json";
import fr from "../../../messages/fr.json";
import localeData from "./locale-data.json";
import { LOCALES, LOCALE_INFO, coverage, formatNumber, intlLocale, isLocale, normalizeLocale, pairLang, pluralCategory, translate, type Locale } from "./index";
import { I18nProvider, orgI18nKey, useI18n } from "./provider";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));

const CRBS = ["cs", "cy", "da", "de", "es", "fi", "fr", "it", "nl", "pt", "pt-br", "sv"] as const;

function flatten(tree: unknown, prefix = ""): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(tree as Record<string, unknown>)) {
    if (typeof v === "string") out[`${prefix}${k}`] = v;
    else Object.assign(out, flatten(v, `${prefix}${k}.`));
  }
  return out;
}

describe("the 14 languages (P18-LANG)", () => {
  it("ships Turkish, English and the 12 other CRBS languages under one code each", () => {
    expect(LOCALES).toEqual(["tr", "en", ...CRBS]);
    expect(Object.keys(localeData.languages).sort()).toEqual([...CRBS].sort());
    expect(normalizeLocale("pt_BR")).toBe("pt-br");
    expect(normalizeLocale(" DE ")).toBe("de");
    expect(normalizeLocale("xx")).toBeNull();
    expect(isLocale("pt-BR")).toBe(false); // codes are lower case, as the API stores them
    expect(intlLocale("pt-br")).toBe("pt-BR");
    expect(intlLocale("pt")).toBe("pt-PT");
  });

  it("names each language in itself, as ICU does", () => {
    for (const l of LOCALES) {
      const icu = new Intl.DisplayNames([intlLocale(l)], { type: "language" }).of(l === "pt-br" ? "pt-BR" : l)!;
      expect(LOCALE_INFO[l].name.toLocaleLowerCase(intlLocale(l))).toBe(icu.toLocaleLowerCase(intlLocale(l)));
    }
  });

  it("falls back to English per key: CRBS strings translated, SmartSched-only strings in English", () => {
    expect(translate("de", "days.1")).toBe("Montag");
    expect(translate("fr", "days.5")).toBe("Vendredi");
    expect(translate("de", "common.week")).toBe("Woche");
    expect(translate("de", "nav.language")).toBe(en.nav.language);
    expect(translate("cy", "crbs.news.title")).toBe(en.crbs.news.title);
    // an organisation override fills a missing German text
    expect(translate("de", "crbs.news.title", undefined, { "crbs.news.title": "Neuigkeiten" })).toBe("Neuigkeiten");
    // placeholders work on the fallback too
    expect(translate("sv", "nav.languagePartial", { pct: "1 %" })).toBe("Partial translation · 1 %");
  });

  it("generated catalogues are sparse subsets of en.json with only CRBS text", () => {
    const keys = new Set(Object.keys(flatten(en)));
    for (const cat of [de, fr]) {
      const flat = flatten(cat);
      expect(Object.keys(flat).length).toBeGreaterThan(0);
      for (const [k, v] of Object.entries(flat)) {
        expect(keys.has(k), k).toBe(true);
        expect(v.trim()).not.toBe("");
      }
    }
  });

  it("reports the share each language translates", () => {
    expect(coverage("en")).toMatchObject({ partial: false, ratio: 1 });
    expect(coverage("tr")).toMatchObject({ partial: false, ratio: 1 });
    for (const l of CRBS) {
      const c = coverage(l);
      expect(c.partial).toBe(true);
      expect(c.ratio).toBeGreaterThan(0);
      expect(c.ratio).toBeLessThan(1);
    }
    expect(coverage("de").translated).toBe(Object.keys(flatten(de)).length);
  });

  it("uses the CLDR plural rules of each language", () => {
    const rooms = { "crbs.news.title": "{n, plural, =0 {kein Raum} one {# Raum} other {# Räume}}" };
    expect(translate("de", "crbs.news.title", { n: 0 }, rooms)).toBe("kein Raum");
    expect(translate("de", "crbs.news.title", { n: 1 }, rooms)).toBe("1 Raum");
    expect(translate("de", "crbs.news.title", { n: 1200 }, rooms)).toBe("1.200 Räume");
    expect(pluralCategory("cs", 3)).toBe("few");
    expect(pluralCategory("cy", 2)).toBe("two");
    expect(pluralCategory("fr", 0)).toBe("one");
    expect(pluralCategory("en", 0)).toBe("other");
    // a message without plural syntax is untouched
    expect(translate("en", "glass.shell.solving", { pct: 40 })).toContain("40");
  });

  it("formats numbers in each language", () => {
    expect(formatNumber("de", 1234.5)).toBe("1.234,5");
    expect(formatNumber("fr", 1234.5).replace(/\s/g, " ")).toBe("1 234,5");
    expect(formatNumber("pt-br", 0.5, { style: "percent" })).toBe("50%");
  });

  it("shows Turkish/English pair texts in English for the CRBS languages", () => {
    expect(pairLang("tr")).toBe("tr");
    expect(pairLang("de")).toBe("en");
  });
});

describe("dates in the CRBS languages", () => {
  it("uses CRBS day and month names with each locale's default patterns", () => {
    expect(dateFormatter(null, "de").long("2026-02-16")).toBe("Montag, 16. Februar 2026");
    expect(dateFormatter(null, "fr").long("2026-02-16")).toBe("Lundi 16 Février 2026");
    expect(dateFormatter(null, "es").long("2026-02-16")).toBe("Lunes, 16 de Febrero de 2026");
    expect(dateFormatter(null, "da").long("2026-02-16")).toBe("Mandag den 16. Februar 2026");
    expect(dateFormatter(null, "sv").short("2026-02-16")).toBe("2026-02-16");
    expect(dateFormatter(null, "de").short("2026-02-16")).toBe("16.02.2026");
    expect(dateFormatter(null, "fi").time("09:05")).toBe("9.05");
    // the organisation's pattern wins, with the language's names
    expect(dateFormatter({ pattern_long: "EEEE d MMMM yyyy" }, "it").long("2026-02-16")).toBe("Lunedì 16 Febbraio 2026");
    // CRBS's Italian file calls Saturday "Dom"; the import corrects it from its own "Sabato"
    expect(formatPattern("2026-02-21", "EEE", "it")).toBe("Sab");
    expect(formatPattern("2026-02-16", "h:mm a", "de")).toBe("12:00 AM");
  });
});

function bundle(language: Locale, languages: Locale[]): OrgI18n {
  return {
    language,
    default_language: "en",
    languages,
    language_names: Object.fromEntries(languages.map((l) => [l, LOCALE_INFO[l].name])),
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

function renderPicker(languages: Locale[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(orgI18nKey("en"), bundle("en", languages));
  for (const l of languages) qc.setQueryData(orgI18nKey(l), bundle(l, languages));
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale="en">
        <LocaleToggle />
        <Probe />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("language picker", () => {
  it("keeps the two-language toggle when the organisation enables only Turkish and English", () => {
    renderPicker(["tr", "en"]);
    expect(screen.getByRole("group", { name: "Language" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "en" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByTestId("locale-picker")).toBeNull();
  });

  it("lists the enabled languages by their own names with a partial-translation note, and switches", async () => {
    renderPicker(["tr", "en", "de", "fr"]);
    const trigger = await screen.findByTestId("locale-picker");
    await userEvent.click(trigger);
    const german = await screen.findByRole("menuitemradio", { name: /Deutsch/ });
    expect(german).toHaveAttribute("lang", "de");
    expect(screen.getByTestId("locale-partial-de")).toHaveTextContent(/^Partial translation · 1%$/);
    expect(screen.queryByTestId("locale-partial-tr")).toBeNull();
    expect(screen.queryByTestId("locale-option-sv")).toBeNull(); // not enabled by the organisation
    await userEvent.click(german);
    expect(screen.getByTestId("probe")).toHaveAttribute("data-locale", "de");
    expect(screen.getByTestId("probe")).toHaveTextContent("Montag");
    expect(document.cookie).toContain("NEXT_LOCALE=de");
    expect(screen.getByTestId("locale-picker")).toHaveAccessibleName(/Language: Deutsch \(Partial translation · 1\s?%\)/);
  });
});
