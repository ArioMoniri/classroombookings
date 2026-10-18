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
        if (!Number.isFinite(x)) return;
        inst.dispatchAction({ type: "showTip", x, y: inst.getHeight() / 2 } as Action);
      },
      hideTip: () => findInstance(ref.current)?.dispatchAction({ type: "hideTip" } as Action),
      // CH-08 / CH-10: a click or tap selects the bucket under it (category axis → its index), only inside the grid
      indexAt: (clientX, clientY) => {
        const inst = findInstance(ref.current);
        if (!inst) return null;
        const rect = inst.getDom().getBoundingClientRect();
        const point = [clientX - rect.left, clientY - rect.top];
        if (!inst.containPixel({ gridIndex: 0 }, point)) return null;
        const value = inst.convertFromPixel({ gridIndex: 0 }, point) as unknown;
        const x = Array.isArray(value) ? Number(value[0]) : Number(value);
        return Number.isFinite(x) ? Math.round(x) : null;
      },
    });
  }, [ref, onReady]);
}
