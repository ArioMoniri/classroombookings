/** W3-OPS: panel helpers and the browser error reporter (scrub, 8 KB fit, dedupe, rate limit, listeners). */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fitReport, installErrorReporter, reportClientError, resetClientReporter, scrubClient } from "@/lib/api/ops";
import { chartGeometry, formatBytes, formatUptime, sameOrigin, totals } from "./ops-model";

describe("ops-model", () => {
  it("formats bytes and uptime per locale", () => {
    expect(formatBytes(1536, "tr-TR")).toBe("1,5 KB");
    expect(formatBytes(60 * 2 ** 30, "en-GB")).toBe("60 GB");
    expect(formatBytes(undefined, "tr-TR")).toBe("–");
    expect(formatUptime(93784, "tr")).toBe("1 g 2 sa");
    expect(formatUptime(3700, "en")).toBe("1 h 1 min");
    expect(formatUptime(120, "tr")).toBe("2 dk");
  });

  it("chart geometry: bars scaled to the busiest minute, p95 line skips empty minutes", () => {
    const g = chartGeometry([{ t: 0, requests: 10, errors: 5, p95_ms: 100 }, { t: 60, requests: 20, errors: 0, p95_ms: null }, { t: 120, requests: 0, errors: 0, p95_ms: 50 }], 300, 100);
    expect(g.bars.map((b) => b.h)).toEqual([50, 100, 0]);
    expect(g.bars[0].err).toBe(25);
    expect(g.line.split(" ")).toHaveLength(2);
    expect(totals([{ t: 0, requests: 10, errors: 5, p95_ms: 100 }, { t: 60, requests: 30, errors: 0, p95_ms: 300 }])).toEqual({ requests: 40, errors: 5, errorPct: 12.5, p95: 300 });
  });

  it("embeds only same-origin Grafana URLs", () => {
    expect(sameOrigin("/grafana/d-solo/x", "https://plan.uni.edu.tr")).toBe(true);
    expect(sameOrigin("https://evil.example/grafana", "https://plan.uni.edu.tr")).toBe(false);
  });
});

describe("browser error reporter", () => {
  const fetchMock = vi.fn(async () => new Response(null, { status: 202 }));
  beforeEach(() => {
    resetClientReporter();
    fetchMock.mockClear();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("scrubs e-mails, tokens and query strings before sending", () => {
    expect(scrubClient("ali@uni.edu.tr Bearer abcdefghijkl https://x.tr/rooms?q=Ahmet")).toBe("[email] Bearer [token] https://x.tr/rooms?[query]");
  });

  it("fits a report into 8 KB", () => {
    const r = fitReport({ message: "m".repeat(5000), stack: "s".repeat(20000), component_stack: "c".repeat(9000), origin: "boundary" });
    expect(new Blob([JSON.stringify(r)]).size).toBeLessThanOrEqual(8 * 1024);
    expect(r.message.length).toBe(1000);
  });

  it("deduplicates the same error for a minute and caps 10 reports a minute", () => {
    expect(reportClientError({ message: "boom", kind: "TypeError", origin: "window.onerror" }, 1000)).toBe(true);
    expect(reportClientError({ message: "boom", kind: "TypeError", origin: "window.onerror" }, 2000)).toBe(false);
    for (let i = 0; i < 12; i++) reportClientError({ message: `e${i}`, origin: "window.onerror" }, 3000 + i);
    expect(fetchMock).toHaveBeenCalledTimes(10);
    expect(reportClientError({ message: "boom", kind: "TypeError", origin: "window.onerror" }, 70_000)).toBe(true);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/ops/errors");
    expect(init.method).toBe("POST");
    expect(init.keepalive).toBe(true);
  });

  it("window error / unhandled rejection listeners report; resource and abort errors do not", () => {
    const uninstall = installErrorReporter(window);
    window.dispatchEvent(new ErrorEvent("error", { error: new TypeError("x is undefined"), message: "x is undefined" }));
    window.dispatchEvent(new ErrorEvent("error", {})); // an <img> that failed to load
    const rejection = new Event("unhandledrejection") as PromiseRejectionEvent;
    Object.defineProperty(rejection, "reason", { value: new Error("late failure") });
    window.dispatchEvent(rejection);
    const abort = new Event("unhandledrejection") as PromiseRejectionEvent;
    Object.defineProperty(abort, "reason", { value: new DOMException("aborted", "AbortError") });
    window.dispatchEvent(abort);
    uninstall();
    window.dispatchEvent(new ErrorEvent("error", { message: "after uninstall" }));
    const bodies = fetchMock.mock.calls.map((c) => JSON.parse(String((c as unknown as [string, RequestInit])[1].body)) as { origin: string; kind: string });
    expect(bodies.map((b) => b.origin)).toEqual(["window.onerror", "unhandledrejection"]);
    expect(bodies[0].kind).toBe("TypeError");
  });
});
