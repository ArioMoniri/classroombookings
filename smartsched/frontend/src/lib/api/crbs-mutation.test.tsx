import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { useCrbsMutation } from "./crbs";

/**
 * e2e-stabilisation 2026-10-16: Admin › Rooms opened with ?new=1 creates a room while the room list is still on its
 * first load. The invalidation must not be absorbed into that in-flight fetch (it began before the write).
 */
describe("useCrbsMutation", () => {
  it("refetches a list whose first load was in flight during the write", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
    const server = { rooms: ["A 101"] };
    let release: (() => void) | null = null;
    let calls = 0;
    const fetchRooms = () => {
      calls += 1;
      const snapshot = [...server.rooms]; // the read happens now, before the write
      if (calls === 1) return new Promise<string[]>((resolve) => (release = () => resolve(snapshot)));
      return Promise.resolve(snapshot);
    };
    const { result } = renderHook(
      () => ({
        list: useQuery({ queryKey: ["crbs", "admin-rooms"], queryFn: fetchRooms }),
        create: useCrbsMutation(async (code: string) => {
          server.rooms.push(code);
          return code;
        }, [["crbs", "admin-rooms"]]),
      }),
      { wrapper },
    );
    await waitFor(() => expect(calls).toBe(1));
    await act(async () => {
      const done = result.current.create.mutateAsync("Z 757");
      // the stale first answer lands only after the mutation's invalidation has started
      setTimeout(() => release?.(), 50);
      await done;
      await new Promise((r) => setTimeout(r, 100));
    });
    await waitFor(() => expect(result.current.list.data).toEqual(["A 101", "Z 757"]));
  });
});
