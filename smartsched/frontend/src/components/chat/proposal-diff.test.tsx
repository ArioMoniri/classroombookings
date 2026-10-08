import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { ProposalDiff } from "./chat-panel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));
const apply = vi.fn(async () => ({ child_run_id: null }));
vi.mock("@/lib/api/shell-extra", async (orig) => ({ ...(await orig<typeof import("@/lib/api/shell-extra")>()), applyProposalSubset: (...a: unknown[]) => apply(...(a as [])) }));

const proposal = {
  id: "d1",
  summary: "Move PHAR 240 to a bigger room",
  moves: [
    { assignment_id: 11, label: "PHAR 240 §1", from: { room: "A206", day: 1, start_period: 1, end_period: 3 }, to: { room: "A204", day: 1, start_period: 1, end_period: 3 } },
    { assignment_id: 12, label: "HEM 334", from: { room: "A204", day: 1, start_period: 1, end_period: 3 }, to: { room: "C201", day: 1, start_period: 1, end_period: 3 } },
  ],
  constraints: [],
  notes: [],
  applied: false,
};

describe("chat proposal as a DiffTable", () => {
  it("lists each move with Turkish slots and applies only the ticked rows", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <I18nProvider initialLocale="tr">
          <ProposalDiff runId={5} proposal={proposal} />
        </I18nProvider>
      </QueryClientProvider>,
    );
    expect(screen.getByText("A 206 · Pzt 08:30–10:50")).toBeInTheDocument();
    expect(screen.getByText("C 201 · Pzt 08:30–10:50")).toBeInTheDocument();
    const boxes = screen.getAllByRole("checkbox");
    expect(boxes).toHaveLength(2);
    await userEvent.click(boxes[1]!);
    await userEvent.click(screen.getByRole("button", { name: "1 değişikliği uygula" }));
    expect(apply).toHaveBeenCalledWith(5, "d1", [11], [11, 12]);
  });
});
