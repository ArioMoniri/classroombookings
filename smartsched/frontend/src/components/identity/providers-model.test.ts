import { describe, expect, it } from "vitest";
import { buttonLayout, cleanPasted, copyAllText, looksLikeGuid, missingFields, parseDomains, stepState, WIZARD_STEPS, type ButtonLike } from "./providers-model";

const base = {
  kind: "oidc" as const,
  configured: false,
  enabled: false,
  client_id: null as string | null,
  client_secret_set: false,
  issuer: null as string | null,
  tenant_id: null as string | null,
  hosted_domains: [] as string[],
  discovery: { ok: null as boolean | null },
  saml: null as {
    idp_entity_id?: string | null;
    certificates?: number;
  } | null,
  test_ok: null as boolean | null,
  library_required: false,
};

describe("guided setup steps (design v3 §5)", () => {
  it("has the five steps in order", () => {
    expect(WIZARD_STEPS).toEqual(["preset", "console", "values", "test", "enable"]);
  });

  it("locks the console values without a public URL and the test until the client is usable", () => {
    const s = stepState(base, { publicUrl: null });
    expect(s.console).toBe("locked");
    expect(s.test).toBe("locked");
    const s2 = stepState(base, { publicUrl: "https://plan.uni.edu.tr" });
    expect(s2.console).toBe("open");
    expect(s2.values).toBe("open");
    expect(s2.test).toBe("locked");
  });

  it("unlocks Etkinleştir only after a configured client and a successful test login", () => {
    const configured = {
      ...base,
      configured: true,
      client_id: "x",
      client_secret_set: true,
      issuer: "https://i",
      discovery: { ok: true },
    };
    expect(stepState(configured, { publicUrl: "https://p" }).test).toBe("open");
    expect(stepState(configured, { publicUrl: "https://p" }).enable).toBe("locked");
    expect(stepState({ ...configured, test_ok: false }, { publicUrl: "https://p" }).enable).toBe("locked");
    expect(stepState({ ...configured, test_ok: true }, { publicUrl: "https://p" }).enable).toBe("open");
    expect(stepState({ ...configured, test_ok: true }, { publicUrl: "https://p" }).values).toBe("done");
  });

  it("names the missing values per kind", () => {
    expect(missingFields(base)).toEqual(["issuer", "client_id", "client_secret"]);
    expect(missingFields({ ...base, kind: "entra", tenant_id: "t" })).toEqual(["client_id", "client_secret"]);
    expect(
      missingFields({
        ...base,
        kind: "google_workspace",
        client_id: "c",
        client_secret_set: true,
      }),
    ).toEqual(["hosted_domains"]);
    expect(missingFields({ ...base, kind: "saml" })).toEqual(["metadata"]);
    expect(
      missingFields({
        ...base,
        kind: "saml",
        saml: { idp_entity_id: "e", certificates: 1 },
      }),
    ).toEqual([]);
  });
});

describe("sign-in buttons with several providers (design v3 §6)", () => {
  const p = (name: string): ButtonLike => ({
    name,
    kind: "oidc",
    label: name,
    start_url: `/api/v1/auth/sso/${name}/start`,
  });

  it("shows one provider alone, at most three equal buttons, the rest behind 'Diğer giriş yolları'", () => {
    expect(buttonLayout([p("a")], null)).toEqual({
      visible: [p("a")],
      more: [],
      single: true,
    });
    const four = [p("a"), p("b"), p("c"), p("d")];
    const l = buttonLayout(four, null);
    expect(l.visible.map((x) => x.name)).toEqual(["a", "b", "c"]);
    expect(l.more.map((x) => x.name)).toEqual(["d"]);
    expect(l.single).toBe(false);
  });

  it("an invite link shows only the invited method's button", () => {
    const l = buttonLayout([p("a"), p("b")], "b");
    expect(l.visible.map((x) => x.name)).toEqual(["b"]);
    expect(l.more).toEqual([]);
    expect(buttonLayout([p("a")], "local").visible).toEqual([]);
  });
});

describe("pasted values (Turkish text normalisation)", () => {
  it("trims spaces, NBSP, zero-width characters and quotes and says so", () => {
    expect(cleanPasted("  'abc~123' ​")).toEqual({
      value: "abc~123",
      trimmed: true,
    });
    expect(cleanPasted("abc")).toEqual({ value: "abc", trimmed: false });
  });

  it("warns when a GUID is pasted as a secret", () => {
    expect(looksLikeGuid("3f2a8c1e-5b7d-4e9a-a6c4-2d8e1f0b9c7a")).toBe(true);
    expect(looksLikeGuid("Q~8Q8~abc.DEF")).toBe(false);
  });

  it("reads domains separated by commas, semicolons or spaces, folding the dotted capital İ", () => {
    expect(parseDomains("UNİ.EDU.TR, @ogr.uni.edu.tr;  personel.uni.edu.tr ")).toEqual(["uni.edu.tr", "ogr.uni.edu.tr", "personel.uni.edu.tr"]);
    expect(parseDomains("")).toEqual([]);
  });

  it("copies every console value as 'Label: value' lines for an e-mail to IT", () => {
    const text = copyAllText(
      [
        {
          key: "redirect_uri",
          label_tr: "Yönlendirme adresi",
          label_en: "Redirect URI",
          value: "https://p/cb",
        },
        {
          key: "scopes",
          label_tr: "Kapsamlar",
          label_en: "Scopes",
          value: "openid profile email",
        },
      ],
      "tr",
    );
    expect(text).toBe("Yönlendirme adresi: https://p/cb\nKapsamlar: openid profile email");
  });
});
