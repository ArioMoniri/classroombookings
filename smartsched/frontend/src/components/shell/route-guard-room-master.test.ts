/**
 * HB-23d (helper-file-router.md §4.2, the backend lane's ask): the helper hands a room master to
 * `/import?kind=room-master`, a route the server opens to `planning.edit` **or** `setup.rooms`
 * (imports.py `RoomsEditor`). The shell's route check must follow that route, not the feature-index entry of
 * `/import` (planning.edit only), or a rooms-only admin gets the no-access page after the card's primary.
 */
import { describe, expect, it } from "vitest";
import { hasPermission } from "@/lib/api/shell-extra";
import { planningRequirement } from "./nav-config";

const roomsOnly = ["setup.rooms"];

describe("planningRequirement with the route's query", () => {
  it("lets a setup.rooms holder open the room-master import", () => {
    const need = planningRequirement("/import", "kind=room-master&from=helper");
    expect(hasPermission(roomsOnly, need!)).toBe(true);
    expect(hasPermission(["planning.edit"], need!)).toBe(true);
  });

  it("keeps the other import kinds (and the bare page) on planning.edit", () => {
    for (const q of ["", "kind=planning-list", "kind=weekly-grid&term=2&from=helper", "kind=crbs"]) {
      const need = planningRequirement("/import", q);
      expect(hasPermission(roomsOnly, need!)).toBe(false);
      expect(hasPermission(["planning.edit"], need!)).toBe(true);
    }
    expect(hasPermission(roomsOnly, planningRequirement("/import")!)).toBe(false);
  });

  it("does not widen other routes with the same query", () => {
    expect(hasPermission(roomsOnly, planningRequirement("/onboarding", "kind=room-master")!)).toBe(false);
    expect(hasPermission(roomsOnly, planningRequirement("/generate", "kind=room-master")!)).toBe(false);
  });
});
