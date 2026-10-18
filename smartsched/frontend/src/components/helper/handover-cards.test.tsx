/**
 * The nav card's hand-overs open the page's own dialog by its address format (handover-links.ts, lib/handover.ts):
 * "Takvimime ekle" → `/profile?calendar=1`, "Davet penceresini aç" → `/admin/users?invite=1&…`, "Yayınlama
 * penceresini aç" → `/runs/<id>?publish=1` (the published run); Dışa aktar opens the run.
 */
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api/endpoints";
import { NavView } from "./cards/nav";
import fixtures from "./__fixtures__/cards.json";
import { featureById } from "./feature-links";
import { HelperCard, type NavCard } from "./schema.gen";
import { makeHost, renderHelper } from "./test-helpers";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/reserve" }));

const nav = (feature_id: string): NavCard => {
  const e = featureById(feature_id)!;
  return HelperCard.parse({ ...fixtures.nav, feature_id, kind: e.kind, anchor: null, title: e.title, path: e.path, steps: { tr: [], en: [] }, actions: [] }) as NavCard;
};

beforeEach(() => vi.restoreAllMocks());

describe("nav card hand-overs", () => {
  it("calendar and invite", () => {
    const host = makeHost();
    const { unmount } = renderHelper(<NavView card={nav("profile.calendar")} />, { host });
    fireEvent.click(screen.getByRole("button", { name: "Takvimime ekle" }));
    expect(host.go).toHaveBeenLastCalledWith("/profile?calendar=1");
    unmount();
    renderHelper(<NavView card={nav("admin.users.invite")} />, { host });
    fireEvent.click(screen.getByRole("button", { name: "Davet penceresini aç" }));
    expect(host.go).toHaveBeenLastCalledWith("/admin/users?invite=1&email=&name=&role=&department=");
  });

  it("publish opens the published run's dialog; export opens the run", async () => {
    vi.spyOn(api.runs, "list").mockResolvedValue([{ id: 5, status: "OPTIMAL", is_active: true }] as never);
    const host = makeHost();
    const { unmount } = renderHelper(<NavView card={nav("runs.publish")} />, { host });
    fireEvent.click(screen.getByRole("button", { name: "Yayınlama penceresini aç" }));
    await waitFor(() => expect(host.go).toHaveBeenLastCalledWith("/runs/5?publish=1"));
    unmount();
    renderHelper(<NavView card={nav("runs.export")} />, { host });
    fireEvent.click(screen.getByRole("button", { name: "Sayfayı aç" }));
    await waitFor(() => expect(host.go).toHaveBeenLastCalledWith("/runs/5"));
  });

  it("a plain page opens its route", () => {
    const host = makeHost();
    renderHelper(<NavView card={nav("admin.holidays")} />, { host });
    fireEvent.click(screen.getByRole("button", { name: "Sayfayı aç" }));
    expect(host.go).toHaveBeenLastCalledWith("/admin/holidays");
  });
});
