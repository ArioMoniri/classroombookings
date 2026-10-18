/**
 * WG-04 contract: the REAL backend's answers (captured 2026-10-18 from the WG-B stack, fresh seed, the seeded teacher and
 * admin) parse with lib/api/welcome.ts and render the right sheet, steps and checklist.
 */
import { describe, expect, it } from "vitest";
import { buildChecklist, buildSheet, buildSteps } from "@/components/welcome/model";
import { WelcomeContent, WelcomeSettings, WelcomeState, WelcomeStats } from "./welcome";

const LIVE = {
  "teacher": {
    "preview": false,
    "audiences": [
      "staff"
    ],
    "primary": "staff",
    "secondary": [],
    "audience_labels": {
      "staff": {
        "tr": "İdari personel",
        "en": "Staff"
      }
    },
    "name": "Akademik",
    "locale": "tr",
    "enabled": {
      "sheet": true,
      "tour": true,
      "checklist": true,
      "hints": true
    },
    "show": {
      "kind": "sheet",
      "key": "sheet",
      "audiences": [
        "staff"
      ],
      "updated": false
    },
    "suppressed": null,
    "sheet": {
      "audience": "staff",
      "state": null,
      "snooze_count": 0,
      "snoozed_until": null,
      "delta": false,
      "updated": false,
      "cards": [
        {
          "key": "quick_reserve",
          "audience": "staff",
          "href": "/reserve",
          "also": false
        },
        {
          "key": "find_room",
          "audience": "staff",
          "href": "/find-room",
          "also": false
        },
        {
          "key": "approval_rooms",
          "audience": "staff",
          "href": "/find-room",
          "also": false
        },
        {
          "key": "my_bookings",
          "audience": "staff",
          "href": "/my-bookings",
          "also": false
        }
      ],
      "overrides": {}
    },
    "tour": {
      "state": null,
      "step": null,
      "steps": [
        {
          "key": "staff.1",
          "audience": "staff",
          "anchor": "nav-reserve",
          "route": null,
          "interactive": false
        },
        {
          "key": "staff.2",
          "audience": "staff",
          "anchor": "nav-find-room",
          "route": null,
          "interactive": false
        },
        {
          "key": "staff.3",
          "audience": "staff",
          "anchor": "nav-my-bookings",
          "route": null,
          "interactive": false
        },
        {
          "key": "staff.4",
          "audience": "staff",
          "anchor": "user-menu",
          "route": null,
          "interactive": false
        }
      ]
    },
    "checklist": {
      "state": null,
      "hidden": false,
      "items": [
        {
          "key": "profile",
          "audience": "staff",
          "href": "/profile",
          "done": false,
          "manual": false
        },
        {
          "key": "first_booking",
          "audience": "staff",
          "href": "/reserve",
          "done": false,
          "manual": false
        },
        {
          "key": "find_room_filter",
          "audience": "staff",
          "href": "/find-room",
          "done": false,
          "manual": true
        },
        {
          "key": "channel",
          "audience": "staff",
          "href": "/profile#notifications",
          "done": false,
          "manual": false
        },
        {
          "key": "calendar_bookings",
          "audience": "staff",
          "href": "/profile#calendar",
          "done": false,
          "manual": false
        }
      ],
      "done": 0,
      "total": 5
    },
    "hints": [],
    "content_version": {
      "staff": 0
    }
  },
  "admin": {
    "preview": false,
    "audiences": [
      "admin",
      "planner",
      "approver"
    ],
    "primary": "admin",
    "secondary": [
      "planner",
      "approver"
    ],
    "audience_labels": {
      "admin": {
        "tr": "Yönetici",
        "en": "Administrator"
      },
      "planner": {
        "tr": "Planlamacı",
        "en": "Planner"
      },
      "approver": {
        "tr": "Onaylayıcı",
        "en": "Approver"
      }
    },
    "name": "Administrator",
    "locale": "tr",
    "enabled": {
      "sheet": true,
      "tour": true,
      "checklist": true,
      "hints": true
    },
    "show": {
      "kind": "sheet",
      "key": "sheet",
      "audiences": [
        "admin",
        "planner",
        "approver"
      ],
      "updated": false
    },
    "suppressed": null,
    "sheet": {
      "audience": "admin",
      "state": null,
      "snooze_count": 0,
      "snoozed_until": null,
      "delta": false,
      "updated": false,
      "cards": [
        {
          "key": "users_roles",
          "audience": "admin",
          "href": "/admin/users",
          "also": false
        },
        {
          "key": "rooms_access",
          "audience": "admin",
          "href": "/admin/rooms",
          "also": false
        },
        {
          "key": "term_times",
          "audience": "admin",
          "href": "/admin/sessions",
          "also": false
        },
        {
          "key": "rules_connections",
          "audience": "admin",
          "href": "/admin/integrations",
          "also": false
        },
        {
          "key": "from_files",
          "audience": "planner",
          "href": "/onboarding",
          "also": true
        }
      ],
      "overrides": {}
    },
    "tour": {
      "state": null,
      "step": null,
      "steps": [
        {
          "key": "admin.1",
          "audience": "admin",
          "anchor": "nav-admin",
          "route": "/admin",
          "interactive": false
        },
        {
          "key": "admin.2",
          "audience": "admin",
          "anchor": "admin-group-users",
          "route": null,
          "interactive": false
        },
        {
          "key": "admin.3",
          "audience": "admin",
          "anchor": "admin-group-resources",
          "route": null,
          "interactive": false
        },
        {
          "key": "admin.4",
          "audience": "admin",
          "anchor": "admin-group-timetable",
          "route": null,
          "interactive": false
        },
        {
          "key": "admin.5",
          "audience": "admin",
          "anchor": "nav-integrations",
          "route": null,
          "interactive": false
        },
        {
          "key": "admin.6",
          "audience": "admin",
          "anchor": "nav-welcome-admin",
          "route": null,
          "interactive": false
        },
        {
          "key": "approver.1",
          "audience": "approver",
          "anchor": "nav-approvals",
          "route": null,
          "interactive": false
        }
      ]
    },
    "checklist": {
      "state": "shown",
      "hidden": false,
      "items": [
        {
          "key": "org_ready",
          "audience": "admin",
          "href": "/admin/settings",
          "done": false,
          "manual": false
        },
        {
          "key": "rooms_added",
          "audience": "admin",
          "href": "/admin/rooms",
          "done": true,
          "manual": false
        },
        {
          "key": "users_invited",
          "audience": "admin",
          "href": "/admin/users",
          "done": true,
          "manual": false
        },
        {
          "key": "mail_ready",
          "audience": "admin",
          "href": "/admin/email",
          "done": false,
          "manual": false
        },
        {
          "key": "welcome_reviewed",
          "audience": "admin",
          "href": "/admin/welcome",
          "done": false,
          "manual": true
        },
        {
          "key": "intake_done",
          "audience": "planner",
          "href": "/onboarding",
          "done": false,
          "manual": false
        }
      ],
      "done": 2,
      "total": 6
    },
    "hints": [],
    "content_version": {
      "admin": 0,
      "planner": 0,
      "approver": 0
    }
  },
  "settings": {
    "settings": {
      "enabled": true,
      "sheet": true,
      "tour": true,
      "checklist": true,
      "hints": true,
      "hints_for_all": false,
      "min_cohort": 5
    },
    "content_version": {
      "admin": 0,
      "planner": 0,
      "viewer": 0,
      "dept_admin": 0,
      "approver": 0,
      "academician": 0,
      "staff": 0
    },
    "text_version": {
      "admin": 0,
      "planner": 0,
      "viewer": 0,
      "dept_admin": 0,
      "approver": 0,
      "academician": 0,
      "staff": 0
    },
    "hints_for_all_at": null,
    "updated_at": null
  },
  "content": {
    "audience": "academician",
    "label": {
      "tr": "Öğretim elemanı",
      "en": "Academician"
    },
    "version": 0,
    "content_version": 0,
    "locales": [
      "tr",
      "en"
    ],
    "editable": [
      {
        "field": "title",
        "max": 80
      },
      {
        "field": "lead",
        "max": 200
      },
      {
        "field": "cards.quick_reserve.title",
        "max": 80
      },
      {
        "field": "cards.quick_reserve.body",
        "max": 200
      },
      {
        "field": "cards.my_requests.title",
        "max": 80
      },
      {
        "field": "cards.my_requests.body",
        "max": 200
      },
      {
        "field": "cards.my_bookings.title",
        "max": 80
      },
      {
        "field": "cards.my_bookings.body",
        "max": 200
      },
      {
        "field": "cards.calendar.title",
        "max": 80
      },
      {
        "field": "cards.calendar.body",
        "max": 200
      }
    ],
    "placeholders": [
      "ad",
      "bölüm",
      "department",
      "name"
    ],
    "fields": {
      "tr": {},
      "en": {}
    },
    "updated_by": null,
    "updated_at": null
  },
  "stats": {
    "days": 30,
    "since": "2026-09-18T00:37:47",
    "min_cohort": 5,
    "audiences": [
      {
        "audience": "admin",
        "small_group": true,
        "shown": null,
        "tour_completed_pct": null,
        "checklist_80_pct": null,
        "dismissed_pct": null,
        "median_days_to_first_booking": null
      },
      {
        "audience": "planner",
        "small_group": true,
        "shown": null,
        "tour_completed_pct": null,
        "checklist_80_pct": null,
        "dismissed_pct": null,
        "median_days_to_first_booking": null
      },
      {
        "audience": "viewer",
        "small_group": true,
        "shown": null,
        "tour_completed_pct": null,
        "checklist_80_pct": null,
        "dismissed_pct": null,
        "median_days_to_first_booking": null
      },
      {
        "audience": "dept_admin",
        "small_group": true,
        "shown": null,
        "tour_completed_pct": null,
        "checklist_80_pct": null,
        "dismissed_pct": null,
        "median_days_to_first_booking": null
      },
      {
        "audience": "approver",
        "small_group": true,
        "shown": null,
        "tour_completed_pct": null,
        "checklist_80_pct": null,
        "dismissed_pct": null,
        "median_days_to_first_booking": null
      },
      {
        "audience": "academician",
        "small_group": true,
        "shown": null,
        "tour_completed_pct": null,
        "checklist_80_pct": null,
        "dismissed_pct": null,
        "median_days_to_first_booking": null
      },
      {
        "audience": "staff",
        "small_group": true,
        "shown": null,
        "tour_completed_pct": null,
        "checklist_80_pct": null,
        "dismissed_pct": null,
        "median_days_to_first_booking": null
      }
    ]
  }
} as const;

describe("welcome API contract (WG-B)", () => {
  it("GET /welcome (staff): the sheet with four staff cards, the tour, the checklist", () => {
    const s = WelcomeState.parse(LIVE.teacher);
    expect(s.show?.kind).toBe("sheet");
    expect(s.name).toBe("Akademik");
    const sheet = buildSheet(s)!;
    expect(sheet.primary).toBe("staff");
    expect(sheet.cards.map((c) => c.key)).toEqual(["quick_reserve", "find_room", "approval_rooms", "my_bookings"]);
    expect(buildSteps(s).map((x) => x.anchor)[0]).toBe("nav-reserve");
    expect(buildSteps(s).length).toBeLessThanOrEqual(5);
    const list = buildChecklist(s)!;
    expect(list.total).toBeGreaterThan(0);
    expect(list.visible.length).toBeLessThanOrEqual(5);
  });

  it("GET /welcome (admin with planner + approver): admin cards first, 'Ayrıca' cards, at most 5", () => {
    const s = WelcomeState.parse(LIVE.admin);
    const sheet = buildSheet(s)!;
    expect(sheet.primary).toBe("admin");
    expect(sheet.cards.length).toBeLessThanOrEqual(5);
    expect(sheet.cards[0]!.key).toBe("users_roles");
    expect(sheet.cards.every((c) => !!c.href)).toBe(true);
  });

  it("admin endpoints: settings (nested), content (fields map), stats (all audiences, small groups)", () => {
    expect(WelcomeSettings.parse(LIVE.settings)).toMatchObject({ sheet: true, hints_for_all: false, min_cohort: 5 });
    const c = WelcomeContent.parse(LIVE.content);
    expect(c.version).toBe(0);
    expect(c.texts.tr).toEqual({});
    const st = WelcomeStats.parse(LIVE.stats);
    expect(st.rows).toHaveLength(7);
    expect(st.rows.every((r) => r.small_group)).toBe(true);
  });
});
