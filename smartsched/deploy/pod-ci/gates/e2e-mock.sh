#!/usr/bin/env bash
# Gate: Playwright smoke against the mock API (builds and starts next on :3100), like the Actions job.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
in_playwright -e "PW_IMAGE=${PW_IMAGE}" -- 'npx playwright test --reporter=list'
