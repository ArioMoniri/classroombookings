import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { assignment } from "@/components/timetable/model/fixtures";
import { I18nProvider } from "@/lib/i18n/provider";
import { ClassInspector, type InspectorProps } from "./class-inspector";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale="en">{ui}</I18nProvider>
    </QueryClientProvider>,
  );
}

const a = assignment({ id: 9, label: "MAT 101 §2", day: 3, sp: 7, ep: 9, rooms: [4], instr: ["Dr. Kaya"], instr_ids: [77], size: 102, locked: false, origin: "MANUAL" });

const base = (over: Partial<InspectorProps> = {}): InspectorProps => ({
  // termId null: the detail query stays idle (no network in unit tests)
  termId: null,
  runId: 5,
  kind: "meetings",
  assignment: a,
  roomName: () => "A 204",
  roomCap: () => 156,
  allWeeks: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14],
  surface: "calendar",
  onClose: vi.fn(),
  appear: false,
  ...over,
});

describe("ClassInspector", () => {
  it("shows when/where with fit, who it placed, and the instructor link honours the shell URL contract", () => {
    wrap(<ClassInspector {...base()} />);
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("MAT 101 §1");
    expect(screen.getByTestId("inspector-room")).toHaveTextContent("A 204 · 102 students · 156 seats (65%)");
    expect(screen.getByTestId("inspector-fit")).toBeInTheDocument();
    expect(screen.getByText("Placed by: By hand")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Dr. Kaya" })).toHaveAttribute("href", "/timetable?lens=week&subject=instructor:77&run=5");
  });

  it("lock shows Saving… then Saved; a failed save says Not saved", async () => {
    const user = userEvent.setup();
    let resolve: (v: boolean) => void = () => undefined;
    const onLock = vi.fn(() => new Promise<boolean>((r) => (resolve = r)));
    const { unmount } = wrap(<ClassInspector {...base({ onLock })} />);
    await user.click(screen.getByTestId("inspector-lock"));
    expect(onLock).toHaveBeenCalledWith(true);
    expect(screen.getByTestId("inspector-save")).toHaveTextContent("Saving…");
    resolve(true);
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    unmount();

    wrap(<ClassInspector {...base({ onLock: () => Promise.resolve(false) })} />);
    await user.click(screen.getByTestId("inspector-lock"));
    expect(await screen.findByText("Not saved")).toBeInTheDocument();
  });

  it("read-only hides the edit actions but keeps the explanation sections", () => {
    wrap(<ClassInspector {...base({ readOnly: true, onLock: vi.fn(), onMove: vi.fn() })} />);
    expect(screen.queryByTestId("inspector-lock")).toBeNull();
    expect(screen.queryByTestId("inspector-move")).toBeNull();
    expect(screen.getByText("Why here")).toBeInTheDocument();
    expect(screen.getByTestId("explain-placement")).toBeInTheDocument();
  });
});
