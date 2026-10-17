"use client";

import { useEffect } from "react";
import { reportClientError } from "@/lib/api/ops";

/**
 * Last-resort boundary for errors in the root layout itself (W3-OPS): reported to /admin/ops, then a plain bilingual
 * page with a retry. No providers are available here (the root layout failed), so the text is inline, Turkish first.
 */
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    reportClientError({ message: error.message || error.name, kind: error.name, stack: error.stack, url: window.location.href, origin: "boundary" });
  }, [error]);
  return (
    <html lang="tr">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: 0, padding: "2.5rem 1rem", textAlign: "center" }}>
        <main role="alert" style={{ maxWidth: 420, margin: "0 auto" }}>
          <h1 style={{ fontSize: "1.25rem" }}>Bir hata oluştu · Something went wrong</h1>
          {error.digest ? <p style={{ fontFamily: "monospace", fontSize: "0.8rem" }}>{error.digest}</p> : null}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              reset();
            }}
          >
            <input type="submit" value="Yeniden dene · Retry" style={{ minHeight: 44, minWidth: 44, fontSize: 16, padding: "0 1rem", marginTop: "1rem" }} />
          </form>
        </main>
      </body>
    </html>
  );
}
