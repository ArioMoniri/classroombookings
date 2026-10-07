"use client";

import { Button } from "@/components/ui/button";

export default function SegmentError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div role="alert" className="mx-auto mt-10 max-w-md rounded-xl border bg-card p-6 text-center">
      <p className="text-lg font-semibold">Something went wrong</p>
      <p className="mt-1 text-sm text-muted-foreground">{error.message}</p>
      {error.digest ? <p className="mt-1 font-mono text-xs text-muted-foreground">Error id {error.digest}</p> : null}
      <Button className="mt-4" onClick={reset}>Retry</Button>
    </div>
  );
}
