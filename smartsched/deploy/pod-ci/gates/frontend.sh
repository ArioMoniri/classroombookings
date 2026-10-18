#!/usr/bin/env bash
# Gate: frontend npm ci + the static checks of `npm run check` (tsc + eslint + check-design), in the Playwright
# image so node_modules (native binaries: SWC, lightningcss) match the e2e gates. Memory: NODE_MEMORY /
# NODE_HEAP_MB (lib.sh). vitest runs in the frontend-unit-* gates (gates/frontend-unit.sh) on the node_modules
# installed here: one gate with all of `npm run check` ran past 1800 s on the 2-CPU pod (runs #70, #81).
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
in_playwright -- '
echo "==== npm ci"; npm ci --no-audit --no-fund
installed=$(node -p "require(\"@playwright/test/package.json\").version")
echo "playwright ${installed} (image ${PW_IMAGE:-?}); NODE_OPTIONS=${NODE_OPTIONS:-}"
step() { local s=$SECONDS; echo "==== $1"; shift; "$@"; echo "---- $((SECONDS - s)) s"; }
# the same commands and heaps as package.json "check", minus the final `vitest run`
step "tsc" node --max-old-space-size=3072 node_modules/typescript/bin/tsc --noEmit
step "eslint" node --max-old-space-size=2048 node_modules/eslint/bin/eslint.js .
step "check-design" node scripts/check-design.mjs
'
