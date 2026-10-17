/** F-01 S08: the reject dialog needs a reason code and a written reason; nothing is sent without both. */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { RejectDialog } from "./reject-dialog";

function renderDialog(props: Partial<Parameters<typeof RejectDialog>[0]> = {}, locale: "tr" | "en" = "tr") {
  const onConfirm = vi.fn();
  render(
    <I18nProvider initialLocale={locale}>
      <RejectDialog open onOpenChange={() => undefined} room="C 303" onConfirm={onConfirm} {...props} />
    </I18nProvider>,
  );
  return { onConfirm };
}

describe("RejectDialog", () => {
  it("offers exactly the four reason codes in Turkish", async () => {
    renderDialog();
    const dialog = await screen.findByTestId("reject-dialog");
    const codes = within(dialog).getByTestId("reject-codes");
    expect(within(codes).getAllByRole("radio")).toHaveLength(4);
    for (const l of ["Oda uygun değil", "Kapasite yetersiz", "Rezervasyon kurallarına uygun değil", "Diğer"]) expect(within(codes).getByLabelText(l)).toBeInTheDocument();
    expect(within(dialog).getByText("C 303 talebini reddet")).toBeInTheDocument();
  });

  it("refuses an empty submit with a message next to each missing field", async () => {
    const { onConfirm } = renderDialog();
    const confirm = await screen.findByTestId("reject-confirm");
    expect(confirm).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(confirm);
    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.getByTestId("reject-code-error")).toHaveTextContent("Bir gerekçe türü seçin.");
    expect(screen.getByTestId("reject-text-error")).toHaveTextContent("Gerekçeyi yazın");
  });

  it("counts spaces and NBSP as blank, then sends the code and the trimmed text", async () => {
    const { onConfirm } = renderDialog();
    await userEvent.click(await screen.findByLabelText("Diğer"));
    await userEvent.type(screen.getByTestId("reject-text"), "    ");
    await userEvent.click(screen.getByTestId("reject-confirm"));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.queryByTestId("reject-code-error")).toBeNull();
    expect(screen.getByTestId("reject-text-error")).toBeInTheDocument();

    await userEvent.click(screen.getByLabelText("Oda uygun değil"));
    await userEvent.clear(screen.getByTestId("reject-text"));
    await userEvent.type(screen.getByTestId("reject-text"), "  Bu saatte bölüm sınavı var. ");
    expect(screen.getByTestId("reject-count")).toHaveTextContent("30 / 1000");
    expect(screen.getByTestId("reject-confirm")).not.toHaveAttribute("aria-disabled");
    await userEvent.click(screen.getByTestId("reject-confirm"));
    expect(onConfirm).toHaveBeenCalledWith({ reason_code: "room_unavailable", reason: "Bu saatte bölüm sınavı var." });
  });

  it("carries the drawer's note over, names a group and the suggested room, shows the backend's refusal (English)", async () => {
    renderDialog({ count: 2, suggestion: "C 305", initialText: "Bakım", error: "a rejection needs a reason" }, "en");
    expect(await screen.findByText("Decline all 2 periods", { selector: "h2" })).toBeInTheDocument();
    expect(screen.getByTestId("reject-text")).toHaveValue("Bakım");
    expect(screen.getByTestId("reject-suggestion")).toHaveTextContent("C 305");
    expect(screen.getByTestId("reject-error")).toHaveTextContent("a rejection needs a reason");
    expect(screen.getByTestId("reject-confirm")).toHaveTextContent("Decline all 2 periods");
  });
});
