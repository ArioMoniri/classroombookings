/** Test helpers for the helper's vitest files (providers, a card host with spies). Not used by the app. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { CardHostContext, type CardHost } from "./cards/context";
import { IDLE_TURN, useHelperStore } from "./helper-store";
import fixtures from "./__fixtures__/cards.json";
import { HelperCard } from "./schema.gen";

export type FixtureName = keyof typeof fixtures;
export const card = (name: FixtureName) => HelperCard.parse(fixtures[name]);

export function makeHost(over: Partial<CardHost> = {}): CardHost {
  return {
    runner: { ask: vi.fn(async () => undefined), runAction: vi.fn(async () => undefined), confirm: vi.fn(async () => undefined), undo: vi.fn(async () => undefined), refresh: vi.fn(async () => undefined), cancel: vi.fn() },
    locale: "tr",
    can: () => true,
    actions: null,
    actionVerb: (a) => (a === "create_booking" ? "Rezerve et" : null),
    go: vi.fn(),
    showMe: vi.fn(),
    searchMenu: vi.fn(),
    textOnly: false,
    ...over,
  };
}

export function renderHelper(ui: ReactNode, opts: { locale?: "tr" | "en"; host?: CardHost; qc?: QueryClient } = {}) {
  const qc = opts.qc ?? new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapped = opts.host ? <CardHostContext.Provider value={opts.host}>{ui}</CardHostContext.Provider> : ui;
  const utils = render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale={opts.locale ?? "tr"}>{wrapped}</I18nProvider>
    </QueryClientProvider>,
  );
  return { ...utils, qc };
}

export function resetHelperStore() {
  useHelperStore.setState({ open: false, opener: null, entries: [], turn: IDLE_TURN, textOnly: false, pendingAsk: null, pendingAction: null, showMe: null, guideSeed: null });
}
