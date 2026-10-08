import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { crbsKeys, type OrgI18n } from "@/lib/api/crbs";
import { overridesFromBundle, translate } from "./index";
import { I18nProvider, orgI18nKey, useI18n } from "./provider";

/** The shape `GET /org/i18n` answers (backend `bookings_i18n.bundle`: its own sets + the admin rows). */
function bundle(language: "tr" | "en", messages: OrgI18n["messages"]): OrgI18n {
  return {
    language,
    default_language: "tr",
    languages: ["tr", "en"],
    language_names: { tr: "Türkçe", en: "English" },
    messages,
    date_patterns: { pattern_long: null, pattern_weekday: null, pattern_time: null },
    date_defaults: { long: "d MMMM yyyy EEEE", weekday: "d MMM yyyy", time: "HH:mm" },
  };
}

describe("overridesFromBundle", () => {
  it("maps set + key to the full message key and keeps only keys the frontend ships", () => {
    const o = overridesFromBundle({
      crbs: { "news.title": "Sürüm notları", "no.such.key": "x" },
      glass: { "shell.breadcrumb": "Konum" },
      email: { booking_created_subject: "Rezervasyon oluşturuldu" },
    });
    expect(o).toEqual({ "crbs.news.title": "Sürüm notları", "glass.shell.breadcrumb": "Konum" });
  });

  it("ignores empty texts, blank sets and missing input", () => {
    expect(overridesFromBundle({ crbs: { "news.title": "  " }, " ": { "news.title": "x" } })).toEqual({});
    expect(overridesFromBundle(undefined)).toEqual({});
  });
});

describe("translate with overrides", () => {
  it("prefers the override, fills its placeholders, and falls back to the shipped text", () => {
    const o = { "glass.shell.solving": "Hesaplanıyor: %{pct}" };
    expect(translate("tr", "glass.shell.solving", { pct: 40 }, o)).toBe("Hesaplanıyor: %40");
    expect(translate("tr", "glass.shell.solving", { pct: 40 })).toBe("Çözülüyor · %40");
    expect(translate("tr", "crbs.news.title", undefined, o)).toBe("Yenilikler");
  });
});

function Probe() {
  const { t, setLocale } = useI18n();
  return (
    <>
      <p data-testid="title">{t("crbs.news.title")}</p>
      <p data-testid="nav">{t("crbs.nav.admin")}</p>
      <button type="button" onClick={() => setLocale("en")}>
        en
      </button>
    </>
  );
}

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

describe("I18nProvider org overrides", () => {
  it("shares the cache entry of useOrgI18n", () => {
    expect(orgI18nKey("tr")).toEqual(crbsKeys.i18n("tr"));
    expect(orgI18nKey("en")).toEqual(crbsKeys.i18n("en"));
  });

  it("overlays the overrides of the active language and swaps them per language", async () => {
    const qc = client();
    qc.setQueryData(crbsKeys.i18n("tr"), bundle("tr", { crbs: { "news.title": "Sürüm notları" } }));
    qc.setQueryData(crbsKeys.i18n("en"), bundle("en", { crbs: { "nav.admin": "Administration" } }));
    render(
      <QueryClientProvider client={qc}>
        <I18nProvider initialLocale="tr">
          <Probe />
        </I18nProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Sürüm notları")).toBeInTheDocument();
    expect(screen.getByTestId("nav")).toHaveTextContent("Kurulum");

    await userEvent.click(screen.getByRole("button", { name: "en" }));
    expect(await screen.findByText("Administration")).toBeInTheDocument();
    // the Turkish override does not leak into English
    expect(screen.getByTestId("title")).toHaveTextContent("What's new");
  });

  it("applies a changed override at runtime, without a reload", async () => {
    const qc = client();
    qc.setQueryData(crbsKeys.i18n("tr"), bundle("tr", { crbs: { "news.title": "Sürüm notları" } }));
    render(
      <QueryClientProvider client={qc}>
        <I18nProvider initialLocale="tr">
          <Probe />
        </I18nProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Sürüm notları")).toBeInTheDocument();
    act(() => {
      qc.setQueryData(crbsKeys.i18n("tr"), bundle("tr", { crbs: { "news.title": "Neler değişti" } }));
    });
    expect(await screen.findByText("Neler değişti")).toBeInTheDocument();
    act(() => {
      qc.setQueryData(crbsKeys.i18n("tr"), bundle("tr", {}));
    });
    expect(await screen.findByText("Yenilikler")).toBeInTheDocument();
  });

  it("refreshes the bundle when the admin translation list refetches after an edit", async () => {
    const qc = client();
    qc.setQueryData(crbsKeys.i18n("tr"), bundle("tr", {}));
    const invalidate = vi.spyOn(qc, "invalidateQueries").mockResolvedValue(undefined);
    render(
      <QueryClientProvider client={qc}>
        <I18nProvider initialLocale="tr">
          <Probe />
        </I18nProvider>
      </QueryClientProvider>,
    );
    act(() => {
      qc.setQueryData(crbsKeys.translations("tr"), [{ id: 1, language: "tr", set: "crbs", key: "news.title", text: "Sürüm notları" }]);
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["crbs", "i18n"] });
  });

  it("never applies a bundle of another language (backend fell back to its default)", async () => {
    const qc = client();
    qc.setQueryData(crbsKeys.i18n("tr"), bundle("en", { crbs: { "news.title": "Release notes" } }));
    render(
      <QueryClientProvider client={qc}>
        <I18nProvider initialLocale="tr">
          <Probe />
        </I18nProvider>
      </QueryClientProvider>,
    );
    await act(async () => undefined);
    expect(screen.getByTestId("title")).toHaveTextContent("Yenilikler");
  });

  it("uses the shipped messages without a QueryClient", () => {
    render(
      <I18nProvider initialLocale="tr">
        <Probe />
      </I18nProvider>,
    );
    expect(screen.getByTestId("title")).toHaveTextContent("Yenilikler");
  });
});
