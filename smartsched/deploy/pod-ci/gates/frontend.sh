#!/usr/bin/env bash
# Gate: frontend npm ci + npm run check (tsc + eslint + vitest), in the Playwright image so node_modules
# (native binaries: SWC, lightningcss) match the e2e gates. Memory: NODE_MEMORY / NODE_HEAP_MB (lib.sh); vitest
# runs with CI=1, so vitest.config.mts uses 2 forks with a capped heap and a 30 s test timeout. Nothing is skipped.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
in_playwright -- '
echo "==== npm ci"; npm ci --no-audit --no-fund
installed=$(node -p "require(\"@playwright/test/package.json\").version")
echo "playwright ${installed} (image ${PW_IMAGE:-?}); NODE_OPTIONS=${NODE_OPTIONS:-}"
echo "==== npm run check"; npm run check
'
