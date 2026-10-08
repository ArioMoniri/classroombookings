#!/usr/bin/env python3
"""Simulate damped springs and print timing + a CSS linear() easing.

Use it before adding or changing a spring token: every preset must reach 95 %
of its target in <= 220 ms and settle within 1 % in <= 300 ms (tokens.md §6
ceiling). Pure stdlib, deterministic.

  python3 -I spring_table.py                   # print the SmartSched presets
  python3 -I spring_table.py 400 30 0.85       # one custom spring (stiffness damping mass)
"""
from __future__ import annotations

import math
import sys

PRESETS: dict[str, tuple[float, float, float]] = {
    "snappy": (520, 42, 0.8),
    "smooth": (380, 36, 1.0),
    "bouncy-subtle": (420, 28, 0.8),
    "sheet": (300, 30, 1.0),
    "glass-morph": (400, 30, 0.85),
    "ticker": (420, 38, 1.0),
    "pointer (useSpring)": (700, 34, 0.5),
}


def simulate(k: float, c: float, m: float, dt: float = 1 / 4000, horizon: float = 1.5):
    """Semi-implicit Euler from 0 to 1 at rest. Returns samples and metrics."""
    x = v = t = 0.0
    samples: list[tuple[float, float]] = []
    t95 = None
    settle = 0.0
    peak = 0.0
    while t < horizon:
        a = (-k * (x - 1) - c * v) / m
        v += a * dt
        x += v * dt
        t += dt
        samples.append((t, x))
        peak = max(peak, x)
        if t95 is None and x >= 0.95:
            t95 = t
        if abs(x - 1) > 0.01:
            settle = t
    zeta = c / (2 * math.sqrt(k * m))
    return samples, zeta, t95 or horizon, settle, max(0.0, peak - 1) * 100


def linear_easing(samples: list[tuple[float, float]], duration: float, stops: int = 14) -> str:
    vals = []
    j = 0
    for i in range(stops + 1):
        target = duration * i / stops
        while j < len(samples) - 1 and samples[j][0] < target:
            j += 1
        vals.append(0.0 if i == 0 else samples[j][1])
    vals[-1] = 1.0
    return "linear(" + ", ".join(f"{v:.3f}".rstrip("0").rstrip(".") or "0" for v in vals) + ")"


def row(name: str, k: float, c: float, m: float) -> None:
    samples, zeta, t95, settle, over = simulate(k, c, m)
    ok = t95 <= 0.22 and settle <= 0.30
    print(
        f"{name:20s} k={k:<5g} c={c:<4g} m={m:<4g} zeta={zeta:4.2f} "
        f"t95={t95 * 1000:4.0f}ms settle1%={settle * 1000:4.0f}ms overshoot={over:4.1f}% "
        f"{'OK' if ok else 'OVER BUDGET'}"
    )
    print(f"  css: {linear_easing(samples, settle)} {round(settle * 100) * 10:.0f}ms")


def main() -> None:
    if len(sys.argv) == 4:
        k, c, m = (float(a) for a in sys.argv[1:4])
        row("custom", k, c, m)
        return
    for name, (k, c, m) in PRESETS.items():
        row(name, k, c, m)


if __name__ == "__main__":
    main()
