import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { suggestion } from "./learning-model.test";
import { ResetDialog } from "./reset-dialog";
import { SuggestionCard } from "./suggestion-card";

function card(over: Partial<Parameters<typeof SuggestionCard>[0]> = {}) {
  const props = { s: suggestion(), canAct: true, onAccept: vi.fn(), onReject: vi.fn(), onSnooze: vi.fn(), ...over };
  render(
    <I18nProvider initialLocale="tr">
      <SuggestionCard {...props} />
    </I18nProvider>,
  );
  return props;
}

describe("SuggestionCard", () => {
  it("shows the claim, the confidence word + meter and the evidence, dashed until accepted", () => {
    card();
    expect(screen.getByRole("heading", { name: /A 206 tercih edilsin mi/ })).toBeInTheDocument();
    const meter = screen.getByRole("meter");
    expect(meter).toHaveAttribute("aria-valuetext", "Orta güven, 2 dönemin 2'sinde");
    expect(meter).toHaveAttribute("data-steps", "2");
    expect(screen.getByText(/Kanıt · 2 dönemin 2'sinde/)).toBeInTheDocument();
    expect(screen.getByTestId("suggestion-card").className).toContain("border-dashed");
    fireEvent.click(screen.getByTestId("suggestion-evidence-toggle"));
    expect(screen.getByText("2026-BAHAR")).toBeInTheDocument();
  });

  it("accepts as a soft preference with weight Normal (5), or dismisses with a reason", () => {
    const p = card();
    fireEvent.click(screen.getByTestId("suggestion-accept"));
    expect(p.onAccept).toHaveBeenCalledWith(5);
    fireEvent.click(screen.getByTestId("suggestion-reject"));
    fireEvent.click(screen.getByTestId("dismiss-wrongPerson"));
    expect(p.onReject).toHaveBeenCalledWith("Yanlış kişi eşleşmesi");
  });

  it("keyboard: a accepts, d opens the reasons (never applies by itself)", () => {
    const p = card();
    const el = screen.getByTestId("suggestion-card");
    fireEvent.keyDown(el, { key: "a" });
    expect(p.onAccept).toHaveBeenCalledWith(5);
    fireEvent.keyDown(el, { key: "d" });
    expect(screen.getByTestId("dismiss-skip")).toBeInTheDocument();
  });

  it("hides the actions without planning.edit and says why", () => {
    card({ canAct: false });
    expect(screen.queryByTestId("suggestion-accept")).toBeNull();
    expect(screen.getByText(/planlama düzenleme izni gerekir/)).toBeInTheDocument();
  });

  it("collapses to a receipt with Geri al after an accept", () => {
    const onUndo = vi.fn();
    card({ receipt: { kind: "accepted", constraintId: 42 }, onUndo });
    expect(screen.getByTestId("suggestion-receipt")).toHaveTextContent("Yumuşak tercih eklendi");
    fireEvent.click(screen.getByTestId("suggestion-undo"));
    expect(onUndo).toHaveBeenCalled();
  });
});

describe("ResetDialog", () => {
  const renderDialog = (scope: "all" | "person") =>
    render(
      <QueryClientProvider client={new QueryClient()}>
        <I18nProvider initialLocale="tr">
          <ResetDialog open onOpenChange={() => undefined} scope={scope} subject={scope === "person" ? { id: 3, label: "Öğr. Gör. S. K." } : undefined} />
        </I18nProvider>
      </QueryClientProvider>,
    );

  it("'Tümü' needs a reason and the typed word SIFIRLA before it resets", () => {
    renderDialog("all");
    const go = screen.getByTestId("reset-confirm");
    expect(go).toBeDisabled();
    fireEvent.change(screen.getByTestId("reset-reason"), { target: { value: "yeniden yapılanma" } });
    expect(go).not.toBeDisabled();
    fireEvent.change(screen.getByTestId("reset-word"), { target: { value: "SIFIR" } });
    fireEvent.click(go);
    expect(screen.getByRole("alert")).toHaveTextContent("Yazılan kelime eşleşmiyor");
  });

  it("a person reset quotes the subject and the 30-day undo; no typed word", () => {
    renderDialog("person");
    expect(screen.getByText("Öğr. Gör. S. K. için öğrenilenler sıfırlansın mı?")).toBeInTheDocument();
    expect(screen.getByText(/30 gün içinde/)).toBeInTheDocument();
    expect(screen.queryByTestId("reset-word")).toBeNull();
  });
});
