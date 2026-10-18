/** HX-03 (helper.md §5.2, A6): the chip's state and why AI is off / who can turn it on. */
import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { HelperStatus } from "@/lib/api/helper";
import { chipState, StatusChip, type HelperMode } from "./status-chip";
import { renderHelper, resetHelperStore } from "./test-helpers";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
let perms: string[] = [];
vi.mock("@/lib/api/shell-extra", async (orig) => ({ ...(await orig<typeof import("@/lib/api/shell-extra")>()), usePermissions: () => ({ can: (p: string | string[]) => (Array.isArray(p) ? p : [p]).some((x) => perms.includes(x)), perms }) }));

const st = (over: Partial<HelperStatus>): HelperStatus => ({ mode: "ai", enabled: true, reason: null, provider_kind: "cloud", provider_label: { tr: "Anthropic (Claude)", en: "Anthropic (Claude)" }, fallback_active: false, message: null, ...over });
const mode = (status: HelperStatus, state = chipState(status, undefined, null)): HelperMode => ({ ai: status.mode === "ai", state, status, blocked: state === "limit", loading: false });

beforeEach(() => {
  resetHelperStore();
  perms = [];
});

describe("status chip", () => {
  it("derives the state from the server, the usage and the last turn", () => {
    expect(chipState(undefined, undefined, null)).toBe("off");
    expect(chipState(st({ mode: "index", reason: "not_routed" }), undefined, null)).toBe("off");
    expect(chipState(st({ provider_kind: "local" }), undefined, null)).toBe("local");
    expect(chipState(st({}), undefined, null)).toBe("cloud");
    expect(chipState(st({}), "hard", null)).toBe("limit");
    expect(chipState(st({}), undefined, "ai_faculty_limit_reached")).toBe("limit");
    expect(chipState(st({}), undefined, "provider_error")).toBe("fallback");
  });

  it("says the provider's name, from the routing config", () => {
    renderHelper(<StatusChip mode={mode(st({}))} />);
    expect(screen.getByTestId("helper-status")).toHaveTextContent("Bulut · Anthropic (Claude)");
  });

  it("AI off (not routed): why, and who can turn it on; an admin gets the link", () => {
    perms = ["setup.settings"];
    renderHelper(<StatusChip mode={mode(st({ mode: "index", reason: "not_routed", message: { tr: "Yardımcı şu an rehber modunda.", en: "Guide mode." } }))} />);
    expect(screen.getByTestId("helper-status")).toHaveTextContent("Yapay zekâ kapalı");
    fireEvent.click(screen.getByTestId("helper-status"));
    expect(screen.getByTestId("helper-status-body")).toHaveTextContent("Yardımcı şu an rehber modunda.");
    expect(screen.getByTestId("helper-status-who")).toHaveTextContent("kurumunuzun yöneticisi açar");
    expect(screen.getByTestId("helper-status-admin")).toBeInTheDocument();
  });

  it("consent missing: the person can turn it on (Profil › Gizlilik); no admin link for a teacher", () => {
    perms = ["book_single.create"];
    renderHelper(<StatusChip mode={mode(st({ mode: "index", reason: "consent_missing" }))} />);
    fireEvent.click(screen.getByTestId("helper-status"));
    expect(screen.getByTestId("helper-status-who")).toHaveTextContent("Bunu siz açabilirsiniz");
    expect(screen.getByRole("button", { name: "Gizlilik ayarlarını aç" })).toBeInTheDocument();
    expect(screen.queryByTestId("helper-status-admin")).toBeNull();
  });
});
