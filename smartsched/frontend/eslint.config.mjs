import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // TanStack Table/Virtual return non-memoisable functions; the compiler skips those components on purpose.
      "react-hooks/incompatible-library": "off",
    },
  },
  {
    // motion audit 2026-10-15 T5: motion's hook ignores the in-app "Reduce motion" switch (<html data-motion>)
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/lib/motion.ts", "src/components/ui/**"],
    rules: {
      "no-restricted-imports": ["error", { paths: [{ name: "motion/react", importNames: ["useReducedMotion"], message: "Use useReduce() from @/lib/motion: it also honours Settings → Appearance → Reduce motion." }] }],
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
