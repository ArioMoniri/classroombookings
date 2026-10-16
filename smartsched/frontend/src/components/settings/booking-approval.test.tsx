/** F-01 S01 / F-11 S07: the approval mode (rules | all) with a one-line explanation of each. */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { BookingApprovalFields } from "./booking-approval";

describe("BookingApprovalFields", () => {
  it("explains both modes and who books directly, and reports the choice", async () => {
    const onChange = vi.fn();
    render(
      <I18nProvider initialLocale="tr">
        <BookingApprovalFields value="rules" onChange={onChange} />
      </I18nProvider>,
    );
    expect(screen.getByText("Rezervasyon onayı")).toBeInTheDocument();
    expect(screen.getByText(/Yalnız onay kuralı olan derslikler onaycıya gider/)).toBeInTheDocument();
    expect(screen.getByText(/her talep önce bir yöneticiye gider/i)).toBeInTheDocument();
    expect(screen.getByTestId("approval-mode-direct")).toHaveTextContent("Onaysız doğrudan rezervasyon");
    await userEvent.click(screen.getByRole("radio", { name: "Her talep önce onaya" }));
    expect(onChange).toHaveBeenCalledWith("all");
  });
});
