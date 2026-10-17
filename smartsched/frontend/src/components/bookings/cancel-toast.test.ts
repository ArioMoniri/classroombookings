import { describe, expect, it } from "vitest";
import { cancelToastText } from "./cancel-toast";
import tr from "../../../messages/tr.json";

const get = (obj: unknown, path: string) => path.split(".").reduce<unknown>((o, k) => (o as Record<string, unknown>)?.[k], obj) as string;
const t = (key: string, values: Record<string, string | number> = {}) => get(tr, key).replace(/\{(\w+)\}/g, (_, k: string) => String(values[k] ?? `{${k}}`));

describe("T-R2-16 cancel toast", () => {
  it("says N rezervasyon iptal edildi, singular only for one date, the reason when given, nothing about 0 kept", () => {
    expect(cancelToastText(t, 1)).toBe("1 rezervasyon iptal edildi");
    expect(cancelToastText(t, 4, { reason: "Dönem sonu" })).toBe("4 rezervasyon iptal edildi · Gerekçe: Dönem sonu");
    expect(cancelToastText(t, 1, { reason: "  Oda bakımda " })).toBe("1 rezervasyon iptal edildi · Gerekçe: Oda bakımda");
    expect(cancelToastText(t, 2, { skipped: 0 })).toBe("2 rezervasyon iptal edildi");
    expect(cancelToastText(t, 2, { skipped: 1, reason: null })).toBe("2 rezervasyon iptal edildi · 1 olduğu gibi kaldı");
  });
});
