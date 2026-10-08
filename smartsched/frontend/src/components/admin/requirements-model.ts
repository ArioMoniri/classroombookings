/**
 * Installer requirements (`GET /org/setup/requirements`, CRBS `Install::check_requirements`): every check is
 * `ok`, `warn` or `err`; any `err` blocks `POST /org/setup` (409). Keys are stable; the order is the backend's.
 */
import type { RequirementStatus, SetupRequirements } from "@/lib/api/crbs";
import type { MessageKey } from "@/lib/i18n";

export interface RequirementRow {
  key: string;
  status: RequirementStatus;
  message: string;
  /** label key when the frontend knows the check; unknown keys show the raw key */
  labelKey: MessageKey | null;
}

const LABELS: Record<string, MessageKey> = {
  python_version: "crbs.setup.req.check.python_version",
  image_library: "crbs.setup.req.check.image_library",
  ldap_module: "crbs.setup.req.check.ldap_module",
  folder_uploads: "crbs.setup.req.check.folder_uploads",
  database: "crbs.setup.req.check.database",
  database_schema: "crbs.setup.req.check.database_schema",
  secrets: "crbs.setup.req.check.secrets",
  smtp: "crbs.setup.req.check.smtp",
};

export function requirementRows(data: SetupRequirements | undefined | null): RequirementRow[] {
  if (!data) return [];
  return Object.entries(data.requirements).map(([key, v]) => ({ key, status: v.status, message: v.message, labelKey: LABELS[key] ?? null }));
}

export interface RequirementSummary {
  blocking: RequirementRow[];
  warnings: RequirementRow[];
  /** setup may continue: the backend's `ok`, or no `err` row when it is missing */
  ok: boolean;
}

export function summariseRequirements(data: SetupRequirements | undefined | null): RequirementSummary {
  const rows = requirementRows(data);
  const blocking = rows.filter((r) => r.status === "err");
  return { blocking, warnings: rows.filter((r) => r.status === "warn"), ok: !!data && (data.ok ?? true) && blocking.length === 0 };
}

/** `POST /org/setup` → 409 "requirements not met: a, b (GET …)": the keys it names, if any. */
export function blockedKeysFromError(message: string | null | undefined): string[] {
  const m = /requirements not met:\s*([^()]+?)\s*(\(|$)/.exec(message ?? "");
  return m ? m[1]!.split(",").map((s) => s.trim()).filter(Boolean) : [];
}
