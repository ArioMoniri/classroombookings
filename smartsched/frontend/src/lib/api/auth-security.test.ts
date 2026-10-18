// AUX-01: the auth-security client against AU-B's contract (app/api/v1/mfa.py, app/services/mfa.py). The paths
// are checked against the generated OpenAPI subset (__fixtures__/au-b-openapi.json); the shapes against answers
// copied from the service's return statements.
import { describe, expect, it } from "vitest";
import spec from "./__fixtures__/au-b-openapi.json";
import { AdminMfa, AUTH_SECURITY_PATHS, MfaPolicy, MfaStatus, PasskeyRow, SignInStepOut, TotpStart, utcDate, maskIdentifier, normalizeRecoveryCode, mfaErrorCode } from "./auth-security";
import { HttpError } from "./client";

const STATUS = {
  available: true,
  reason: null,
  account_type: "local",
  policy: { mfa_policy: "optional", mfa_roles: ["ADMIN"], mfa_grace_days: 14, passkeys_enabled: true, passkey_first_factor: true },
  passkeys_available: true,
  required: false,
  grace_until: null,
  totp: { enabled: true, enabled_at: "2026-10-18T09:00:00" },
  recovery_codes: { remaining: 9, total: 10 },
  passkeys: [{ id: 3, name: "iCloud Anahtar Zinciri", transports: ["internal", "hybrid"], backed_up: true, created_at: "2026-10-18T09:10:00", last_used_at: null }],
  trusted_devices: [{ id: 1, label: "Chrome · macOS", created_at: "2026-10-18T09:00:00", expires_at: "2026-11-17T09:00:00", last_used_at: null }],
  locked_until: null,
};

describe("AU-B contract", () => {
  it("every path the client calls exists in the backend's OpenAPI", () => {
    const paths = (spec as { paths: Record<string, string[]> }).paths;
    for (const [method, path] of AUTH_SECURITY_PATHS) {
      const key = `/api/v1${path}`;
      expect(paths[key], key).toBeDefined();
      expect(paths[key]).toContain(method);
    }
  });

  it("the request bodies match the backend's pydantic models", () => {
    const schemas = (spec as { schemas: Record<string, { properties: Record<string, unknown>; required?: string[] }> }).schemas;
    expect(Object.keys(schemas.VerifyIn.properties).sort()).toEqual(["challenge_token", "code", "method", "trust_device"]);
    expect(Object.keys(schemas.AdminResetIn.properties).sort()).toEqual(["identity_check", "keep_passkeys", "reason"]);
    expect(Object.keys(schemas.app__schemas__mfa__PolicyIn.properties).sort()).toEqual(["mfa_grace_days", "mfa_policy", "mfa_roles", "passkey_first_factor", "passkeys_enabled", "trusted_device_days"]);
    expect(Object.keys(schemas.TokenOut.properties)).toEqual(expect.arrayContaining(["mfa_required", "mfa_methods", "challenge_token", "mfa_setup_required", "mfa_grace_until"]));
  });

  it("parses GET /auth/mfa", () => {
    const s = MfaStatus.parse(STATUS);
    expect(s.totp.enabled).toBe(true);
    expect(s.passkeys[0].name).toBe("iCloud Anahtar Zinciri");
    expect(s.trusted_devices).toHaveLength(1);
    expect(MfaStatus.parse({ ...STATUS, available: false, reason: "sso_account", account_type: "sso" }).reason).toBe("sso_account");
  });

  it("parses the TOTP start, a passkey row, the policy and the admin summary", () => {
    expect(TotpStart.parse({ secret: "A".repeat(32), otpauth_uri: "otpauth://totp/x", issuer: "Uni", account: "ayse", digits: 6, period: 30, algorithm: "SHA1", expires_in: 900 }).expires_in).toBe(900);
    expect(PasskeyRow.parse({ ...STATUS.passkeys[0], aaguid: "fbfc3007-154e-4ecc-8c0b-6e020557d7bd" }).aaguid).toBe("fbfc3007-154e-4ecc-8c0b-6e020557d7bd");
    expect(MfaPolicy.parse(STATUS.policy).mfa_grace_days).toBe(14);
    const admin = AdminMfa.parse({ user_id: 4, account_type: "local", totp_enabled: true, totp_enabled_at: null, recovery_codes_remaining: 10, passkeys: [{ name: "x", created_at: "2026-10-18T09:00:00", last_used_at: null }], trusted_devices: 0, locked_until: null, can_reset_mfa: true, can_send_reset_link: true });
    expect(admin.can_reset_mfa).toBe(true);
  });

  it("parses the route handler's step answers", () => {
    expect(SignInStepOut.parse({ status: "mfa", methods: ["totp", "passkey"], masked: "ay•••@ornek.edu.tr" }).status).toBe("mfa");
    expect(SignInStepOut.parse({ status: "signed_in", user: { id: 1 }, recovery_codes_remaining: 2 }).recovery_codes_remaining).toBe(2);
  });
});

describe("helpers", () => {
  it("reads the backend's naive UTC datetimes as UTC", () => {
    expect(utcDate("2026-10-18T09:00:00")?.toISOString()).toBe("2026-10-18T09:00:00.000Z");
    expect(utcDate("2026-10-18T09:00:00+03:00")?.toISOString()).toBe("2026-10-18T06:00:00.000Z");
    expect(utcDate(null)).toBeNull();
  });
  it("masks the identifier for the account line (§5.1)", () => {
    expect(maskIdentifier("ayse.yilmaz@ornek.edu.tr")).toBe("ay•••@ornek.edu.tr");
    expect(maskIdentifier("fatih")).toBe("fa•••");
    expect(maskIdentifier("a@b.c")).toBe("a•••@b.c");
  });
  it("normalises a recovery code: case, spaces, hyphens, O→0, I/L→1 (§5.3)", () => {
    expect(normalizeRecoveryCode(" abcd efgh-ijkl mnop ")).toBe("ABCD-EFGH-1JK1-MN0P");
    expect(normalizeRecoveryCode("abc")).toBe("ABC");
    expect(normalizeRecoveryCode("ABCDEFGHJKMNPQRSTV")).toBe("ABCD-EFGH-JKMN-PQRS");
  });
  it("reads the refusal code of a problem detail", () => {
    expect(mfaErrorCode(new HttpError(409, "x", { detail: { code: "sso_account", message_tr: "…" } }))).toBe("sso_account");
    expect(mfaErrorCode(new HttpError(409, "x", { code: "no_email" }))).toBe("no_email");
    expect(mfaErrorCode(new Error("x"))).toBeNull();
  });
});
