/**
 * WG-09: the welcome guide's motion budget (welcome-guide.md §8; ticket: calm, ≤ 240 ms for UI, off under reduced
 * motion). Every transition in `welcomeMotion` ends within 240 ms, delays included; exits are faster than entrances;
 * the reduced replacement is a ≤ 100 ms fade. A source guard keeps the welcome components on this module: no shared
 * springs (they settle in 270–285 ms), no raw durations, and every animating file reads the reduced-motion setting.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import type { Transition } from "motion/react";
import { describe, expect, it } from "vitest";
import { WELCOME_MAX_S, WELCOME_SHEET_SETTLE_MS, WELCOME_STAGGER_ITEMS, welcomeMotion } from "./motion";

const end = (t: Transition) => ((t as { delay?: number }).delay ?? 0) + ((t as { duration?: number }).duration ?? 0);

describe("welcome motion budget", () => {
  it("every one-shot transition ends within 240 ms, delays included", () => {
    expect(WELCOME_MAX_S).toBe(0.24);
    for (const [name, t] of Object.entries(welcomeMotion)) {
      if (typeof t === "function") {
        for (let i = 0; i < 12; i++) expect(end(t(i)), `${name}(${i})`).toBeLessThanOrEqual(WELCOME_MAX_S + 1e-9);
      } else {
        expect(end(t), name).toBeLessThanOrEqual(WELCOME_MAX_S + 1e-9);
        expect((t as { type?: string }).type, `${name} is a tween`).not.toBe("spring");
      }
    }
  });

  it("the card stagger caps at 5 items, 30 ms apart, and the 5th card ends exactly at the ceiling", () => {
    expect(WELCOME_STAGGER_ITEMS).toBe(5);
    expect((welcomeMotion.cardReveal(1) as { delay: number }).delay).toBeCloseTo(0.03);
    expect(end(welcomeMotion.cardReveal(4))).toBeCloseTo(0.24);
    expect(end(welcomeMotion.cardReveal(9))).toBeCloseTo(0.24);
  });

  it("exits are faster than entrances; the reduced replacement is an opacity fade ≤ 100 ms", () => {
    expect(end(welcomeMotion.pageExit)).toBeLessThan(end(welcomeMotion.pageEnter));
    expect(end(welcomeMotion.reduced)).toBeLessThanOrEqual(0.1);
  });

  it("the hero waits for the sheet to settle (240 ms)", () => {
    expect(WELCOME_SHEET_SETTLE_MS).toBe(240);
  });
});

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) return files(p);
    return /\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f) && f !== "test-helpers.tsx" && f !== "motion.ts" ? [p] : [];
  });
}

describe("welcome components use the welcome motion module", () => {
  const dir = __dirname;
  const sources = files(dir).map((p) => ({ rel: relative(dir, p), src: readFileSync(p, "utf8") }));

  it("no shared springs and no raw durations in welcome components", () => {
    for (const { rel, src } of sources) {
      expect(src, rel).not.toMatch(/\bsprings\.\w+/);
      expect(src, rel).not.toMatch(/duration:\s*(?!0\b)[0-9.]+/);
      expect(src, rel).not.toMatch(/\b\d+ms\b/);
    }
  });

  it("every file that animates with motion also reads the reduced-motion setting", () => {
    for (const { rel, src } of sources) {
      if (!/from "motion\/react"/.test(src) || !/<motion\.|<AnimatePresence/.test(src)) continue;
      expect(/useReduce\(\)|reduceMotion/.test(src), rel).toBe(true);
    }
  });
});
