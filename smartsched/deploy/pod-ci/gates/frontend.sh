#!/usr/bin/env bash
# Gate: frontend npm ci + npm run check (tsc + eslint + vitest), in the Playwright image so node_modules
# (native binaries: SWC, lightningcss) match the e2e gates.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
in_playwright -- '
echo "==== npm ci"; npm ci --no-audit --no-fund
installed=$(node -p "require(\"@playwright/test/package.json\").version")
echo "playwright ${installed} (image ${PW_IMAGE:-?})"
echo "==== npm run check"; npm run check
'
