/**
 * Gözetmen ekle on the real 2026 Final plan (fixture: plan #2 of "Final (A)", instructor_pool none, two pool
 * members added after the solve): the picker lists the free people from `GET …/candidates` and everyone else as a
 * disabled row with the server's reason; Ekle posts `{post_key, person_key, reason}` and a 409 shows the server's
 * sentence, its reason text and the problems. The progress panel shows the backend's phase and percentage, and
 * while solving (pct 30) the elapsed time against the limit; resolved shortages read "Giderildi".
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "@/lib/api/client";
import type { Candidates, Diagnosis, PlanBrief, Post } from "@/lib/api/invigilation";
import { I18nProvider } from "@/lib/i18n/provider";
import fx from "./__fixtures__/add-duty-final.json";

const state = vi.hoisted(() => ({ posted: [] as { path: string; body: unknown }[], candidates: null as unknown, reply: null as null | (() => unknown) }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  request: async (path: string, opts: { method?: string; body?: unknown } = {}) => {
    if (path === "/invigilation/plans/2/candidates") return state.candidates;
    if (path === "/invigilation/plans/2/duties" && opts.method === "POST") {
      state.posted.push({ path, body: opts.body });
      return state.reply!();
    }
    throw new Error(`unexpected ${opts.method ?? "GET"} ${path}`);
  },
}));

import { DiagnosisList } from "./diagnosis-list";
import { RunningPanel } from "./plan-detail";
import { ReassignDialog } from "./reassign-dialog";

const post = fx.post as unknown as Post;

function wrap(ui: React.ReactNode, locale: "tr" | "en" = "tr") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale={locale}>{ui}</I18nProvider>
    </QueryClientProvider>,
  );
}

describe("Gözetmen ekle", () => {
  beforeEach(() => {
    state.posted = [];
    state.candidates = fx.candidates;
    state.reply = () => fx.added;
    toast.success.mockReset();
  });

  it("lists the free people of the post and adds the one picked, with the reason", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    wrap(<ReassignDialog planId={2} target={{ post, duty: null }} onClose={onClose} />);
    const dlg = await screen.findByTestId("invig-reassign-dialog");
    expect(dlg).toHaveTextContent("salonuna gözetmen ekle");
    expect(dlg).toHaveTextContent("1/3 gözetmen");
    // the old "about a minute" wording is gone (candidates answer in about 0.3 s)
    expect(dlg).not.toHaveTextContent(/dakika/);
    const ok = within(dlg).getByTestId("invig-reassign-ok");
    expect(ok).toBeDisabled();
    await user.click(await within(dlg).findByRole("radio", { name: /Fixture İki/ }));
    await user.type(within(dlg).getByTestId("invig-reassign-reason"), "elle dolduruldu");
    expect(ok).toHaveTextContent("Ekle");
    await user.click(ok);
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(state.posted).toEqual([{ path: "/invigilation/plans/2/duties", body: { post_key: "2026-05-13|30|6-8", person_key: "STAFF:2", reason: "elle dolduruldu" } }]);
    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining("Arş. Gör. Fixture İki"));
  });

  it("shows a 409 with the server's sentence, its reason and the problems (on_duty, real answer)", async () => {
    const user = userEvent.setup();
    state.reply = () => {
      throw new HttpError(409, "409 Conflict", fx.refused_on_duty);
    };
    wrap(<ReassignDialog planId={2} target={{ post, duty: null }} onClose={() => undefined} />);
    const dlg = await screen.findByTestId("invig-reassign-dialog");
    await user.click(await within(dlg).findByRole("radio", { name: /Fixture İki/ }));
    await user.click(within(dlg).getByTestId("invig-reassign-ok"));
    const err = await within(dlg).findByTestId("invig-reassign-error");
    expect(within(err).getByTestId("invig-refusal")).toHaveAttribute("data-reason", "on_duty");
    expect(err).toHaveTextContent("Bu kişi bu göreve atanamaz: bir sert kural bozulur");
    expect(within(err).getByTestId("invig-refusal-reason")).toHaveTextContent("Neden: aynı saatte başka bir salonda görevli");
    expect(err).toHaveTextContent("STAFF:2: 2026-06-01|10|9-9 and 2026-06-01|11|9-9 at once");
  });

  it("reads post_full in English with its reason text", async () => {
    const user = userEvent.setup();
    state.reply = () => {
      throw new HttpError(409, "409 Conflict", fx.refused_post_full);
    };
    wrap(<ReassignDialog planId={2} target={{ post, duty: null }} onClose={() => undefined} />, "en");
    const dlg = await screen.findByTestId("invig-reassign-dialog");
    await user.click(await within(dlg).findByRole("radio", { name: /Fixture İki/ }));
    await user.click(within(dlg).getByTestId("invig-reassign-ok"));
    const err = await within(dlg).findByTestId("invig-reassign-error");
    expect(err).toHaveTextContent("This room session already has the 1 invigilator(s) it needs");
    expect(err).toHaveTextContent("Reason: fully staffed");
  });

  it("shows everyone who cannot take the post as a disabled row with the reason (nobody free: open by itself)", async () => {
    state.candidates = fx.candidates_busy;
    wrap(<ReassignDialog planId={2} target={{ post, duty: null }} onClose={() => undefined} />);
    const dlg = await screen.findByTestId("invig-reassign-dialog");
    expect(await within(dlg).findByTestId("invig-cand-none")).toHaveTextContent("Bu saatte uygun kimse yok.");
    const rows = within(dlg).getAllByTestId("invig-cand-off");
    expect(rows).toHaveLength((fx.candidates_busy as Candidates).unavailable.length);
    for (const r of rows) {
      expect(r).toHaveAttribute("data-reason", "on_duty");
      expect(within(r).getByRole("radio")).toBeDisabled();
      expect(within(r).getByRole("radio")).toHaveAccessibleDescription("aynı saatte başka bir salonda görevli");
    }
    expect(dlg.querySelector("details")).toHaveAttribute("open");
  });
});

describe("plan progress", () => {
  const brief = fx.brief_before as unknown as PlanBrief;
  it("shows the backend's phase and percentage as a determinate bar", () => {
    wrap(<RunningPanel p={{ ...brief, status: "RUNNING", progress: { phase: "loading", pct: 10 } }} elapsed={1} />);
    expect(screen.getByTestId("invig-phase")).toHaveTextContent("Sınavlar ve havuz yükleniyor");
    const bar = screen.getByTestId("invig-progress");
    expect(bar).toHaveRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "10");
    expect(screen.queryByTestId("invig-solve-time")).toBeNull();
  });
  it("while solving the percentage stays at 30 and the elapsed time against the limit moves", () => {
    wrap(<RunningPanel p={{ ...brief, status: "RUNNING", progress: { phase: "solving", pct: 30 } }} elapsed={2} />);
    expect(screen.getByTestId("invig-phase")).toHaveTextContent("Çözülüyor");
    expect(screen.getByTestId("invig-progress")).toHaveAttribute("aria-valuenow", "30");
    const time = screen.getByTestId("invig-solve-time");
    expect(time).toHaveRole("progressbar");
    expect(time).toHaveAttribute("aria-valuenow", "2");
    expect(time).toHaveAttribute("aria-valuemax", "3");
    expect(screen.getByTestId("invig-solve-time")).toHaveTextContent("2 / 3 sn");
  });
  it("invents no number when the job has not reported one", () => {
    wrap(<RunningPanel p={{ ...brief, status: "QUEUED", progress: null }} elapsed={0} />, "en");
    expect(screen.getByTestId("invig-phase")).toHaveTextContent("Waiting in the queue");
    expect(screen.queryByRole("progressbar")).toBeNull();
  });
});

describe("resolved shortages", () => {
  it("keep their entry, marked resolved, in a group after the open ones", () => {
    const resolved = fx.diagnosis_resolved as unknown as Diagnosis;
    const open: Diagnosis = { ...resolved, resolved: false, post_keys: ["2026-06-01|11|9-9"] };
    wrap(<DiagnosisList items={[resolved, open]} onPost={() => undefined} />);
    const groups = screen.getAllByTestId("invig-diag-group");
    expect(groups.map((g) => g.getAttribute("data-resolved"))).toEqual([null, "true"]);
    expect(groups[1]).toHaveTextContent("Uygun kişi yetmiyor: giderildi");
    expect(screen.getByTestId("invig-diagnosis")).toHaveTextContent("1 hata, 0 uyarı · 1 giderildi");
  });
});
