"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { reportClientError } from "@/lib/api/ops";
import { useI18n } from "@/lib/i18n/provider";

/** A page that threw: the reason and a retry, in the user's language (admin persona M-36: it was English). */
export default function SegmentError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const { t } = useI18n();
  // W3-OPS: a render error of any page becomes a grouped error event on /admin/ops
  useEffect(() => {
    reportClientError({ message: error.message || error.name, kind: error.name, stack: error.stack, url: window.location.href, origin: "boundary" });
  }, [error]);
  return (
    <div role="alert" className="mx-auto mt-10 max-w-md rounded-xl border bg-card p-6 text-center">
      <p className="text-lg font-semibold">{t("common.error")}</p>
      <p className="mt-1 text-sm text-muted-foreground">{error.message}</p>
      {error.digest ? <p className="mt-1 font-mono text-xs text-muted-foreground">{t("common.errorId")} {error.digest}</p> : null}
      <Button className="mt-4" onClick={reset}>
        {t("common.retry")}
      </Button>
    </div>
  );
}
