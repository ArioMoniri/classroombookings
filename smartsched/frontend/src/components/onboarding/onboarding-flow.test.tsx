import { readFileSync } from "node:fs";
import path from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { councilBackend } from "@/test/fixtures/council";
import { OnboardingFlow } from "./onboarding-flow";

/** A real file from the backend fixtures (the Bahar list exported as an English CSV). */
const CSV = path.resolve(import.meta.dirname, "../../../../backend/tests/fixtures/universal/bahar_requests_en.csv");

/** The recorded backend plus the routes this screen added since: the AI policy and the commit dry run. */
function withDryRun(backend: ReturnType<typeof councilBackend>, policy: { intake_enabled: boolean }) {
  const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  const dry = { on_conflict: "keep", counts: { meeting_requests: { create: 1348, update: 0, unchanged: 0, conflict: 0 }, sections: { create: 1150, update: 0, unchanged: 0, conflict: 0 }, constraints: { create: 39, update: 0, unchanged: 0, conflict: 0 } }, rows: [], rows_total: 0, conflicts_total: 0, result: { term_code: "2026-BAHAR-EN" } };
  return async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input instanceof Request ? input.url : input), "http://localhost");
    if (url.pathname === "/api/v1/ai/policy") {
      backend.calls.push(`GET ${url.pathname}`);
      return json({ ...policy, vision_enabled: false, signoff: null, notice: { tr: "", en: "" }, notice_version: "1", legal_basis: "" });
    }
    if (init?.method === "POST" && /\/commit$/.test(url.pathname) && JSON.parse(String(init.body ?? "{}")).dry_run) {
      backend.calls.push(`DRY ${url.pathname}`);
      return json(dry);
    }
    return backend.fetch(input, init);
  };
}

// every test starts at a clean address: the flow writes ?job=<id> into it (T-R1-26)
beforeEach(() => window.history.replaceState(null, "", "/onboarding"));

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
  let calls: string[] = [];
  beforeEach(() => {
    const backend = councilBackend();
    calls = backend.calls;
    vi.stubGlobal("fetch", withDryRun(backend, { intake_enabled: true }));
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
    expect(within(screen.getByTestId("file-1")).getByText("general path")).toBeInTheDocument();
    expect(within(progress).getByText("Deterministic (no AI)")).toBeInTheDocument();

    const reviewCard = await screen.findByTestId("onboarding-review", {}, { timeout: 5000 });
    expect(within(reviewCard).getByTestId("blocking-count").textContent).toMatch(/[1-9]\d* blocking/);
    const commitButton = screen.getByTestId("onboarding-commit-button");
    expect(commitButton).toBeDisabled();
    // R3-M-03: the phone's floating capsule says how many decisions are open and is disabled with them
    const capsule = screen.getByTestId("onboarding-commit-capsule");
    expect(capsule).toHaveTextContent(/decisions? pending/);
    expect(within(capsule).getByTestId("onboarding-commit-capsule-button")).toBeDisabled();

    await user.click(within(reviewCard).getByRole("button", { name: "Accept all blocking" }));
    await waitFor(() => expect(screen.getByTestId("blocking-count").textContent).toBe("0 blocking"));
    expect(calls).toContain("POST /api/v1/council/jobs/1/review");

    await user.clear(screen.getByTestId("term-code"));
    await user.type(screen.getByTestId("term-code"), "2026-BAHAR-EN");
    await waitFor(() => expect(screen.getByTestId("onboarding-commit-button")).toBeEnabled());
    // Yaz never writes on the first press (T-R1-24): the dry run's counts in a confirm that says there is no undo
    await user.click(screen.getByTestId("onboarding-commit-button"));
    const confirm = await screen.findByTestId("onboarding-commit-confirm");
    expect(calls).toContain("DRY /api/v1/council/jobs/1/commit");
    expect(calls.filter((c) => c === "POST /api/v1/council/jobs/1/commit")).toHaveLength(0);
    expect(confirm).toHaveTextContent("1,348 new requests will be written into 2026-BAHAR-EN");
    expect(within(confirm).getByTestId("onboarding-commit-confirm-counts")).toHaveTextContent("Rules");
    expect(within(confirm).getByTestId("onboarding-commit-irreversible")).toHaveTextContent("cannot be undone");
    await user.click(within(confirm).getByTestId("onboarding-commit-confirm-button"));
    const result = await screen.findByTestId("onboarding-result");
    expect(result).toHaveTextContent("Written into 2026-BAHAR-EN");
    expect(result).toHaveTextContent("Requests: 1,348");
    expect(result.textContent).not.toMatch(/[a-z]+_[a-z]+/); // no raw keys
    expect(result.textContent).not.toMatch(/\bfaculties\b/); // R3-M-07
  }, 30_000); // the whole flow (upload, polling, review, commit): the 5 s default is too tight on a loaded runner
});

describe("OnboardingFlow with the AI policy off (T-R1-23)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("unticks and disables the AI switch, labels no file AI and starts without the AI wording", async () => {
    const backend = councilBackend();
    vi.stubGlobal("fetch", withDryRun(backend, { intake_enabled: false }));
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <I18nProvider initialLocale="tr">
          <OnboardingFlow />
        </I18nProvider>
      </QueryClientProvider>,
    );
    await user.upload(screen.getByTestId("onboarding-input"), [
      new File([readFileSync(CSV)], "bahar_requests_en.csv", { type: "text/csv" }),
      new File(["x"], "rules_memo.docx"),
      new File(["x"], "taranmis_sinav_programi.pdf"),
    ]);
    const drop = screen.getByTestId("onboarding-drop");
    await waitFor(() => expect(within(drop).getByTestId("onboarding-ai-off")).toHaveTextContent("Yönetici kapattı"));
    const ai = within(drop).getByRole("checkbox", { name: /yapay zekâ modelini kullan/ });
    expect(ai).toHaveAttribute("aria-disabled", "true");
    expect(ai).not.toBeChecked();
    expect(drop.querySelectorAll('[data-method="ai"]')).toHaveLength(0);
    expect(drop.querySelectorAll('[data-method="off"]')).toHaveLength(2);
    expect(screen.getByTestId("onboarding-start")).toHaveTextContent("Başlat · 3 dosya");
  });
});

describe("OnboardingFlow keeps the job in the address (T-R1-26)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    window.history.replaceState(null, "", "/");
  });

  it("reopens ?job=<id> after a reload and lists the recent jobs otherwise", async () => {
    const backend = councilBackend();
    vi.stubGlobal("fetch", withDryRun(backend, { intake_enabled: true }));
    window.history.replaceState(null, "", "/onboarding?job=1");
    renderFlow();
    await screen.findByTestId("onboarding-progress");
    expect(backend.calls).toContain("GET /api/v1/council/jobs/1");
    expect(screen.queryByTestId("onboarding-drop")).toBeNull();
    // a new job: the address forgets the old one and the recent jobs are offered
    await userEvent.setup().click(screen.getByRole("button", { name: "New onboarding" }));
    expect(window.location.search).toBe("");
    const recent = await screen.findByTestId("onboarding-recent");
    expect(within(recent).getByRole("button", { name: "Open job 1" })).toBeInTheDocument();
  });
});

describe("OnboardingFlow: the job's own address, a button drop zone and an accept list (T-R2-20)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    window.history.replaceState(null, "", "/");
  });

  it("opens /onboarding/<id> from the route and goes back to /onboarding for a new job", async () => {
    const backend = councilBackend();
    vi.stubGlobal("fetch", withDryRun(backend, { intake_enabled: true }));
    window.history.replaceState(null, "", "/onboarding/1");
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <I18nProvider initialLocale="en">
          <OnboardingFlow initialJobId={1} />
        </I18nProvider>
      </QueryClientProvider>,
    );
    await screen.findByTestId("onboarding-progress");
    expect(backend.calls).toContain("GET /api/v1/council/jobs/1");
    expect(screen.queryByTestId("onboarding-drop")).toBeNull();
    await userEvent.setup().click(screen.getByRole("button", { name: "New onboarding" }));
    expect(window.location.pathname).toBe("/onboarding");
    expect(window.location.search).toBe("");
    await screen.findByTestId("onboarding-recent");
  });

  it("is one button that the keyboard opens, and the input accepts the listed formats", async () => {
    const backend = councilBackend();
    vi.stubGlobal("fetch", withDryRun(backend, { intake_enabled: true }));
    renderFlow();
    const zone = screen.getByTestId("onboarding-dropzone");
    expect(zone.tagName).toBe("BUTTON");
    expect(zone).toHaveAccessibleName(/Drop files|Dosyaları/);
    expect(zone.querySelector("button, input, a, [tabindex]")).toBeNull(); // no nested control
    const input = screen.getByTestId<HTMLInputElement>("onboarding-input");
    expect(input.accept.split(",")).toEqual(expect.arrayContaining([".xlsx", ".csv", ".pdf", ".docx", ".ics", "image/*"]));
    const click = vi.spyOn(HTMLInputElement.prototype, "click").mockImplementation(() => undefined);
    const user = userEvent.setup();
    zone.focus();
    await user.keyboard("{Enter}");
    await user.keyboard(" ");
    expect(click).toHaveBeenCalledTimes(2);
  });
});
