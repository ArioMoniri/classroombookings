/**
 * Flow loop round 2, lane F (docs/ROADMAP.md T-R2-31..33): the admin screens' contracts behind the fixes.
 *
 * - T-R2-32: every disabled permission box in the roles editor carries a visible reason (not held, read-only role,
 *   locked Administrator); /admin/departments is a card list on phones and a table with a pinned first column
 *   otherwise; the user form says a missing role next to the field; the features grid, the language rows and the
 *   permission rows step to 44 px on coarse pointers (jsdom has no layout: class contracts, like settings-solver-touch).
 * - T-R2-33: the English CHANGELOG list on Kurum ayarları sits in a closed <details lang="en"> behind a Turkish line.
 * - T-R2-31: the audit row is the focus target after an undo and renders a coded reason (audit-model.test.ts).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import type { Locale } from "@/lib/i18n";

const phone = vi.hoisted(() => ({ value: false }));
const data = vi.hoisted(() => ({
  departments: [
    { id: 1, name: "Tıp Fakültesi", description: "Dönem 1-3", icon: null, faculty_id: null, is_evening: false, user_count: 4 },
    { id: 2, name: "Hemşirelik", description: null, icon: null, faculty_id: null, is_evening: false, user_count: 0 },
  ],
  changelog: { entries: [{ version: "0.9.0", date: "2026-10-01", sections: { Added: ["Roles with permission sets and booking limits."] } }], latest: "0.9.0", viewed_at: null, unread: false },
}));
vi.mock("next/navigation", () => ({ usePathname: () => "/admin/departments", useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }), useSearchParams: () => new URLSearchParams() }));
vi.mock("@/components/bookings/use-is-phone", () => ({ useIsPhone: () => phone.value, useIsCompact: () => phone.value }));
vi.mock("@/lib/api/crbs", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/crbs")>()),
  useDepartments: () => ({ data: data.departments, isLoading: false }),
  useChangelog: () => ({ data: data.changelog, isLoading: false }),
}));

import { DepartmentsAdmin } from "./departments-admin";
import { PermissionMatrix } from "./roles-admin";
import { WhatsNewPanel } from "./whats-new";

function wrap(ui: ReactNode, locale: Locale = "tr") {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLocale={locale}>{ui}</I18nProvider>
    </QueryClientProvider>,
  );
}

const src = (file: string) => readFileSync(join(process.cwd(), "src/components", file), "utf8");

const catalogue = {
  system: { planning: [{ id: 1, name: "planning.admin" }, { id: 2, name: "setup.users" }] },
  bookings: { room: [{ id: 3, name: "room.view" }] },
};
const hintsAndDisabled = () => ({
  hints: screen.queryAllByTestId("role-disabled-hint").map((h) => h.textContent),
  disabled: screen.getAllByRole("checkbox").filter((c) => c.hasAttribute("disabled") || c.getAttribute("aria-disabled") === "true").length,
});

describe("roles editor: a reason under every disabled permission (T-R2-32, F-11 S04)", () => {
  it("names the permissions the editor lacks", () => {
    wrap(<PermissionMatrix catalogue={catalogue} value={new Set()} onToggle={() => undefined} held={new Set(["setup.users", "room.view"])} />);
    const { hints, disabled } = hintsAndDisabled();
    // planning.admin plus the 14 booking actions (book_single.* / book_recur.*) the editor does not hold
    expect(disabled).toBe(15);
    expect(hints).toHaveLength(disabled);
    expect(new Set(hints)).toEqual(new Set(["Bu yetki sizde yok"]));
  });
  it("explains a read-only role on the boxes the editor does hold, and the missing ones as missing", () => {
    wrap(<PermissionMatrix catalogue={catalogue} value={new Set()} onToggle={() => undefined} disabled held={new Set(["setup.users", "room.view"])} />);
    const { hints, disabled } = hintsAndDisabled();
    expect(disabled).toBe(17);
    expect(hints).toHaveLength(disabled);
    expect(hints.filter((h) => h === "Bu yetki sizde yok")).toHaveLength(15);
    expect(hints.filter((h) => h === "Bu rol salt okunur; değiştiremezsiniz")).toHaveLength(2);
  });
  it("explains the locked Administrator role on every box", () => {
    wrap(<PermissionMatrix catalogue={catalogue} value={new Set(["planning.admin", "setup.users", "room.view"])} onToggle={() => undefined} disabled locked />);
    const { hints, disabled } = hintsAndDisabled();
    expect(disabled).toBe(17);
    expect(hints).toHaveLength(disabled);
    expect(new Set(hints)).toEqual(new Set(["Yönetici rolünde her izin korunur"]));
  });
  it("permission rows are 44 px label rows on coarse pointers", () => {
    const s = src("admin/roles-admin.tsx");
    const systemRow = s.split("\n").find((l) => l.includes('data-permission={p.name}') && l.includes("items-start"));
    expect(systemRow).toContain("pointer-coarse:min-h-11");
  });
});

describe("/admin/departments on a phone (T-R2-32, MOBILE.md M-07)", () => {
  it("is a card list: the name on line 1, the count and 44 px actions", () => {
    phone.value = true;
    wrap(<DepartmentsAdmin />);
    expect(screen.getByTestId("departments-cards")).toBeInTheDocument();
    expect(screen.queryByTestId("departments-table")).toBeNull();
    const card = screen.getByTestId("department-card-1");
    expect(card).toHaveTextContent("Tıp Fakültesi");
    expect(card).toHaveTextContent("Dönem 1-3 · 4 kullanıcı");
    expect(screen.getByTestId("department-card-2")).toHaveTextContent("0 kullanıcı");
    expect(screen.getByRole("button", { name: "Tıp Fakültesi düzenle" })).toHaveClass("pointer-coarse:size-11");
    phone.value = false;
  });
  it("keeps the table with a pinned first column elsewhere", () => {
    phone.value = false;
    wrap(<DepartmentsAdmin />);
    const table = screen.getByTestId("departments-table");
    const first = table.querySelector("tbody tr > :first-child");
    expect(first).toHaveClass("sticky", "left-0");
    expect(screen.queryByTestId("departments-cards")).toBeNull();
  });
});

describe("Kurum ayarları › Yenilikler (T-R2-33, R2-M-18)", () => {
  it("keeps the English changelog behind a closed Turkish summary, marked lang=en", () => {
    wrap(<WhatsNewPanel />);
    const details = screen.getByTestId("news-english") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    expect(details.querySelector("summary")).toHaveTextContent("İngilizce notları göster");
    expect(details.querySelector("summary")).toHaveTextContent("Sürüm notları İngilizce yazılır.");
    // round 3: the English list is not in the DOM while the detail is closed; opened, it is marked lang=en
    expect(details.querySelector('[lang="en"]')).toBeNull();
    details.open = true;
    fireEvent(details, new Event("toggle"));
    expect(details.querySelector('[lang="en"]')).toHaveTextContent("Roles with permission sets");
  });
  it("shows the list directly in the English UI", () => {
    wrap(<WhatsNewPanel />, "en");
    expect(screen.queryByTestId("news-english")).toBeNull();
    expect(screen.getByText("Roles with permission sets and booking limits.")).toBeInTheDocument();
  });
});

describe("class contracts on touch (jsdom has no layout)", () => {
  it("the user form says a missing role next to its field, read with it", () => {
    const s = src("admin/users-admin.tsx");
    expect(s).toContain('data-testid="role-error"');
    expect(s).toContain("aria-invalid={error ? true : undefined}");
    expect(s).toContain('setRoleError(t("crbs.users.needRole"))');
    expect(s).toContain('document.getElementById("u-role")?.focus()');
  });
  it("the features grid cells and the language rows step to 44 px", () => {
    const f = src("admin/features-admin.tsx");
    expect(f).toContain("pointer-coarse:min-h-11 pointer-coarse:min-w-11");
    expect(f.match(/pointer-coarse:h-11/g)?.length ?? 0).toBeGreaterThanOrEqual(3);
    const o = src("admin/org-settings.tsx");
    const lang = o.split("\n").find((l) => l.includes("lang={l.code}") && l.includes("<label"));
    expect(lang).toContain("pointer-coarse:min-h-11");
  });
  it("the audit row is the focus target after Geri al and the button is 44 px on phones (T-R2-31, R2-S-08)", () => {
    const a = src("audit/audit-view.tsx");
    expect(a).toContain('focusAfter([`[data-audit-id="${event.id}"]`])');
    expect(a).toContain("data-audit-id={e.id}");
    expect(a).toContain("tabIndex={-1}");
    const undo = a.split("\n").find((l) => l.includes("data-testid={`audit-undo-${e.id}`}"));
    expect(undo).toContain("pointer-coarse:h-11");
    expect(a).toContain("auditReason(e.reason, t)");
  });
});
