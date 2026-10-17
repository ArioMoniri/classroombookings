/**
 * Runs in the browser before the app becomes interactive (Next.js `instrumentation-client`): uncaught errors and
 * unhandled promise rejections are reported to `POST /api/v1/ops/errors` (W3-OPS: grouped, PII-scrubbed error events
 * on /admin/ops; deduplicated and rate limited in the tab and on the server). Render errors caught by an error
 * boundary are reported by `app/(app)/error.tsx` and `app/global-error.tsx`.
 */
import { installErrorReporter } from "@/lib/api/ops";

try {
  installErrorReporter(window);
} catch {
  /* monitoring must never break the app */
}
