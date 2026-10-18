/**
 * Where the e2e specs read the seed workbooks from (FIX-I, after FIX-J's KVKK upload guard).
 *
 * - `E2E_FIXTURES_DIR` always wins.
 * - A recording stack (`scripts/record/stack.sh`: `REC_WORKDIR` set, or `KVKK_UPLOAD_GUARD=1`, or
 *   `E2E_RECORDING_STACK=1`) refuses the raw, unmasked workbooks of backend/tests/fixtures (app/core/kvkk_guard.py),
 *   so the specs use the masked copies `stack.sh fixtures` writes to `$REC_WORKDIR/fixtures`, and fail with a clear
 *   message when there are none, instead of uploading the raw files.
 * - Anything else (pod CI, a plain local backend: the guard is off there) keeps the raw fixtures.
 */
import { existsSync } from "node:fs";
import path from "node:path";

type Env = Record<string, string | undefined>;

export function resolveFixturesDir(env: Env, raw: string, exists: (p: string) => boolean = existsSync): string {
  if (env.E2E_FIXTURES_DIR) return env.E2E_FIXTURES_DIR;
  const recording = Boolean(env.REC_WORKDIR) || env.KVKK_UPLOAD_GUARD === "1" || env.E2E_RECORDING_STACK === "1";
  if (!recording) return raw;
  const masked = env.REC_WORKDIR ? path.join(env.REC_WORKDIR, "fixtures") : null;
  if (masked && exists(masked)) return masked;
  throw new Error(
    "KVKK: this is a recording stack (scripts/record/stack.sh), whose /import and council refuse the raw seed workbooks. " +
      "Set E2E_FIXTURES_DIR=$REC_WORKDIR/fixtures (masked copies; run `scripts/record/stack.sh fixtures` to make them). " +
      "The raw backend/tests/fixtures are used only where the upload guard is off (pod CI, a plain local backend).",
  );
}
