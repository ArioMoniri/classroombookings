/**
 * Server times (HB18-F01). The API sends UTC; some payloads still send it naive ("2026-10-18T13:11:22", the
 * backend's `utcnow` convention). `Date.parse` reads a naive ISO date-time as the browser's *local* time, so in
 * Europe/Istanbul every such time was 3 h off. Read server times only through this.
 */
const HAS_ZONE = /(?:[zZ]|[+-]\d\d:?\d\d)$/;

/** Epoch ms of a server ISO time, a naive one read as UTC; `NaN` for nothing or garbage. */
export function parseServerTime(iso: string | null | undefined): number {
  if (typeof iso !== "string" || !iso.trim()) return Number.NaN;
  const text = iso.trim();
  if (HAS_ZONE.test(text)) {
    // "+0300" is not ISO for every engine: write it as "+03:00"
    return Date.parse(text.replace(/([+-]\d\d)(\d\d)$/, "$1:$2"));
  }
  // a date-time with no zone is UTC; trim sub-millisecond digits ("…22.572159") for strict engines
  return Date.parse(`${text.replace(/(\.\d{3})\d+$/, "$1")}Z`);
}
