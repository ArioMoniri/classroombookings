// Flow-loop round 2, lane A (T-R2-02, R2-A-03 / R2-S-16): every Dialog and Sheet popup is modal — aria-modal="true" and a
// focus trap of its own (Tab from the last control cycles to the first, Shift+Tab from the first to the last), because
// base-ui's guard-based trap let Tab out of the confirm dialogs into the page (the skip link, the logo). jsdom has no
// layout; e2e/loop-r2-laneA.spec.ts repeats it on a stack.sh build.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Dialog, DialogContent, DialogFooter, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { ConfirmDialog } from "@/components/admin/kit";
import { I18nProvider } from "@/lib/i18n/provider";

const tr = (ui: React.ReactNode) => render(<I18nProvider initialLocale="tr">{ui}</I18nProvider>);
/** base-ui moves the initial focus a tick after mount: let it settle before the test picks its own focus */
const settled = () => new Promise((r) => setTimeout(r, 50));

describe("T-R2-02: confirm dialogs trap focus", () => {
  it("DialogContent is aria-modal and Tab cycles inside it in both directions", async () => {
    const user = userEvent.setup();
    tr(
      <Dialog open>
        <DialogContent role="alertdialog" data-testid="dlg" showCloseButton={false}>
          <DialogTitle>Talebi geri çek</DialogTitle>
          <DialogFooter>
            <button type="button">Vazgeç</button>
            <button type="button">Geri çek</button>
          </DialogFooter>
        </DialogContent>
      </Dialog>,
    );
    const dlg = screen.getByTestId("dlg");
    expect(dlg).toHaveAttribute("role", "alertdialog");
    expect(dlg).toHaveAttribute("aria-modal", "true");
    const first = screen.getByRole("button", { name: "Vazgeç" });
    const last = screen.getByRole("button", { name: "Geri çek" });
    await settled();
    last.focus();
    await user.tab();
    expect(document.activeElement).toBe(first);
    await user.tab({ shift: true });
    expect(document.activeElement).toBe(last);
    for (let i = 0; i < 10; i++) {
      await user.tab();
      expect(dlg.contains(document.activeElement)).toBe(true);
    }
  });

  it("SheetContent (the phone confirm) is aria-modal and traps Tab the same way", async () => {
    const user = userEvent.setup();
    tr(
      <Sheet open>
        <SheetContent side="bottom" role="alertdialog" data-testid="sheet" showCloseButton={false}>
          <SheetTitle>Talebi geri çek</SheetTitle>
          <button type="button">Vazgeç</button>
          <button type="button">Geri çek</button>
        </SheetContent>
      </Sheet>,
    );
    const sheet = screen.getByTestId("sheet");
    expect(sheet).toHaveAttribute("aria-modal", "true");
    await settled();
    screen.getByRole("button", { name: "Geri çek" }).focus();
    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Vazgeç" }));
  });

  it("the kit ConfirmDialog is an alertdialog", () => {
    tr(<ConfirmDialog open onOpenChange={vi.fn()} title="Bağlantıyı sıfırla" confirmLabel="Sıfırla" onConfirm={vi.fn()} />);
    expect(screen.getByRole("alertdialog", { name: "Bağlantıyı sıfırla" })).toHaveAttribute("aria-modal", "true");
  });
});
