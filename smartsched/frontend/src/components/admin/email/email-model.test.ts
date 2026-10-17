/** W3-MAIL: presets fill and lock the connection, only changed fields are saved, secrets never go back masked. */
import { describe, expect, it } from "vitest";
import type { MailSettings, Preset } from "./api";
import { changes, cleanSecret, dnsTone, domainOf, leavesPreset, presetFill, stepDone, stepsText } from "./email-model";

const ms365: Preset = {
  id: "microsoft365_oauth2",
  label: "Microsoft 365 / Exchange Online (OAuth2)",
  host: "smtp.office365.com",
  port: 587,
  security: "starttls",
  auth_mode: "xoauth2",
  username_hint_tr: "",
  username_hint_en: "",
  password_label_tr: "Parola",
  password_label_en: "Password",
  oauth_provider: "microsoft",
  console_url: "https://entra.microsoft.com/",
  hosts: ["smtp.office365.com"],
  steps: [{ tr: "API izinleri: SMTP.SendAsApp", en: "API permissions: SMTP.SendAsApp", copy: "SMTP.SendAsApp" }],
  notes_tr: "",
  notes_en: "",
  extra: {},
  abroad: false,
};
const sendgrid: Preset = { ...ms365, id: "sendgrid", host: "smtp.sendgrid.net", auth_mode: "password", oauth_provider: "", extra: { username: "apikey" }, abroad: true };

const stored = {
  provider: "custom",
  host: "smtp.uni.edu.tr",
  port: 587,
  security: "starttls",
  auth_mode: "password",
  username: "bildirim",
  password: { set: true, masked: "smtp********izli" },
  from_address: "bildirim@uni.edu.tr",
  configured: true,
  status: "connected",
  unsent: 0,
} as unknown as MailSettings;

describe("presets", () => {
  it("fill host, port, TLS, sign-in and the OAuth provider", () => {
    expect(presetFill(ms365)).toEqual({ provider: "microsoft365_oauth2", host: "smtp.office365.com", port: 587, security: "starttls", auth_mode: "xoauth2", oauth_provider: "microsoft" });
    expect(presetFill(sendgrid).username).toBe("apikey");
  });
  it("tell when the admin leaves the preset", () => {
    expect(leavesPreset(ms365, { host: "smtp.office365.com", port: 587, security: "starttls" })).toBe(false);
    expect(leavesPreset(ms365, { host: "smtp.office365.com", port: 25 })).toBe(true);
    expect(leavesPreset(undefined, { port: 25 })).toBe(false);
  });
  it("copy the console steps for IT as numbered lines in the reader's language", () => {
    expect(stepsText(ms365, "tr")).toBe("1. API izinleri: SMTP.SendAsApp\n   SMTP.SendAsApp");
  });
});

describe("saving", () => {
  it("sends only the changed fields and never a masked secret", () => {
    expect(changes(stored, { host: "smtp.uni.edu.tr", from_name: "Planlama" })).toEqual({ from_name: "Planlama" });
    expect(changes(stored, { password: null })).toEqual({});
    expect(changes(stored, { password: "yeni-gizli" })).toEqual({ password: "yeni-gizli" });
    expect(changes(stored, { abroad_ack: false })).toEqual({});
    expect(changes(stored, { abroad_ack: true })).toEqual({ abroad_ack: true });
  });
  it("cleans pasted secrets (NBSP, quotes, spaces) and says so", () => {
    expect(cleanSecret(" abcd efgh ijkl mnop ")).toEqual({ value: "abcd efgh ijkl mnop", trimmed: true });
    expect(cleanSecret('"SG.key"')).toEqual({ value: "SG.key", trimmed: true });
    expect(cleanSecret("plain")).toEqual({ value: "plain", trimmed: false });
  });
});

describe("steps and DNS", () => {
  it("marks the steps that are done", () => {
    expect(stepDone("provider", stored)).toBe(true);
    expect(stepDone("domain", stored)).toBe(false);
    expect(stepDone("domain", stored, { dnsChecked: true })).toBe(true);
    expect(stepDone("enable", stored)).toBe(true);
  });
  it("reads the from-domain with Turkish İ folded and maps DNS verdicts to tones", () => {
    expect(domainOf("Bildirim@ÜNİVERSİTE.edu.tr")).toBe("üniversite.edu.tr");
    expect([dnsTone("ok"), dnsTone("warn"), dnsTone("error"), dnsTone("unknown")]).toEqual(["success", "warning", "error", "neutral"]);
  });
});
