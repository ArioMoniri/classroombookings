"use client";
// SmartSched charts (CH-02): finds the ECharts instance EvilCharts mounted inside a form and hands the shell a small
// API (image export now; `showTip` for the CH-03 keyboard layer). Resolved on every call, because EvilCharts
// re-inits the instance when the renderer changes (print, phone). Imported only by the lazy forms. Original work.
import * as echarts from "echarts/core";
import { useEffect, type RefObject } from "react";
import type { ChartApi } from "./chart-form-types";

export function findInstance(root: HTMLElement | null): ReturnType<typeof echarts.getInstanceByDom> {
  if (!root) return undefined;
  for (const el of Array.from(root.querySelectorAll<HTMLElement>("div"))) {
    const inst = echarts.getInstanceByDom(el);
    if (inst && !inst.isDisposed()) return inst;
  }
  return undefined;
}

export function useChartApi(ref: RefObject<HTMLElement | null>, onReady?: (api: ChartApi) => void): void {
  useEffect(() => {
    if (!onReady) return;
    type Action = Parameters<ReturnType<typeof echarts.init>["dispatchAction"]>[0];
    onReady({
      getDataURL: (opts) => findInstance(ref.current)?.getDataURL(opts) ?? null,
      dispatchAction: (action) => findInstance(ref.current)?.dispatchAction(action as Action),
      // by pixel, like a hover: `showTip` by dataIndex shows an empty tooltip when the axis pointer is "none"
      // (EvilCharts bars). The bucket's x comes from the category axis; y is the plot's middle.
      showTip: (index) => {
        const inst = findInstance(ref.current);
        if (!inst) return;
        const x = inst.convertToPixel({ xAxisIndex: 0 }, index) as unknown as number;
        (window as unknown as Record<string, unknown>).__dbg = { x, h: inst.getHeight(), xa: JSON.stringify((inst.getOption() as Record<string, unknown>).xAxis).slice(0, 200), tt: JSON.stringify((inst.getOption() as Record<string, unknown>).tooltip).slice(0, 300) };
        if (!Number.isFinite(x)) return;
        inst.dispatchAction({ type: "showTip", x, y: inst.getHeight() / 2 } as Action);
      },
      hideTip: () => findInstance(ref.current)?.dispatchAction({ type: "hideTip" } as Action),
    });
  }, [ref, onReady]);
}
