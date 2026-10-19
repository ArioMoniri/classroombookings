/**
 * CH12-F04 (FIX-G): a plain Turkish / English line for the error classes the ops inbox sees most (SQLAlchemy and
 * network errors). The raw class, message and SQL move behind "Ayrıntı"; an unknown class keeps its own name.
 */
export type PlainErrorKey = "dbLocked" | "db" | "rollback" | "integrity" | "timeout" | "connection" | "server";

export function plainErrorKey(kind: string | null | undefined, message: string | null | undefined): PlainErrorKey | null {
  const k = (kind ?? "").split(".").pop() ?? "";
  const m = (message ?? "").toLowerCase();
  if (k === "OperationalError") return m.includes("database is locked") ? "dbLocked" : "db";
  if (k === "PendingRollbackError" || k === "InvalidRequestError" && m.includes("rollback")) return "rollback";
  if (k === "IntegrityError" || k === "UniqueViolation" || k === "ForeignKeyViolation") return "integrity";
  if (k === "TimeoutError" || k === "QueuePoolTimeout" || k === "ReadTimeout" || k === "ConnectTimeout") return "timeout";
  if (k === "ConnectionError" || k === "ConnectionRefusedError" || k === "ConnectError" || k === "InterfaceError") return "connection";
  // a server group without an exception class is keyed by its answer ("http_503"): never show that key raw
  if (/^http_5\d\d$/.test(k)) return "server";
  return null;
}
