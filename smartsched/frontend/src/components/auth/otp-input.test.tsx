// AUX-02 (docs/design/v3/auth.md §10.3, §10.4, §13): one real input drawn as 6 slots (input-otp, MIT); paste strips
// spaces and hyphens and fires onComplete once; one textbox named "Doğrulama kodu"; Backspace and arrows work; the
// slots are ≥ 44 px and the text ≥ 16 px on phones; the recovery field normalises its value.
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { OtpInput } from "./otp-input";
import { RecoveryCodeField } from "./recovery-code-field";

function Harness({ onComplete, state }: { onComplete?: (v: string) => void; state?: "idle" | "error" | "success" }) {
  const [v, setV] = useState("");
  return (
    <I18nProvider initialLocale="tr">
      <OtpInput id="otp" value={v} onChange={setV} onComplete={onComplete} state={state} message={state === "error" ? "Kod doğru değil." : undefined} />
      <output data-testid="value">{v}</output>
    </I18nProvider>
  );
}

function paste(el: HTMLElement, text: string) {
  fireEvent.paste(el, { clipboardData: { getData: () => text } });
}

describe("OtpInput", () => {
  it("is one textbox named 'Doğrulama kodu' with the one-time-code attributes", () => {
    render(<Harness />);
    const boxes = screen.getAllByRole("textbox");
    expect(boxes).toHaveLength(1);
    const input = screen.getByRole("textbox", { name: "Doğrulama kodu" });
    expect(input).toHaveAttribute("inputmode", "numeric");
    expect(input).toHaveAttribute("autocomplete", "one-time-code");
    expect(input).toHaveAttribute("maxlength", "6");
    expect(input.getAttribute("pattern")).toBeTruthy();
    expect(input).toHaveAccessibleDescription(/6 haneli kod/);
  });

  it.each(["123 456", "123-456", " 12 34-56 "])("paste %j → 6 digits and onComplete once", async (text) => {
    const onComplete = vi.fn();
    render(<Harness onComplete={onComplete} />);
    const input = screen.getByRole("textbox", { name: "Doğrulama kodu" });
    input.focus();
    paste(input, text);
    expect(await screen.findByTestId("value")).toHaveTextContent("123456");
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onComplete).toHaveBeenCalledWith("123456");
  });

  it("typing, Backspace and the arrow keys work on the one input", async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    render(<Harness onComplete={onComplete} />);
    const input = screen.getByRole("textbox", { name: "Doğrulama kodu" });
    await user.click(input);
    await user.keyboard("12a3");
    expect(screen.getByTestId("value")).toHaveTextContent(/^123$/);
    await user.keyboard("{Backspace}");
    expect(screen.getByTestId("value")).toHaveTextContent(/^12$/);
    await user.keyboard("{ArrowLeft}{ArrowRight}3456");
    expect(screen.getByTestId("value")).toHaveTextContent("123456");
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it("draws 6 slots grouped 3 + 3, ≥ 44 px wide, 48 × 56 and 16 px+ text on coarse pointers", () => {
    render(<Harness />);
    const slots = document.querySelectorAll("[data-otp-slot]");
    expect(slots).toHaveLength(6);
    expect(document.querySelectorAll("[data-otp-group]")).toHaveLength(2);
    for (const s of slots) {
      expect(s.className).toMatch(/\bw-11\b/);
      expect(s.className).toMatch(/\bh-13\b/);
      expect(s.className).toMatch(/pointer-coarse:w-12/);
      expect(s.className).toMatch(/pointer-coarse:h-14/);
      expect(s.className).toMatch(/text-2xl/);
    }
    // the real input carries the 16 px rule too (iOS does not zoom)
    expect(screen.getByRole("textbox").className).toMatch(/text-base/);
  });

  it("error: invalid, the message linked, every slot in the error edge", () => {
    render(<Harness state="error" />);
    const input = screen.getByRole("textbox", { name: "Doğrulama kodu" });
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription(/Kod doğru değil/);
    for (const s of document.querySelectorAll("[data-otp-slot]")) expect(s).toHaveAttribute("data-state", "error");
  });

  it("success: a polite status 'Doğrulandı'", () => {
    render(<Harness state="success" />);
    expect(screen.getByRole("status")).toHaveTextContent("Doğrulandı");
  });
});

function RecoveryHarness({ onSubmit }: { onSubmit?: (v: string) => void }) {
  const [v, setV] = useState("");
  return (
    <I18nProvider initialLocale="tr">
      <form onSubmit={(e) => (e.preventDefault(), onSubmit?.(v))}>
        <RecoveryCodeField id="rc" value={v} onChange={setV} />
      </form>
      <output data-testid="rvalue">{v}</output>
    </I18nProvider>
  );
}

describe("RecoveryCodeField", () => {
  it("is named 'Kurtarma kodu' with characters capitalisation and no autocorrect", () => {
    render(<RecoveryHarness />);
    const input = screen.getByRole("textbox", { name: "Kurtarma kodu" });
    expect(input).toHaveAttribute("autocapitalize", "characters");
    expect(input).toHaveAttribute("autocorrect", "off");
    expect(input).toHaveAttribute("spellcheck", "false");
    expect(input).toHaveAttribute("autocomplete", "off");
    expect(input).toHaveAccessibleDescription(/bir kez kullanılır/);
  });

  it("normalises case, spaces and hyphens, O → 0 and I/L → 1, into XXXX-XXXX-XXXX-XXXX", async () => {
    const user = userEvent.setup();
    render(<RecoveryHarness />);
    const input = screen.getByRole("textbox", { name: "Kurtarma kodu" });
    await user.click(input);
    await user.paste("abcd efgh-ijkl mnop");
    expect(screen.getByTestId("rvalue")).toHaveTextContent("ABCD-EFGH-1JK1-MN0P");
  });
});
