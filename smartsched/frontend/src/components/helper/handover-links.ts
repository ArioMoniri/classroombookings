/**
 * The helper's hand-over links (helper.md §4.3, ROADMAP HX-06): a card never writes for these, it opens the page's
 * own dialog or field with values in the address, in the formats the pages read (lib/handover.ts):
 *
 * - `/profile?calendar=1`: the "Takvimime ekle" sheet;
 * - `/admin/users?invite=1&email=&name=&role=&department=`: the invite sheet, prefilled;
 * - `/runs/<id>?publish=1`: the run's publish dialog;
 * - `/runs/<id>?chat=<text>`: the run chat's composer, prefilled, not sent.
 *
 * Yayınla and Dışa aktar exist only on a run's own page (`/runs/<id>`), while the feature index (static routes)
 * says `/runs`. {@link resolveRunId} picks the run: the one in the address, else (Yayınla) the newest finished
 * unpublished one, else the published one, else the newest finished one; with no run they fall back to `/runs` (where "Göster" then says the button is not on the page).
 */
import { api } from "@/lib/api/endpoints";
import type { ScheduleRun } from "@/lib/api/schemas";
import type { FeatureEntry } from "./feature-links";

export interface InviteValues {
  email?: string;
  name?: string;
  role?: string;
  department?: string;
}

/** Features whose control is on `/runs/<id>` only. */
const RUN_SCOPED: ReadonlySet<string> = new Set(["runs.publish", "runs.export"]);

export const isRunScoped = (e: FeatureEntry): boolean => RUN_SCOPED.has(e.id);

const FINISHED: ReadonlySet<string> = new Set(["OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL"]);

/**
 * The published run, else the newest finished one (by id), else null. For Yayınla (`runs.publish`) the newest
 * finished run that is not published yet comes first: the published run has no Yayınla button (HB18-F05).
 */
export function pickRun(runs: readonly Pick<ScheduleRun, "id" | "status" | "is_active">[], featureId?: string): number | null {
  if (featureId === "runs.publish") {
    const unpublished = runs.filter((r) => !r.is_active && FINISHED.has(r.status)).sort((a, b) => b.id - a.id);
    if (unpublished[0]) return unpublished[0].id;
  }
  const active = runs.find((r) => r.is_active && FINISHED.has(r.status));
  if (active) return active.id;
  const done = runs.filter((r) => FINISHED.has(r.status)).sort((a, b) => b.id - a.id);
  return done[0]?.id ?? null;
}

/** The run a run-scoped control means: the address's `/runs/<id>`, else {@link pickRun} over the person's runs. */
export async function resolveRunId(pathname: string, featureId?: string): Promise<number | null> {
  const here = /^\/runs\/(\d+)(?:\/|$)/.exec(pathname);
  if (here) return Number(here[1]);
  try {
    return pickRun(await api.runs.list(), featureId);
  } catch {
    return null;
  }
}

/** A run-scoped feature's page (`/runs/<id>`, or `/runs` without a run). */
export const runFeatureHref = (_featureId: string, runId: number | null): string => (runId ? `/runs/${runId}` : "/runs");

/** The run chat with a prefilled draft (≤ 500 characters, plain text; the person sends it). */
export const runChatHref = (runId: number, text: string): string => `/runs/${runId}?${new URLSearchParams({ chat: text.slice(0, 500) })}`;

/** The hand-over link of a feature, or null when it has none (its plain route is used). */
export function handoverHref(featureId: string, opts: { invite?: InviteValues; runId?: number | null } = {}): string | null {
  switch (featureId) {
    case "profile.calendar":
      return "/profile?calendar=1";
    case "admin.users.invite": {
      const v = opts.invite ?? {};
      const q = new URLSearchParams({ invite: "1", email: v.email ?? "", name: v.name ?? "", role: v.role ?? "", department: v.department ?? "" });
      return `/admin/users?${q}`;
    }
    case "runs.publish":
      return opts.runId ? `/runs/${opts.runId}?publish=1` : "/runs";
    default:
      return null;
  }
}
