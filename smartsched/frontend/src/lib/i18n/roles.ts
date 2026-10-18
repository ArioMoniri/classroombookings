/**
 * Display names of roles and permissions (round-1 R1-M-16 / R1-A-10, T-R1-30). The stored role codes
 * (`ADMIN`, `PLANNER`, `TEACHER`, `VIEWER`, `CUSTOM`, `NONE`) and permission names (`book_single.create`) never
 * change; only what a person reads is localised:
 *
 * - a built-in role still carrying its shipped name ("Administrator", "Teacher", or the Turkish one) reads as
 *   `glass.role.<CODE>` ("Yönetici", "Öğretim elemanı"), like the sidebar footer;
 * - a built-in role an administrator renamed, and every custom role, keeps its own name.
 *
 * Mirrors the backend's `bookings_perms.role_label()` (TR/EN pair for e-mails and the sign-in hint).
 */
import { hasMessages, translate, type Locale, type MessageKey } from "./index";

export const BUILTIN_ROLES = ["ADMIN", "PLANNER", "TEACHER", "VIEWER"] as const;
export type BuiltinRole = (typeof BUILTIN_ROLES)[number];

/** the names the roles were seeded with (CRBS data.sql and earlier SmartSched seeds) */
const SHIPPED_NAMES: Record<BuiltinRole, readonly string[]> = {
  ADMIN: ["administrator", "admin"],
  PLANNER: ["planner"],
  TEACHER: ["teacher"],
  VIEWER: ["viewer"],
};

/**
 * The built-in roles' shipped names and descriptions in both languages (F-CH-1: the browser holds only the active
 * language's messages, and a role saved in the other language must still read as built-in). Kept equal to
 * `glass.role.*` / `glass.roleDescription.*` in messages/*.json by lazy-messages.test.tsx.
 */
export const SHIPPED_ROLE_TEXTS: Record<"tr" | "en", { name: Record<BuiltinRole, string>; description: Record<BuiltinRole, string> }> = {
  tr: {
    name: { ADMIN: "Yönetici", PLANNER: "Planlamacı", TEACHER: "Öğretim elemanı", VIEWER: "İzleyici" },
    description: {
      ADMIN: "Her izne sahip; kurulum, kullanıcılar ve roller",
      PLANNER: "Planlama birimi: içe aktarma, ders programları ve rezervasyonlar",
      TEACHER: "Öğretim elemanı: salonları görür ve rezervasyon yapar",
      VIEWER: "Planları ve rezervasyonları yalnızca görüntüler",
    },
  },
  en: {
    name: { ADMIN: "Administrator", PLANNER: "Planner", TEACHER: "Teacher", VIEWER: "Viewer" },
    description: {
      ADMIN: "Every permission: setup, users and roles",
      PLANNER: "Planning office: imports, timetables and bookings",
      TEACHER: "Teaching staff: views rooms and books them",
      VIEWER: "Read-only access to plans and bookings",
    },
  },
};

/** the shipped text in either language (and the active messages, which may carry an organisation's own) */
function isShippedText(kind: "name" | "description", code: BuiltinRole, folded: string): boolean {
  const key = (kind === "name" ? `glass.role.${code}` : `glass.roleDescription.${code}`) as MessageKey;
  return (["tr", "en"] as const).some((l) => fold(SHIPPED_ROLE_TEXTS[l][kind][code]) === folded || (hasMessages(l) && fold(translate(l, key)) === folded));
}

const isBuiltin = (code: string | null | undefined): code is BuiltinRole => !!code && (BUILTIN_ROLES as readonly string[]).includes(code);

const fold = (s: string) => s.trim().toLocaleLowerCase("tr-TR");

/** True when `name` is one of the names a built-in role ships with, in any offered language. */
function shippedName(code: BuiltinRole, name: string): boolean {
  const n = fold(name);
  if (SHIPPED_NAMES[code].includes(n)) return true;
  return isShippedText("name", code, n);
}

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

export interface RoleLike {
  /** a role row's `code` or a user's coarse `role` */
  code?: string | null;
  name?: string | null;
}

/** The role's name for people: `roleLabel(t, { code: "TEACHER", name: "Teacher" })` → "Öğretim elemanı". */
export function roleLabel(t: T, role: RoleLike | null | undefined): string {
  const code = role?.code ? role.code.toUpperCase() : null;
  const name = role?.name?.trim() ?? "";
  if (isBuiltin(code) && (!name || shippedName(code, name))) return t(`glass.role.${code}` as MessageKey);
  if (name) return name;
  if (code === "NONE") return t("glass.role.NONE");
  return code ? t(`glass.role.${code}` as MessageKey) : "";
}

/** the descriptions the roles were seeded with (`bookings_perms.ROLE_DEFAULTS`) */
const SHIPPED_DESCRIPTIONS: Record<BuiltinRole, readonly string[]> = {
  ADMIN: ["administrator"],
  PLANNER: ["planning office: imports, timetables and bookings"],
  TEACHER: ["teacher"],
  VIEWER: ["read-only access to plans and bookings"],
};

/** A built-in role's shipped description in the reader's language; anything an administrator wrote as it is. */
export function roleDescription(t: T, role: (RoleLike & { description?: string | null }) | null | undefined): string {
  const code = role?.code ? role.code.toUpperCase() : null;
  const text = role?.description?.trim() ?? "";
  if (!isBuiltin(code)) return text;
  const key = `glass.roleDescription.${code}` as MessageKey;
  const n = fold(text);
  if (!text || SHIPPED_DESCRIPTIONS[code].includes(n) || isShippedText("description", code, n) || shippedName(code, text)) return t(key);
  return text;
}

/** The same for one language (toasts raised after a language switch, e-mails composed in the browser). */
export function roleLabelIn(locale: Locale, role: RoleLike | null | undefined): string {
  return roleLabel((key, vars) => translate(locale, key, vars), role);
}

/** Translated label of a permission name (`book_single.create` → "Tek seferlik: oluşturma"); the backend's
 *  description, then the name, when no key exists. */
export function permissionLabel(t: T, name: string, description?: string | null): string {
  const flat = name.replace(".", "_");
  for (const key of [`crbs.perm.${flat}`, `approvals.perm.${flat}`] as MessageKey[]) {
    const out = t(key);
    if (out !== key) return out;
  }
  return description ?? name;
}

/** "a, b, c +2" of translated permission labels, short enough for an <option>. */
export function permissionList(t: T, names: readonly string[], max = 3): string {
  const labels = names.map((n) => permissionLabel(t, n));
  return labels.length > max ? `${labels.slice(0, max).join(", ")} +${labels.length - max}` : labels.join(", ");
}
