/**
 * Wave-1 setup screens (docs/product/wave1-api.md): approval rules (P1, `setup.rooms_acl`) and the audit log
 * (P7, `audit.view`). They sit beside the CRBS setup menu (`ADMIN_SECTIONS` in lib/permissions.ts) and are
 * merged into it by the admin gate, the /admin index, the breadcrumbs and ⌘K.
 */
import type { MessageKey } from "@/lib/i18n";
import { hasPermission, type AdminSection, type PermissionRequirement } from "@/lib/permissions";

export interface Wave1Section {
  id: "approval-rules" | "audit";
  href: `/admin/${string}`;
  labelKey: MessageKey;
  descriptionKey: MessageKey;
  permission: readonly string[];
  group: AdminSection["group"];
}

export const WAVE1_SECTIONS: readonly Wave1Section[] = [
  { id: "approval-rules", href: "/admin/approval-rules", labelKey: "wave1.rules.title", descriptionKey: "wave1.rules.lead", permission: ["setup.rooms_acl"], group: "rooms" },
  { id: "audit", href: "/admin/audit", labelKey: "wave1.audit.title", descriptionKey: "wave1.audit.lead", permission: ["audit.view"], group: "organisation" },
];

export function wave1SectionsFor(perms: readonly string[] | undefined | null): Wave1Section[] {
  return WAVE1_SECTIONS.filter((s) => hasPermission(perms, s.permission));
}

/** The permission a wave-1 setup route needs, or `undefined` when the path is not one of them. */
export function wave1Requirement(pathname: string): PermissionRequirement | undefined {
  return WAVE1_SECTIONS.find((s) => pathname === s.href || pathname.startsWith(`${s.href}/`))?.permission;
}
