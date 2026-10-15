import { describe, expect, it } from "vitest";
import { harmonised } from "./harmonise";

// a stand-in for the i18n t(): plain {name} interpolation
const tpl: Record<string, string> = { atTime: "{day} {time}'de", ghost: "Run #{run}'de", plain: "{n} sınıf" };
const t = (key: string, vars: Record<string, string | number> = {}) => tpl[key].replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? `{${k}}`));

describe("harmonised (Turkish suffix after a placeholder)", () => {
  it("re-harmonises the suffix written after a value", () => {
    expect(harmonised(t, "tr", "atTime", { day: "Pazartesi", time: "09:00" })).toBe("Pazartesi 09:00'da");
    expect(harmonised(t, "tr", "atTime", { day: "Salı", time: "14:20" })).toBe("Salı 14:20'de");
    expect(harmonised(t, "tr", "ghost", { run: 6 })).toBe("Run #6'da");
    expect(harmonised(t, "tr", "ghost", { run: 12 })).toBe("Run #12'de");
  });
  it("leaves other templates and other languages alone", () => {
    expect(harmonised(t, "tr", "plain", { n: 4 })).toBe("4 sınıf");
    expect(harmonised(t, "en", "ghost", { run: 6 })).toBe("Run #6'de");
  });
});
