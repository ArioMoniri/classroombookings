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
    onReady({
      getDataURL: (opts) => findInstance(ref.current)?.getDataURL(opts) ?? null,
      dispatchAction: (action) => findInstance(ref.current)?.dispatchAction(action as Parameters<ReturnType<typeof echarts.init>["dispatchAction"]>[0]),
    });
  }, [ref, onReady]);
}
