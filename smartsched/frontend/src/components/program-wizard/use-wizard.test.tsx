/**
 * useWizard autosave (backend PATCH /program-drafts/{id}): a flush that arrives while another save is on the wire
 * (the commit or "Devam" right after an edit) waits for it and then sends the rest; it used to answer `false` and
 * the commit showed "Taslak kaydedilemedi; hiçbir şey yazılmadı".
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DraftOut, Validation, draftsApi, type PatchOut } from "@/lib/api/program-drafts";
import { newPayload } from "./wizard-model";
import { usePendingStore, useWizard } from "./use-wizard";

const validation = (version: number) => Validation.parse({ draft_id: 7, version, can_commit: false, counts: {}, summary: {} });

function initial(): DraftOut {
  // the server already holds the full default payload, so mounting does not save
  return DraftOut.parse({ id: 7, term_id: 3, version: 1, status: "draft", step: "program", summary: {}, payload: newPayload(), validation: validation(1) });
}

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>;

describe("useWizard flush", () => {
  beforeEach(() => usePendingStore.setState({ byId: {} }));
  afterEach(() => vi.restoreAllMocks());

  it("waits for the in-flight save instead of failing, then sends the newer edit", async () => {
    const first = deferred<PatchOut>();
    const patch = vi
      .spyOn(draftsApi, "patch")
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(async (_id, body) => ({ id: 7, version: (body.base_version ?? 0) + 1, overwritten: [], validation: validation(3) }));
    const { result } = renderHook(() => useWizard(7, initial()), { wrapper });

    act(() => result.current.update((p) => ({ ...p, program: { ...p.program, prefix: "MBG" } })));
    let a!: Promise<boolean>;
    act(() => {
      a = result.current.flush();
    });
    // a second edit and a forced flush (the commit) while the first PATCH is still pending
    act(() => result.current.update((p) => ({ ...p, program: { ...p.program, name: "Moleküler Biyoloji ve Genetik Tezli YL" } })));
    let b!: Promise<boolean>;
    act(() => {
      b = result.current.flush();
    });
    await act(async () => {
      first.resolve({ id: 7, version: 2, overwritten: [], validation: validation(2) });
      await a;
    });
    await expect(b).resolves.toBe(true);

    expect(patch).toHaveBeenCalledTimes(2);
    expect(patch.mock.calls[0]![1].base_version).toBe(1);
    expect(patch.mock.calls[1]![1].base_version).toBe(2);
    expect(JSON.stringify(patch.mock.calls[1]![1].ops)).toContain("Moleküler Biyoloji");
    expect(result.current.save.kind).toBe("saved");
    expect(result.current.draft.version).toBe(3);
  });

  it("answers false when the save on the wire fails", async () => {
    const first = deferred<PatchOut>();
    vi.spyOn(draftsApi, "patch").mockImplementationOnce(() => first.promise.then(() => Promise.reject(new Error("boom"))));
    const { result } = renderHook(() => useWizard(7, initial()), { wrapper });
    act(() => result.current.update((p) => ({ ...p, program: { ...p.program, prefix: "MBG" } })));
    let a!: Promise<boolean>;
    let b!: Promise<boolean>;
    act(() => {
      a = result.current.flush();
      b = result.current.flush();
    });
    await act(async () => {
      first.resolve({ id: 7, version: 2, overwritten: [], validation: validation(2) });
      await a;
    });
    await expect(b).resolves.toBe(false);
    expect(result.current.save).toMatchObject({ kind: "error", message: "boom" });
  });
});
