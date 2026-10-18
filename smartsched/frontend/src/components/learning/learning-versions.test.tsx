/**
 * AS-17 / RF-07 in the learning memory: "Öğrenmeyi yenile" records a version, "Bu sürüme dön" reverts behind a
 * confirmation (focus back on the refresh button), and one habit can be turned off, corrected or tuned.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { learningVersionsApi, type LearningVersion, type Prior } from "@/lib/api/learning-versions";
import { I18nProvider } from "@/lib/i18n/provider";
import { filterPriors, LearningHabits } from "./learning-habits";
import { LearningVersions } from "./learning-versions";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function wrap(node: ReactNode) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">{node}</I18nProvider>
    </QueryClientProvider>,
  );
}

const v = (id: number, number: number, trigger = "manual"): LearningVersion => ({ id, number, trigger, trigger_label: { tr: trigger === "manual" ? "Elle" : "Gece", en: "x" }, created_at: "2026-10-18T06:00:00", observations: 120, priors: 30, suggestible: 14, checksum: "", diff: { new: [], dropped: [], changed: [], counts: { new: 2, dropped: 1, changed: 3 } }, restored_from: null });

describe("LearningVersions", () => {
  beforeEach(() => {
    vi.spyOn(learningVersionsApi, "settings").mockResolvedValue({ nightly_refresh: false });
    vi.spyOn(learningVersionsApi, "calibration").mockResolvedValue({ proposals: [], applied: {}, confidence: "none" });
  });
  afterEach(() => vi.restoreAllMocks());

  it("refreshes learning for the term and lists versions with their diff", async () => {
    vi.spyOn(learningVersionsApi, "versions").mockResolvedValue({ versions: [v(12, 3), v(11, 2, "nightly")], pinned_version_id: null, nightly_refresh: false });
    const refresh = vi.spyOn(learningVersionsApi, "refresh").mockResolvedValue({ version: v(13, 4) });
    wrap(<LearningVersions termId={2} />);
    const rows = await screen.findAllByTestId("version-row");
    expect(rows[0]).toHaveTextContent("Sürüm 3");
    expect(rows[0]).toHaveTextContent("120 gözlem · 14 öneri · +2 yeni, −1 düşen, 3 değişen");
    expect(rows[0]).toHaveTextContent("Geçerli");
    expect(within(rows[0]!).queryByTestId("version-revert")).toBeNull();
    await act(async () => { fireEvent.click(screen.getByTestId("learning-refresh")); });
    await waitFor(() => expect(refresh).toHaveBeenCalledWith(2));
  });

  it("reverts to an older version after a confirmation and gives focus back to the refresh button", async () => {
    vi.spyOn(learningVersionsApi, "versions").mockResolvedValue({ versions: [v(12, 3), v(11, 2)], pinned_version_id: null, nightly_refresh: false });
    const revert = vi.spyOn(learningVersionsApi, "revert").mockResolvedValue({ identical: false, version: v(13, 4, "revert") });
    wrap(<LearningVersions termId={2} />);
    const rows = await screen.findAllByTestId("version-row");
    fireEvent.click(within(rows[1]!).getByTestId("version-revert"));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("Sürüm 2'e dönülsün mü?");
    await act(async () => { fireEvent.click(within(dialog).getByRole("button", { name: "Bu sürüme dön" })); });
    await waitFor(() => expect(revert).toHaveBeenCalledWith(11));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByTestId("learning-refresh")));
  });

  it("an empty term reads the needs sentence", async () => {
    vi.spyOn(learningVersionsApi, "versions").mockResolvedValue({ versions: [], pinned_version_id: null, nightly_refresh: false, needs: { tr: "Henüz öğrenme sürümü yok: Öğrenmeyi yenile", en: "x" } });
    wrap(<LearningVersions termId={2} />);
    expect(await screen.findByTestId("versions-empty")).toHaveTextContent("Henüz öğrenme sürümü yok");
  });
});

const prior = (over: Partial<Prior>): Prior => ({ id: 7, subject: { type: "instructor", id: "98", label: "Dr. A. Y." }, attribute: "building", value: "C", value_label: { tr: "C Blok", en: "Block C" }, confidence: 0.8, suggestible: true, evidence: {}, ...over });

describe("LearningHabits", () => {
  afterEach(() => vi.restoreAllMocks());

  it("turns one habit off with a reason", async () => {
    vi.spyOn(learningVersionsApi, "priors").mockResolvedValue([prior({})]);
    const put = vi.spyOn(learningVersionsApi, "setHabit").mockResolvedValue({});
    wrap(<LearningHabits termId={2} />);
    const row = await screen.findByTestId("habit-row");
    expect(row).toHaveTextContent("Dr. A. Y.: bina C Blok");
    fireEvent.click(within(row).getByTestId("habit-edit"));
    await act(async () => { fireEvent.click(within(row).getByTestId("habit-save")); });
    await waitFor(() => expect(put).toHaveBeenCalledWith(7, { state: "disabled", reason: undefined, value: undefined, weight: undefined }));
  });

  it("corrects a habit to another value, tunes the weight, and a corrected one shows its state", async () => {
    vi.spyOn(learningVersionsApi, "priors").mockResolvedValue([prior({}), prior({ id: 8, value: "A", value_label: "A Blok", evidence: { habit: { state: "corrected", to: "B" } } })]);
    const put = vi.spyOn(learningVersionsApi, "setHabit").mockResolvedValue({});
    wrap(<LearningHabits termId={2} />);
    const rows = await screen.findAllByTestId("habit-row");
    expect(rows[1]).toHaveTextContent("Düzeltildi: B");
    fireEvent.click(within(rows[0]!).getByTestId("habit-edit"));
    fireEvent.click(within(rows[0]!).getByTestId("habit-do-corrected"));
    fireEvent.click(within(rows[0]!).getByTestId("habit-save"));
    expect(await within(rows[0]!).findByRole("alert")).toHaveTextContent("Doğru değeri yazın.");
    fireEvent.change(within(rows[0]!).getByTestId("habit-value"), { target: { value: "D" } });
    await act(async () => { fireEvent.click(within(rows[0]!).getByTestId("habit-save")); });
    await waitFor(() => expect(put).toHaveBeenCalledWith(7, { state: "corrected", reason: undefined, value: "D", weight: undefined }));
    fireEvent.click(within(rows[1]!).getByTestId("habit-edit"));
    fireEvent.click(within(rows[1]!).getByTestId("habit-do-tuned"));
    fireEvent.change(within(rows[1]!).getByTestId("habit-weight"), { target: { value: "2" } });
    await act(async () => { fireEvent.click(within(rows[1]!).getByTestId("habit-save")); });
    await waitFor(() => expect(put).toHaveBeenCalledWith(8, { state: "tuned", reason: undefined, value: undefined, weight: 2 }));
  });

  it("searches Turkish-insensitively", () => {
    const list = [prior({}), prior({ id: 9, subject: { type: "course", id: "1", label: "İnşaat Mühendisliği" } })];
    expect(filterPriors(list, "insaat", "tr", (a) => a).map((p) => p.id)).toEqual([9]);
  });
});
