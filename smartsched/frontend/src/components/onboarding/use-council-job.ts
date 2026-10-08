"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ACTIVE_JOB, CouncilJob, councilApi } from "@/lib/api/council";

export const councilKey = (id: number) => ["council", id] as const;

/**
 * Live council job: server-sent `snapshot` events (GET /council/jobs/{id}/events) update the cache;
 * when EventSource is unavailable or the stream fails, the query polls every 1.5 s while the job runs.
 */
export function useCouncilJob(id: number | null) {
  const qc = useQueryClient();
  const [streaming, setStreaming] = useState(false);

  const query = useQuery({
    queryKey: councilKey(id ?? 0),
    queryFn: () => councilApi.get(id ?? 0),
    enabled: id !== null,
    refetchInterval: (q) => {
      const data = q.state.data;
      if (data && !ACTIVE_JOB.has(data.status)) return false;
      return streaming ? false : 1500;
    },
  });

  useEffect(() => {
    if (id === null || typeof EventSource === "undefined") return;
    const es = new EventSource(councilApi.eventsUrl(id));
    es.onopen = () => setStreaming(true);
    es.addEventListener("snapshot", (e) => {
      try {
        const parsed = CouncilJob.safeParse(JSON.parse((e as MessageEvent<string>).data));
        if (parsed.success) qc.setQueryData(councilKey(id), parsed.data);
      } catch {
        /* a malformed event is ignored; polling covers it */
      }
    });
    es.addEventListener("done", () => {
      es.close();
      setStreaming(false);
      void qc.invalidateQueries({ queryKey: councilKey(id) });
    });
    es.onerror = () => {
      es.close();
      setStreaming(false);
    };
    return () => {
      es.close();
      setStreaming(false);
    };
  }, [id, qc]);

  return query;
}
