import { describe, expect, it } from "vitest";
import type { SetupRequirements } from "@/lib/api/crbs";
import { blockedKeysFromError, requirementRows, summariseRequirements } from "./requirements-model";

/* shape recorded from GET /org/setup/requirements on a dev backend (APP_SECRET default, no SMTP) */
const sample: SetupRequirements = {
  setup_required: true,
  ok: false,
  requirements: {
    python_version: { status: "ok", message: "Python 3.13.1" },
    image_library: { status: "ok", message: "" },
    ldap_module: { status: "warn", message: "The 'ldap3' package is only needed for LDAP authentication." },
    folder_uploads: { status: "ok", message: "" },
    database: { status: "ok", message: "" },
    database_schema: { status: "err", message: "Database schema is at 0004_review_fixes; run 'alembic upgrade head' (0005_crbs_legacy_ids)." },
    secrets: { status: "warn", message: "APP_SECRET is the development default; set your own before going live." },
    smtp: { status: "warn", message: "SMTP is not configured; e-mails are kept in the outbox until it is." },
    future_check: { status: "ok", message: "" },
  },
};

describe("installer requirements", () => {
  it("keeps the backend order and labels the known checks", () => {
    const rows = requirementRows(sample);
    expect(rows.map((r) => r.key)).toEqual(Object.keys(sample.requirements));
    expect(rows[0]!.labelKey).toBe("crbs.setup.req.check.python_version");
    expect(rows.at(-1)!.labelKey).toBeNull();
  });
  it("err blocks setup, warn does not", () => {
    const s = summariseRequirements(sample);
    expect(s.ok).toBe(false);
    expect(s.blocking.map((r) => r.key)).toEqual(["database_schema"]);
    expect(s.warnings).toHaveLength(3);
    const fixed = { ...sample, ok: true, requirements: { ...sample.requirements, database_schema: { status: "ok" as const, message: "" } } };
    expect(summariseRequirements(fixed)).toMatchObject({ ok: true, blocking: [] });
    expect(summariseRequirements(undefined).ok).toBe(false);
  });
  it("reads the blocking keys from the 409 of POST /org/setup", () => {
    expect(blockedKeysFromError("requirements not met: database_schema, secrets (GET /org/setup/requirements)")).toEqual(["database_schema", "secrets"]);
    expect(blockedKeysFromError("setup is already complete")).toEqual([]);
    expect(blockedKeysFromError(null)).toEqual([]);
  });
});
