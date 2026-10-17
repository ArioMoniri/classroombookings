/**
 * Round-2 T-R2-25 (R2-M-11 / R2-M-26): after a priority is saved, focus never falls to <body>. The request / section
 * form returns focus to the edited row (`data-row-id`), a person's or programme's form keeps it on its own save
 * button while the parent refreshes its data.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { PriorityForm, SubjectPriorityForm } from "./priority-editor";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
// the signed-in account's permissions (an administrator unless a test says otherwise)
const me = vi.hoisted(() => ({ perms: ["planning.view", "planning.edit", "planning.admin"] as string[] }));
vi.mock("@/lib/permissions", async (orig) => {
  const real = await orig<typeof import("@/lib/permissions")>();
  return { ...real, usePermissions: () => ({ loading: false, perms: me.perms, can: (need: string | string[]) => real.hasPermission(me.perms, need), canAll: (need: string[]) => real.hasAllPermissions(me.perms, need), userId: 1, departmentId: null }) };
});

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const wrap = (ui: React.ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLocale="tr">{ui}</I18nProvider>
    </QueryClientProvider>,
  );

afterEach(() => {
  vi.unstubAllGlobals();
  me.perms = ["planning.view", "planning.edit", "planning.admin"];
});

describe("who sets a person's priority (owner decision 2026-10-17, R2-M-08)", () => {
  it("hides the person priority form from a planner; a programme's form stays", () => {
    me.perms = ["planning.view", "planning.edit"];
    wrap(
      <>
        <SubjectPriorityForm subject="person" id={98} termId={2} label="Dr. Öğr. Üyesi S. E." current={null} />
        <SubjectPriorityForm subject="program" id={5} termId={2} label="Psikoloji" current={null} />
      </>,
    );
    expect(screen.queryByTestId("person-priority")).toBeNull();
    expect(screen.queryByTestId("person-priority-save")).toBeNull();
    expect(screen.getByTestId("program-priority-save")).toBeInTheDocument();
  });
  it("shows it to a coordinator / administrator (planning.admin)", () => {
    wrap(<SubjectPriorityForm subject="person" id={98} termId={2} label="Dr. Öğr. Üyesi S. E." current={null} />);
    expect(screen.getByTestId("person-priority-save")).toBeInTheDocument();
  });
});

describe("priority editor focus (T-R2-25)", () => {
  it("returns focus to the edited row after a request priority is saved", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ priority: 1, previous: null })));
    const onDone = vi.fn();
    wrap(
      <>
        <div role="row" tabIndex={0} data-row-id="1156" data-testid="the-row">PSY 277 §1</div>
        <PriorityForm target={{ termId: 2, requestId: 1156, sectionId: 77, label: "PSY 277 §1", priority: { value: 0, source: "default" } }} onDone={onDone} />
      </>,
    );
    await userEvent.click(screen.getByTestId("priority-save"));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    await waitFor(() => expect(document.activeElement).toBe(screen.getByTestId("the-row")));
    expect(document.activeElement).not.toBe(document.body);
  });
  it("keeps focus on the save button after a person priority is saved, also when the parent re-renders it", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ subject_type: "person", subject_id: 98, term_id: 2, priority: 1, previous: null, source: "person", request_ids: [1, 2, 3, 4] })));
    const { rerender } = wrap(<SubjectPriorityForm subject="person" id={98} termId={2} label="Dr. Öğr. Üyesi S. E." current={null} />);
    await userEvent.click(screen.getByTestId("person-priority-save"));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByTestId("person-priority-save")));
    // the profile refetches the overrides and passes the new value down: no remount, the focus stays
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <I18nProvider initialLocale="tr">
          <SubjectPriorityForm subject="person" id={98} termId={2} label="Dr. Öğr. Üyesi S. E." current={1} />
        </I18nProvider>
      </QueryClientProvider>,
    );
    expect(document.activeElement).toBe(screen.getByTestId("person-priority-save"));
    expect(document.activeElement).not.toBe(document.body);
  });
});
