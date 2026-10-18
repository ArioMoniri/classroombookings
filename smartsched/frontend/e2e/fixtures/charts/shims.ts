// CH-03 fixture only (e2e/charts-a11y.spec.ts): stand-ins for the Next runtime, which a plain vite bundle lacks.
import { Suspense, createElement, lazy, type ComponentType } from "react";

export default function dynamic<P extends object>(loader: () => Promise<ComponentType<P>>, opts?: { loading?: ComponentType }) {
  const Lazy = lazy(async () => ({ default: await loader() }));
  return function Dynamic(props: P) {
    return createElement(Suspense, { fallback: opts?.loading ? createElement(opts.loading) : null }, createElement(Lazy as ComponentType<P>, props));
  };
}

export const usePathname = () => "/fixture";
export const useSearchParams = () => new URLSearchParams();
export const useRouter = () => ({ replace: () => undefined, push: () => undefined });
