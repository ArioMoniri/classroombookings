/** Test helpers for the welcome guide's vitest files (payload builders, providers). Not used by the app. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { WelcomeState, welcomeKeys } from "@/lib/api/welcome";
import { I18nProvider } from "@/lib/i18n/provider";
import { useWelcomeStore } from "./welcome-store";

export function makeState(over: Record<string, unknown> = {}): WelcomeState {
  return WelcomeState.parse({
    enabled: { sheet: true, tour: true, checklist: true, hints: true },
    audiences: ["academician"],
    primary: "academician",
    show: null,
    department: "Psikoloji",
    first_name: "Ayşe",
    sheet: { cards: [], updated: false },
    tour: { steps: [] },
    checklist: { items: [], hidden: false },
    hints: [],
    ...over,
  });
}

export function resetWelcomeStore() {
  useWelcomeStore.setState({ sheet: null, tour: null, checklistOpen: false, dismissedHints: [], localDone: [], autoHint: null });
  try {
    window.sessionStorage.clear();
  } catch {
    /* none */
  }
}

export function renderWelcome(ui: ReactNode, opts: { state?: WelcomeState; locale?: "tr" | "en" } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  if (opts.state) qc.setQueryData(welcomeKeys.state, opts.state);
  const utils = render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale={opts.locale ?? "tr"}>{ui}</I18nProvider>
    </QueryClientProvider>,
  );
  return { ...utils, qc };
}

/** matchMedia with a fixed answer per query fragment (e.g. phone: max-width queries match). */
export function mockMedia(match: (query: string) => boolean) {
  window.matchMedia = ((query: string) => ({
    matches: match(query),
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}
export const PHONE_MEDIA = (q: string) => q.includes("max-width") || q.includes("coarse");
export const DESKTOP_MEDIA = (q: string) => q.includes("min-width");
