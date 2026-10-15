/** Studio "Export draft as JSON" (advanced): the saved draft as a portable, versioned document. */
import type { Draft } from "@/lib/api/studio-schemas";

export function draftExport(draft: Draft, exportedAt: string = new Date().toISOString()) {
  return { schema: "smartsched.studio-draft/1" as const, exported_at: exportedAt, draft };
}

export function draftFileName(draft: Draft): string {
  return `smartsched-draft-term${draft.term_id}-${draft.kind.toLowerCase()}-v${draft.version}.json`;
}

export function downloadJson(name: string, data: unknown): void {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
