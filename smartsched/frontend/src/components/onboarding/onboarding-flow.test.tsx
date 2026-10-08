import { readFileSync } from "node:fs";
import path from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { getResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { handlers, resetMockState } from "@/mocks/handlers";
import { OnboardingFlow } from "./onboarding-flow";

/** A real file from the backend fixtures (the Bahar list exported as an English CSV). */
const CSV = path.resolve(import.meta.dirname, "../../../../backend/tests/fixtures/universal/bahar_requests_en.csv");

function renderFlow() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale="en">
        <OnboardingFlow />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("OnboardingFlow", () => {
  const calls: string[] = [];
  beforeEach(() => {
    resetMockState();
    calls.length = 0;
    vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      const req = new Request(new URL(String(input), "http://localhost"), init);
      calls.push(`${req.method} ${new URL(req.url).pathname}`);
      return (await getResponse(handlers, req)) ?? new Response("{}", { status: 501 });
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("drops files, shows council progress per file, reviews and commits into a term", async () => {
    const user = userEvent.setup();
    renderFlow();
    const file = new File([readFileSync(CSV)], "bahar_requests_en.csv", { type: "text/csv" });
    await user.upload(screen.getByTestId("onboarding-input"), file);
    expect(screen.getByText("bahar_requests_en.csv")).toBeInTheDocument();
    await user.click(screen.getByTestId("onboarding-start"));

    await screen.findByTestId("onboarding-progress");
    expect(calls).toContain("POST /api/v1/council/jobs");
    // the queued job is replaced by the finished snapshot (polling: jsdom has no EventSource)
    await waitFor(() => expect(within(screen.getByTestId("file-1")).getByTestId("step-structure")).toHaveAttribute("data-status", "DONE"), { timeout: 5000 });
    const progress = screen.getByTestId("onboarding-progress");
    expect(within(screen.getByTestId("file-1")).getByText("general")).toBeInTheDocument();
    expect(within(progress).getByText("Deterministic (no AI)")).toBeInTheDocument();

    const reviewCard = await screen.findByTestId("onboarding-review", {}, { timeout: 5000 });
    expect(within(reviewCard).getByTestId("blocking-count").textContent).toMatch(/[1-9]\d* blocking/);
    const commitButton = screen.getByTestId("onboarding-commit-button");
    expect(commitButton).toBeDisabled();

    await user.click(within(reviewCard).getByRole("button", { name: "Accept all blocking" }));
    await waitFor(() => expect(screen.getByTestId("blocking-count").textContent).toBe("0 blocking"));
    expect(calls).toContain("POST /api/v1/council/jobs/1/review");

    await user.clear(screen.getByTestId("term-code"));
    await user.type(screen.getByTestId("term-code"), "2026-BAHAR-EN");
    await waitFor(() => expect(screen.getByTestId("onboarding-commit-button")).toBeEnabled());
    await user.click(screen.getByTestId("onboarding-commit-button"));
    expect(await screen.findByTestId("onboarding-result")).toHaveTextContent("Written into 2026-BAHAR-EN");
    expect(screen.getByTestId("onboarding-result")).toHaveTextContent("meeting_requests: 1348");
  });
});
