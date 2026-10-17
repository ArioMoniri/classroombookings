/**
 * Round-1 T-R1-41 on the learning memory: "Son sıfırlamalar" names the person by title + initials (the server's
 * subject_label), never "#98", and the standalone page has its own h1.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { learningApi, type ResetRow } from "@/lib/api/learning";
import { I18nProvider } from "@/lib/i18n/provider";
import { LearningMemoryPanel } from "./learning-memory-panel";

vi.mock("@/lib/permissions", () => ({ usePermissions: () => ({ loading: false, perms: [], can: () => true, canAll: () => true }) }));
vi.mock("@/components/shell/term-switcher", () => ({ useActiveTerm: () => ({ term: { id: 2, code: "2026-GUZ" }, isLoading: false }) }));
vi.mock("@/lib/api/hooks", () => ({ useTerms: () => ({ data: [{ id: 2, code: "2026-GUZ" }] }) }));
vi.mock("@/components/onboarding/intake-memory", () => ({ IntakeMemoryPanel: () => null }));

const row = (over: Partial<ResetRow>): ResetRow => ({ id: 7, kind: "RESET", scope: "person", value: "98", reason: "görev değişikliği", actor_id: 1, created_at: "2026-10-16T11:58:00", undo_until: "2026-11-15T11:58:00", days_left: 29, undoable: true, undone_at: null, purged_at: null, counts: {}, subject_label: "Öğr. Gör. A. Y. Y.", ...over });

function mount(heading?: "h1" | "h2") {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">
        <LearningMemoryPanel heading={heading} />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("LearningMemoryPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("names the person of a reset by title + initials, never by '#<id>'", async () => {
    vi.spyOn(learningApi, "summary").mockResolvedValue({ terms: [], observations: 10, hidden_by_reset: 2, suggestions: {} });
    vi.spyOn(learningApi, "resets").mockResolvedValue([row({}), row({ id: 6, kind: "ERASURE", subject_label: null, undoable: false, purged_at: "2026-10-15T10:00:00" })]);
    mount("h1");
    const rows = await screen.findAllByTestId("reset-row");
    expect(rows[0]).toHaveTextContent("Öğr. Gör. A. Y. Y.");
    expect(rows[1]).toHaveTextContent("kaydı bulunmayan kişi");
    for (const r of rows) expect(r.textContent).not.toMatch(/#\d/);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("stays an h2 where Settings mounts it under its own h1", async () => {
    vi.spyOn(learningApi, "summary").mockResolvedValue({ terms: [], observations: 0, hidden_by_reset: 0, suggestions: {} });
    vi.spyOn(learningApi, "resets").mockResolvedValue([]);
    mount();
    await screen.findByText("Henüz sıfırlama yok.");
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
    expect(screen.getByRole("heading", { level: 2, name: "Öğrenme belleği" })).toBeInTheDocument();
  });
});
