/** Import wizard flows with a review step: the CRBS upgrade (dry run → diff → confirm → result) and the room
 *  master (upload → diff → apply). The API is mocked at its module boundary; the e2e spec drives the real one. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "@/lib/api/client";
import type { UpgradeReport } from "@/lib/api/crbs-upgrade";
import { I18nProvider } from "@/lib/i18n/provider";

const state = vi.hoisted(() => ({ admin: true, dry: vi.fn(), commit: vi.fn(), upload: vi.fn() }));

vi.mock("@/lib/api/shell-extra", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/shell-extra")>()),
  usePermissions: () => ({ perms: [], me: undefined, can: () => state.admin }),
  uploadImportWithProgress: (...a: unknown[]) => state.upload(...a),
}));
vi.mock("@/lib/api/crbs-upgrade", async (orig) => {
  const real = await orig<typeof import("@/lib/api/crbs-upgrade")>();
  return { ...real, crbsUpgrade: { dryRun: (...a: unknown[]) => state.dry(...a), commit: (...a: unknown[]) => state.commit(...a) } };
});
vi.mock("@/lib/api/hooks", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/hooks")>()),
  useRooms: () => ({ data: [{ id: 1, code: "A101", display_name: "A 101", building_code: "A", floor: 1, capacity: 58, exam_capacity: 30, tags: [], is_bookable: true }], isLoading: false }),
}));

import { CrbsUpgrade } from "./crbs-upgrade";
import { RoomMasterImport } from "./room-master-import";

const report = (dry: boolean): UpgradeReport => ({
  dry_run: dry,
  fingerprint: "fp-1",
  source: { users: 1, rooms: 0, auth_roles: 4 },
  tables: { users: { before: 1, after: 2, delta: 1 }, roles: { before: 5, after: 9, delta: 4 }, rooms: { before: 90, after: 90, delta: 0 } },
  changed: { users: { before: 1, after: 2, delta: 1 }, roles: { before: 5, after: 9, delta: 4 } },
  rows_new: 5,
  importer: { created: { roles: 4, users: 1 }, updated: {}, rows_skipped_count: 0, skip_reasons: {}, extra: {} },
  warnings: ["sessions: the dates generator was skipped (MySQL variables)"],
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale="en">{ui}</I18nProvider>
    </QueryClientProvider>,
  );
}

const sql = (name: string) => new File(["CREATE TABLE users (user_id int);"], name, { type: "application/sql" });

describe("CRBS upgrade", () => {
  beforeEach(() => {
    state.admin = true;
    state.dry.mockReset().mockResolvedValue(report(true));
    state.commit.mockReset().mockResolvedValue(report(false));
  });

  it("dry-runs the dumps, shows the diff, then commits with the reviewed fingerprint", async () => {
    const onStep = vi.fn();
    wrap(<CrbsUpgrade onStep={onStep} onBack={() => undefined} />);
    expect(screen.getByTestId("crbs-upgrade-dry-run")).toBeDisabled();
    await userEvent.upload(screen.getByTestId("file-input"), [sql("structure.sql"), sql("data.sql")]);
    await userEvent.click(screen.getByTestId("crbs-upgrade-dry-run"));
    expect(state.dry.mock.calls[0]![0]).toMatchObject({ kind: "dump" });
    expect((state.dry.mock.calls[0]![0] as { files: File[] }).files.map((f) => f.name)).toEqual(["structure.sql", "data.sql"]);
    expect(await screen.findByTestId("crbs-upgrade-summary")).toHaveTextContent("5 new rows in 2 tables.");
    expect(screen.getByTestId("crbs-table-roles")).toHaveTextContent("+4");
    expect(screen.queryByTestId("crbs-table-rooms")).toBeNull(); // unchanged tables are not listed
    expect(onStep).toHaveBeenLastCalledWith("preview");
    expect(state.commit).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId("crbs-upgrade-confirm"));
    await userEvent.click(await screen.findByTestId("crbs-upgrade-commit"));
    await waitFor(() => expect(state.commit).toHaveBeenCalledTimes(1));
    expect(state.commit.mock.calls[0]![1]).toBe("fp-1");
    expect(await screen.findByTestId("crbs-upgrade-result")).toHaveTextContent("Upgrade applied");
    expect(onStep).toHaveBeenLastCalledWith("done");
  });

  it("asks for a new dry run when the source changed since (409)", async () => {
    state.commit.mockRejectedValue(new HttpError(409, "the CRBS source differs from the reviewed dry run (fingerprint mismatch); run the dry run again"));
    wrap(<CrbsUpgrade onStep={() => undefined} onBack={() => undefined} />);
    await userEvent.upload(screen.getByTestId("file-input"), sql("dump.sql"));
    await userEvent.click(screen.getByTestId("crbs-upgrade-dry-run"));
    await userEvent.click(await screen.findByTestId("crbs-upgrade-confirm"));
    await userEvent.click(await screen.findByTestId("crbs-upgrade-commit"));
    expect(await screen.findByTestId("crbs-upgrade-error")).toHaveTextContent(/source changed since the dry run/);
    expect(screen.getByTestId("crbs-upgrade-dry-run")).toBeInTheDocument(); // back at the source step
  });

  it("names the refused DSN host the backend reports (422)", async () => {
    state.dry.mockRejectedValue(new HttpError(422, "422", { detail: { message: "CRBS DSN refused", issues: ["host db:3306 is not in 'crbs_dsn_allowed_hosts' ()"], setting: "crbs_dsn_allowed_hosts" } }));
    wrap(<CrbsUpgrade onStep={() => undefined} onBack={() => undefined} />);
    await userEvent.click(screen.getByRole("tab", { name: "Live database" }));
    await userEvent.type(screen.getByTestId("crbs-upgrade-dsn"), "mysql://u:p@db:3306/crbs");
    await userEvent.click(screen.getByTestId("crbs-upgrade-dry-run"));
    expect(await screen.findByTestId("crbs-upgrade-error")).toHaveTextContent(/refused this database address.*crbs_dsn_allowed_hosts/);
  });

  it("explains that the upgrade is admin-only instead of a 403", () => {
    state.admin = false;
    wrap(<CrbsUpgrade onStep={() => undefined} onBack={() => undefined} />);
    expect(screen.getByTestId("crbs-upgrade-admin-only")).toHaveTextContent("Only an administrator");
  });
});

describe("room master", () => {
  beforeEach(() => {
    state.upload.mockReset().mockResolvedValue({ id: 9, kind: "room-master", filename: "room_master.csv", status: "DONE", summary: { rows: 2, created: 1, updated: 1, skipped: 0, warnings: [] }, created_at: "2026-10-15T18:00:00Z" });
  });

  it("shows the diff before anything is written, then applies it", async () => {
    wrap(<RoomMasterImport term={{ id: 1, code: "2026-BAHAR", start_date: "2026-02-02" }} onStep={() => undefined} onBack={() => undefined} />);
    const csv = new File(["code;capacity;exam_capacity;tags\nA 101;60;30;PC\nZ 999;10;;\n"], "room_master.csv", { type: "text/csv" });
    await userEvent.upload(screen.getByTestId("file-input"), csv);
    expect(await screen.findByTestId("room-master-counts")).toHaveTextContent("1 rooms change · 0 unchanged · 1 not matched · 0 lines with errors");
    expect(screen.getByTestId("rm-row-changed")).toHaveTextContent(/Capacity:\s*58\s*→\s*60/);
    expect(screen.getByTestId("rm-row-changed")).toHaveTextContent(/Tags:\s*–\s*→\s*PC/);
    expect(state.upload).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId("room-master-apply"));
    await waitFor(() => expect(state.upload).toHaveBeenCalledTimes(1));
    expect(state.upload.mock.calls[0]![0]).toBe("room-master");
    expect(await screen.findByTestId("room-master-result")).toHaveTextContent("2 rows read · 1 rooms updated · 1 created");
  });
});
