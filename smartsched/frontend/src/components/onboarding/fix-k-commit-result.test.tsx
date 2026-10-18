// E2EB-F12 (FIX-K): after "Yaz" the result takes focus (the phone capsule unmounts); re-uploading an identical
// room list reads "Derslikler: 87 · değişiklik yok" instead of "aktarıcılar tarafından yazıldı"; the diff note is plain.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CommitOut, CouncilJob } from "@/lib/api/council";
import { I18nProvider } from "@/lib/i18n/provider";
import { CommitPanel } from "./commit-panel";
import { useOnboardingCopy } from "./copy";

beforeEach(() => vi.stubGlobal("fetch", vi.fn(async () => new Response("[]", { status: 200, headers: { "content-type": "application/json" } }))));
afterEach(() => vi.unstubAllGlobals());

const JOB = { id: 3, files: [{ index: 0, filename: "room_master.csv" }], plan: { groups: [], global_files: [0] } } as unknown as CouncilJob;
const RESULT = { term_code: "2026-GUZ", files: [0], fast_path: [], general: {}, constraints_created: [], constraints_rejected: [], constraints_total: 0, changes: { rooms: { create: 0, update: 0, unchanged: 87, conflict: 0 } } } as unknown as CommitOut;

function Hint() {
  return <p data-testid="hint">{useOnboardingCopy().diffHint}</p>;
}

const wrap = (result: CommitOut) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">
        <CommitPanel job={JOB} blocking={0} busy={false} result={result} onCommit={() => undefined} />
      </I18nProvider>
    </QueryClientProvider>,
  );

describe("onboarding commit result (E2EB-F12)", () => {
  it("an unchanged re-upload says how many rooms it read and that nothing changed, and takes focus", async () => {
    wrap(RESULT);
    const box = screen.getByTestId("onboarding-result");
    expect(box).toHaveTextContent("Derslikler: 87 · değişiklik yok");
    expect(box).not.toHaveTextContent("aktarıcılar");
    await waitFor(() => expect(document.activeElement).toBe(screen.getByTestId("onboarding-result-title")));
  });

  it("the diff note is plain Turkish", () => {
    render(
      <I18nProvider initialLocale="tr">
        <Hint />
      </I18nProvider>,
    );
    expect(screen.getByTestId("hint")).toHaveTextContent("Önizleme: veritabanı değişmedi.");
  });
});
