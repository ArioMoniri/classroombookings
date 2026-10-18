"use client";
/**
 * /admin/users (CRBS `Users`): search and filters, add/edit with role, department, names and the
 * force-password-change flag, per-user booking limits (R = role value, U = own value, X = unlimited),
 * one-time reset codes (shown once), delete, and the CSV import with a per-row result table.
 *
 * Microsoft sign-in (docs/design/v2/sign-in.md §13; parts in ./users-admin-identity): invite sheet, status
 * "dot + word" and sign-in method columns, "Kendi kaydı" filter, "Sonraki Microsoft girişinde bağla", the
 * break-glass warning, the edit dialog's identities section and the instructor link.
 */
import { Copy, Mail, MoreHorizontal, Pencil, ShieldQuestion, Trash2, Upload, UserPlus } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Chip } from "@/components/ui/chip";
import { Button } from "@/components/ui/button";
import { BusyLabel } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { SlidersHorizontal } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { useIsPhone } from "@/components/bookings/use-is-phone";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  crbs,
  crbsError,
  LIMIT_KEYS,
  useCrbsMutation,
  useDepartments,
  useRoles,
  useUserConstraints,
  useUserSearch,
  type AdminUser,
  type Constraints,
  type ImportResult,
  type LimitKey,
  type ResetToken,
  type UserIn,
} from "@/lib/api/crbs";
import { canManageAccount, isPrivilegedRole, roleGrantCheck, usePermissions } from "@/lib/permissions";
import { useAuthProviders, useInvites, useUserIdentityStatus, type Invite, type UserIdentityStatus } from "@/lib/api/identity";
import { invitePrefill, roleValueFor, type InvitePrefill } from "@/lib/handover";
import { BindDialog, BreakGlassWarning, IdentitiesSection, IdentityMenuItems, IdentityStatusCell, IdentityTags, InviteSheet, MethodCell, RevokeDialog } from "./users-admin-identity";
import { breakGlassMissing, identityQuery, invitesByUser, methodView, statusView, type IdentityFilter, type MethodFilter } from "./users-admin-identity-model";
import { matchesMfaFilter, MfaFilterSelect, MfaMethodTag, mfaListState, securityAccount, useUserSecurity, type MfaFilter, type SecurityUser } from "./users-security";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { permissionList, roleLabel } from "@/lib/i18n/roles";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import { useBookingFormat } from "@/components/bookings/use-booking-format";
import { Alert, ConfirmDialog, Field, Loading, PageTitle, SelectField } from "./kit";
import { useErrorToast } from "./admin-gate";
import { handedFile, useHelperFileHandoff } from "@/components/helper/file-handoff";
import { HandedFileRow } from "@/components/helper/handed-file-row";
import { HelperFileLink } from "@/components/helper/file-link";
import { normaliseScopes } from "@/components/approvals/approvals-model";
import { ScopePicker, scopeLabel, useScopeLookups } from "@/components/approvals/scope-picker";
import type { Scope } from "@/lib/api/wave1";

const PAGE = 25;
const SEEDED = [
  { code: "ADMIN", key: "crbs.users.roleAdmin" },
  { code: "PLANNER", key: "crbs.users.rolePlanner" },
  { code: "VIEWER", key: "crbs.users.roleViewer" },
  { code: "TEACHER", key: "crbs.users.roleTeacher" },
] as const;

/** filter chips: 36 px on touch plus a 4 px hit extension above and below, so the target is 44 px */
const TOUCH_CHIP = "pointer-coarse:h-9 relative after:absolute after:inset-x-0 after:-inset-y-1";

export function UsersAdmin() {
  const { t } = useI18n();
  const { can, perms, userId } = usePermissions();
  // ?role=<id> (the role editor's "all users" link), ?department=<id> and ?q= preset the filters
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [q, setQ] = useState(() => params.get("q") ?? "");
  // HX-06 hand-over: ?invite=1&email=&name=&role=&department= are the invite's fields, not the list filters
  const [handover] = useState(() => invitePrefill(params));
  const [role, setRole] = useState(() => (handover ? "" : (params.get("role") ?? "").replace(/\D/g, "")));
  const [dept, setDept] = useState(() => (handover ? "" : (params.get("department") ?? "").replace(/\D/g, "")));
  const [enabled, setEnabled] = useState(() => (params.get("enabled") === "1" || params.get("enabled") === "0" ? params.get("enabled")! : ""));
  const [sort, setSort] = useState("username");
  const [page, setPage] = useState(0);
  const prevRef = useRef<HTMLButtonElement>(null);
  const nextRef = useRef<HTMLButtonElement>(null);
  const [idFilter, setIdFilter] = useState<IdentityFilter>(() => (params.get("identity") === "invited" ? "invited" : params.get("identity") === "self" ? "self" : "all"));
  const [method, setMethod] = useState<MethodFilter>(() => (["microsoft", "local", "ldap", "binding"].includes(params.get("method") ?? "") ? (params.get("method") as MethodFilter) : ""));
  // T-R1-33: the filters live in the address (?role=&q=&department=&enabled=&identity=&method=), so a reload or a
  // shared link keeps them; only the keys this screen owns are rewritten
  useEffect(() => {
    const next = new URLSearchParams(params.toString());
    const own: Record<string, string> = { q, role, department: dept, enabled, identity: idFilter === "all" ? "" : idFilter, method };
    let changed = false;
    for (const [k, v] of Object.entries(own)) {
      if ((next.get(k) ?? "") === v) continue;
      changed = true;
      if (v) next.set(k, v);
      else next.delete(k);
    }
    if (changed) router.replace(next.size ? `${pathname}?${next.toString()}` : pathname, { scroll: false });
  }, [q, role, dept, enabled, idFilter, method, params, pathname, router]);
  // the 2FA filter (AU-18 mfa_state) is a server parameter too (RF-B `mfa_state=`): total and paging cover every page
  const [mfaFilter, setMfaFilter] = useState<MfaFilter>("");
  const phone = useIsPhone();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const activeFilters = [role, dept, enabled, idFilter === "all" ? "" : idFilter, method, mfaFilter].filter(Boolean).length;
  const usersAdmin = can("setup.users");
  // the identity chips and the method select filter on the server (`identity=`, `self_signup_days=7`), with
  // server paging and the server's total; only setup.users sees the identity columns, so only they filter by it
  const base = { q: q || undefined, role_id: role ? Number(role) : undefined, department_id: dept ? Number(dept) : undefined, enabled: enabled === "" ? undefined : enabled === "1" };
  const query = { ...base, ...(usersAdmin ? identityQuery(idFilter, method) : {}), ...(usersAdmin && mfaFilter ? { mfa_state: mfaFilter } : {}), sort, limit: PAGE, offset: page * PAGE };
  const users = useUserSearch(query);
  // the chip counts: the server's totals for the same filters (limit 1)
  const invitedCount = useUserSearch({ ...base, ...identityQuery("invited", ""), limit: 1 }, usersAdmin);
  const selfCount = useUserSearch({ ...base, ...identityQuery("self", ""), limit: 1 }, usersAdmin);
  const providers = useAuthProviders();
  const auth = providers.data?.auth;
  const msEnabled = Boolean(auth?.microsoft.enabled);
  const idStatus = useUserIdentityStatus(usersAdmin);
  const invites = useInvites(usersAdmin);
  const inviteOf = invitesByUser(invites.data);
  const statusOf = (u: AdminUser): UserIdentityStatus | undefined => idStatus.data?.[String(u.id)];
  const counts = { invited: invitedCount.data?.total ?? 0, selfRecent: selfCount.data?.total ?? 0 };
  const [inviteOpen, setInviteOpen] = useState(false);
  // the hand-over opens the invite sheet (Microsoft on) or "Yeni kullanıcı", prefilled; it never sends anything.
  // Once opened, its keys leave the address, so a reload does not reopen it.
  const [handoverOpened, setHandoverOpened] = useState(false);
  const [binding, setBinding] = useState<AdminUser | null>(null);
  const [revoking, setRevoking] = useState<{ invite: Invite; kind: "invite" | "bind" } | null>(null);
  const nameOf = (id: number | null | undefined) => {
    const hit = id ? users.data?.items.find((x) => x.id === id) : undefined;
    return hit ? hit.displayname || hit.full_name || hit.username || hit.email || null : null;
  };
  const visible = users.data?.items ?? [];
  const privileged = (u: AdminUser) => u.role === "ADMIN" || isPrivilegedRole(roles.data?.find((r) => r.id === u.role_id)) || (u.approves_for?.length ?? 0) > 0;
  const roles = useRoles(can("setup.roles"));
  const departments = useDepartments();
  const [editing, setEditing] = useState<AdminUser | "new" | null>(null);
  useEffect(() => {
    if (!handover || handoverOpened || providers.isPending) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- a one-off hand-over read from the address once the sign-in methods are known
    setHandoverOpened(true);
    if (usersAdmin) setInviteOpen(true); // E2EA-F10: a local-password invite when Microsoft is off
    else setEditing("new");
    const next = new URLSearchParams(window.location.search);
    for (const k of ["invite", "email", "name"]) next.delete(k);
    router.replace(next.size ? `${pathname}?${next.toString()}` : pathname, { scroll: false });
  }, [handover, handoverOpened, providers.isPending, usersAdmin, router, pathname]);
  // HB-23c: ?import=1 (the helper's "Kullanıcıları içe aktar") opens the import sheet once; the key leaves the address
  const [importOpen, setImportOpen] = useState(() => params.get("import") === "1");
  useEffect(() => {
    if (params.get("import") !== "1") return;
    const next = new URLSearchParams(window.location.search);
    for (const k of ["import", "from"]) next.delete(k);
    router.replace(next.size ? `${pathname}?${next.toString()}` : pathname, { scroll: false });
  }, [params, router, pathname]);
  const [token, setToken] = useState<{ user: AdminUser; token: ResetToken } | null>(null);
  const [deleting, setDeleting] = useState<AdminUser | null>(null);
  const toastError = useErrorToast();
  const reset = useCrbsMutation((u: AdminUser) => crbs.users.resetToken(u.id));
  const del = useCrbsMutation((u: AdminUser) => crbs.users.remove(u.id), [["crbs", "users"]]);
  const total = users.data?.total ?? 0;
  const manageable = (u: AdminUser) => canManageAccount(perms, userId, { id: u.id, role: u.role, role_permissions: roles.data?.find((r) => r.id === u.role_id)?.permissions });
  const fmt = useBookingFormat();
  const dt = (iso: string | null | undefined) => fmt.dateTime(iso) || "—";
  // AUX-08 (auth.md §7): the "Giriş" menu group, the edit sheet's "Giriş ve güvenlik" block and their dialogs;
  // "Sıfırlama kodunu ekranda göster" is the old one-time reset code
  const showCode = (id: number) => {
    const u = visible.find((x) => x.id === id) ?? (editing && editing !== "new" && editing.id === id ? editing : null);
    if (u) reset.mutate(u, { onSuccess: (tok) => setToken({ user: u, token: tok }), onError: toastError });
  };
  const security = useUserSecurity({ meId: userId, onShowCode: showCode });
  const mfaGrace = (u: AdminUser) => statusOf(u)?.mfa_grace_until ?? null;
  const secUser = (u: AdminUser): SecurityUser => {
    const m = methodView(statusOf(u), u.auth_source);
    return { id: u.id, name: u.displayname || u.full_name || u.username || u.email || "", email: u.email, account: securityAccount(m), providerName: m === "microsoft" || m === "microsoftInvite" ? "Microsoft" : null, mfa: mfaListState(statusOf(u)), role: u.role, lastLoginAt: u.last_login_at };
  };
  // the filter is applied by the server; a row whose known state in the status map disagrees (the map refreshed
  // while the page was cached) is still left out, an unknown state is trusted to the server
  const mfaKnown = usersAdmin && Object.values(idStatus.data ?? {}).some((x) => mfaListState(x) !== null);
  const rows = mfaKnown && mfaFilter ? visible.filter((u) => { const s = mfaListState(statusOf(u)); return s === null || matchesMfaFilter(s, mfaFilter); }) : visible;

  return (
    <div className="flex flex-col gap-5">
      {/* phones (T-R1-33, R1-M-30): the three actions sit as icon buttons beside the title, so the first user card
          starts above 300 px; their names are the accessible labels */}
      <PageTitle
        className={phone ? "max-sm:mb-2 max-sm:flex-row max-sm:items-start max-sm:justify-between" : undefined}
        title={t("crbs.admin.users.title")}
        subtitle={
          users.data
            ? [t("crbs.users.count", { n: users.data.total }), idStatus.data && counts.invited ? t("sso.users.countInvited", { n: counts.invited }) : null, idStatus.data && counts.selfRecent ? t("sso.users.countSelf", { n: counts.selfRecent }) : null].filter(Boolean).join(" · ")
            : t("crbs.admin.users.lead")
        }
        actions={
          <>
            <Button variant="outline" size={phone ? "icon" : "default"} onClick={() => setImportOpen(true)} data-testid="users-import" aria-label={phone ? t("crbs.users.import") : undefined} title={phone ? t("crbs.users.import") : undefined}>
              <Upload aria-hidden />
              {phone ? null : t("crbs.users.import")}
            </Button>
            {/* local accounts are the exception once Microsoft is on (break-glass, service accounts) */}
            {/* HX12B-F15 (fix-h-2026-10-18): on a phone the screen's one primary keeps its words ("Yeni kullanıcı", or
                "Davet et" once Microsoft is on); only the secondary actions shrink to labelled icons */}
            <Button variant={msEnabled && usersAdmin ? "outline" : "default"} size={phone && msEnabled && usersAdmin ? "icon" : "default"} className={phone && !(msEnabled && usersAdmin) ? "min-h-11 rounded-full px-4" : undefined} onClick={() => setEditing("new")} data-testid="users-new" data-tour={msEnabled && usersAdmin ? undefined : "admin-users-invite"} aria-label={phone && msEnabled && usersAdmin ? t("sso.users.createLocal") : undefined} title={phone && msEnabled && usersAdmin ? t("sso.users.createLocal") : undefined}>
              <UserPlus aria-hidden />
              {phone && msEnabled && usersAdmin ? null : msEnabled && usersAdmin ? t("sso.users.createLocal") : t("crbs.users.new")}
            </Button>
            {msEnabled && usersAdmin ? (
              <Button className={phone ? "min-h-11 rounded-full px-4" : undefined} onClick={() => setInviteOpen(true)} data-testid="users-invite" data-tour="admin-users-invite">
                <Mail aria-hidden />
                {t("sso.users.inviteAction")}
              </Button>
            ) : usersAdmin ? (
              // E2EA-F10 (FIX-K): with password sign-in only, "Davet et" sends a link where the person sets a password;
              // "Yeni kullanıcı" stays the one primary
              <Button variant="outline" size={phone ? "icon" : "default"} onClick={() => setInviteOpen(true)} data-testid="users-invite" aria-label={phone ? t("sso.users.inviteAction") : undefined} title={phone ? t("sso.users.inviteAction") : undefined}>
                <Mail aria-hidden />
                {phone ? null : t("sso.users.inviteAction")}
              </Button>
            ) : null}
          </>
        }
      />
      {breakGlassMissing(auth, idStatus.data) ? <BreakGlassWarning onCreateLocal={() => setEditing("new")} /> : null}
      {/* T-R1-33 (R1-M-30): on a phone the five filter controls sit in a bottom sheet behind one "Filtreler · n"
          trigger (MOBILE.md M-04), so the first user card starts above 300 px; the search box stays on the page */}
      {phone ? (
        <div className="flex items-center gap-2">
          <div className="min-w-0 flex-1">
            <Input
              type="search"
              aria-label={t("crbs.users.search")}
              placeholder={t("crbs.users.searchHint")}
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(0);
              }}
              data-testid="users-search"
            />
          </div>
          <Button variant="outline" onClick={() => setFiltersOpen(true)} aria-haspopup="dialog" data-testid="users-filters-open">
            <SlidersHorizontal aria-hidden />
            {activeFilters ? t("crbs.users.filterOpenCount", { n: activeFilters }) : t("crbs.users.filterOpen")}
          </Button>
        </div>
      ) : (
        <>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr_1fr]">
            <Input
              type="search"
              aria-label={t("crbs.users.search")}
              placeholder={t("crbs.users.searchHint")}
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(0);
              }}
              data-testid="users-search"
            />
            <SelectField aria-label={t("crbs.users.role")} data-testid="users-role-filter" value={role} onChange={(e) => (setRole(e.target.value), setPage(0))}>
              <option value="">{t("crbs.users.allRoles")}</option>
              {(roles.data ?? []).map((r) => (
                <option key={r.id} value={r.id}>
                  {roleLabel(t, r)}
                </option>
              ))}
            </SelectField>
            <SelectField aria-label={t("crbs.users.department")} value={dept} onChange={(e) => (setDept(e.target.value), setPage(0))}>
              <option value="">{t("crbs.users.allDepartments")}</option>
              {(departments.data ?? []).map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </SelectField>
            <SelectField aria-label={t("crbs.users.status")} value={enabled} onChange={(e) => (setEnabled(e.target.value), setPage(0))}>
              <option value="">{t("crbs.users.anyStatus")}</option>
              <option value="1">{t("crbs.users.enabled")}</option>
              <option value="0">{t("crbs.users.disabled")}</option>
            </SelectField>
            <SelectField aria-label={t("crbs.users.sort")} data-testid="users-sort" value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="username">{t("crbs.users.sortUsername")}</option>
              <option value="displayname">{t("crbs.users.sortName")}</option>
              <option value="-lastlogin">{t("crbs.users.sortLogin")}</option>
              <option value="role">{t("crbs.users.sortRole")}</option>
              {/* CRBS users_index sortable columns: enabled and department too (backend sort_map; UI gap audit #22) */}
              <option value="-enabled,username">{t("admingaps.users.sortEnabled")}</option>
              <option value="department,username">{t("admingaps.users.sortDepartment")}</option>
            </SelectField>
          </div>
          {usersAdmin && idStatus.data ? (
            <div className="flex flex-wrap items-center gap-2" role="group" aria-label={t("sso.users.filters")} data-testid="identity-filters">
              <Chip className={TOUCH_CHIP} selected={idFilter === "all" && enabled !== "0"} onSelectedChange={() => (setIdFilter("all"), setMethod(""), setEnabled(""), setPage(0))}>
                {t("sso.users.filterAll")}
              </Chip>
              <Chip className={TOUCH_CHIP} selected={idFilter === "invited"} onSelectedChange={(on) => (setIdFilter(on ? "invited" : "all"), on && setMethod(""), setPage(0))} data-testid="filter-invited">
                {t("sso.users.filterInvited", { n: counts.invited })}
              </Chip>
              <Chip className={TOUCH_CHIP} selected={idFilter === "self"} onSelectedChange={(on) => (setIdFilter(on ? "self" : "all"), on && setMethod(""), setPage(0))} data-testid="filter-self">
                {t("sso.users.filterSelf", { n: counts.selfRecent })}
              </Chip>
              <Chip className={TOUCH_CHIP} selected={enabled === "0"} onSelectedChange={(on) => (setEnabled(on ? "0" : ""), setPage(0))}>
                {t("sso.users.status.disabled")}
              </Chip>
              <SelectField aria-label={t("sso.users.methodFilter")} className="w-auto min-w-44" value={method} onChange={(e) => (setMethod(e.target.value as MethodFilter), e.target.value && setIdFilter("all"), setPage(0))} data-testid="filter-method">
                <option value="">{t("sso.users.methodFilter")}</option>
                <option value="microsoft">{t("sso.users.method.microsoft")}</option>
                <option value="local">{t("sso.users.method.local")}</option>
                <option value="ldap">{t("sso.users.method.ldap")}</option>
                <option value="binding">{t("sso.users.status.binding")}</option>
              </SelectField>
              {mfaKnown ? <MfaFilterSelect value={mfaFilter} onChange={(v) => (setMfaFilter(v), setPage(0))} className="min-w-44" /> : null}
            </div>
          ) : null}
        </>
      )}
      <Sheet open={phone && filtersOpen} onOpenChange={setFiltersOpen}>
        <SheetContent side="bottom" className="gap-0 data-[side=bottom]:max-h-[92dvh]" data-testid="users-filters-sheet">
          <SheetHeader className="px-5 pt-5">
            <SheetTitle className="type-title-3">{t("crbs.users.filtersTitle")}</SheetTitle>
            <SheetDescription className="sr-only">{t("crbs.admin.users.lead")}</SheetDescription>
          </SheetHeader>
          <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto overscroll-contain px-5 pt-4 pb-2">
            <div className="grid gap-2">
              <SelectField aria-label={t("crbs.users.role")} data-testid="users-role-filter" value={role} onChange={(e) => (setRole(e.target.value), setPage(0))}>
                <option value="">{t("crbs.users.allRoles")}</option>
                {(roles.data ?? []).map((r) => (
                  <option key={r.id} value={r.id}>
                    {roleLabel(t, r)}
                  </option>
                ))}
              </SelectField>
              <SelectField aria-label={t("crbs.users.department")} value={dept} onChange={(e) => (setDept(e.target.value), setPage(0))}>
                <option value="">{t("crbs.users.allDepartments")}</option>
                {(departments.data ?? []).map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </SelectField>
              <SelectField aria-label={t("crbs.users.status")} value={enabled} onChange={(e) => (setEnabled(e.target.value), setPage(0))}>
                <option value="">{t("crbs.users.anyStatus")}</option>
                <option value="1">{t("crbs.users.enabled")}</option>
                <option value="0">{t("crbs.users.disabled")}</option>
              </SelectField>
              <SelectField aria-label={t("crbs.users.sort")} data-testid="users-sort" value={sort} onChange={(e) => setSort(e.target.value)}>
                <option value="username">{t("crbs.users.sortUsername")}</option>
                <option value="displayname">{t("crbs.users.sortName")}</option>
                <option value="-lastlogin">{t("crbs.users.sortLogin")}</option>
                <option value="role">{t("crbs.users.sortRole")}</option>
                {/* CRBS users_index sortable columns: enabled and department too (backend sort_map; UI gap audit #22) */}
                <option value="-enabled,username">{t("admingaps.users.sortEnabled")}</option>
                <option value="department,username">{t("admingaps.users.sortDepartment")}</option>
              </SelectField>
            </div>
            {usersAdmin && idStatus.data ? (
              <div className="flex flex-wrap items-center gap-2" role="group" aria-label={t("sso.users.filters")} data-testid="identity-filters">
                <Chip className={TOUCH_CHIP} selected={idFilter === "all" && enabled !== "0"} onSelectedChange={() => (setIdFilter("all"), setMethod(""), setEnabled(""), setPage(0))}>
                  {t("sso.users.filterAll")}
                </Chip>
                <Chip className={TOUCH_CHIP} selected={idFilter === "invited"} onSelectedChange={(on) => (setIdFilter(on ? "invited" : "all"), on && setMethod(""), setPage(0))} data-testid="filter-invited">
                  {t("sso.users.filterInvited", { n: counts.invited })}
                </Chip>
                <Chip className={TOUCH_CHIP} selected={idFilter === "self"} onSelectedChange={(on) => (setIdFilter(on ? "self" : "all"), on && setMethod(""), setPage(0))} data-testid="filter-self">
                  {t("sso.users.filterSelf", { n: counts.selfRecent })}
                </Chip>
                <Chip className={TOUCH_CHIP} selected={enabled === "0"} onSelectedChange={(on) => (setEnabled(on ? "0" : ""), setPage(0))}>
                  {t("sso.users.status.disabled")}
                </Chip>
                <SelectField aria-label={t("sso.users.methodFilter")} className="w-auto min-w-44" value={method} onChange={(e) => (setMethod(e.target.value as MethodFilter), e.target.value && setIdFilter("all"), setPage(0))} data-testid="filter-method">
                  <option value="">{t("sso.users.methodFilter")}</option>
                  <option value="microsoft">{t("sso.users.method.microsoft")}</option>
                  <option value="local">{t("sso.users.method.local")}</option>
                  <option value="ldap">{t("sso.users.method.ldap")}</option>
                  <option value="binding">{t("sso.users.status.binding")}</option>
                </SelectField>
              {mfaKnown ? <MfaFilterSelect value={mfaFilter} onChange={(v) => (setMfaFilter(v), setPage(0))} className="min-w-44" /> : null}
              </div>
            ) : null}
          </div>
          <SheetFooter className="hairline-t flex-row justify-end gap-2 px-5 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
            <Button variant="ghost" onClick={() => (setRole(""), setDept(""), setEnabled(""), setIdFilter("all"), setMethod(""), setPage(0))}>
              {t("wave1.audit.reset")}
            </Button>
            <Button onClick={() => setFiltersOpen(false)} data-testid="users-filters-apply">
              {t("crbs.users.apply")}
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>
      <Card variant="glass" className="py-0">
        {users.isLoading ? (
          <Loading className="px-4" />
        ) : (
          <Table data-testid="users-table">
            <TableHeader className={phone ? "sr-only" : undefined}>
              <TableRow>
                <TableHead className="pl-4">{t("crbs.users.name")}</TableHead>
                <TableHead className="hidden md:table-cell">{t("crbs.users.email")}</TableHead>
                <TableHead className="hidden sm:table-cell">{t("crbs.users.role")}</TableHead>
                {usersAdmin && idStatus.data ? <TableHead className="hidden lg:table-cell">{t("sso.users.methodColumn")}</TableHead> : null}
                {usersAdmin && idStatus.data ? <TableHead className="hidden sm:table-cell">{t("sso.users.statusColumn")}</TableHead> : null}
                <TableHead className="hidden xl:table-cell">{t("crbs.users.department")}</TableHead>
                <TableHead className="hidden lg:table-cell">{t("crbs.users.lastLogin")}</TableHead>
                <TableHead className="w-10 pr-4">
                  <span className="sr-only">{t("crbs.common.actions")}</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((u) => (
                <TableRow key={u.id} data-username={u.username ?? u.email ?? ""}>
                  <TableCell className="pl-4 whitespace-normal [overflow-wrap:anywhere]">
                    <span className="block font-medium text-label-1">
                      {u.displayname || u.full_name || u.username || u.email}
                      <IdentityTags s={statusOf(u)} />
                    </span>
                    <span className="block type-footnote text-label-3">
                      {/* the e-mail has its own column from md up: show it here only on phones (UI/UX review: e-mail twice) */}
                      {u.username ?? <span className="md:hidden">{u.email}</span>}
                      {u.auth_source === "ldap" ? " · LDAP" : ""}
                    </span>
                    {/* phones: the role column is hidden, so the role (and the privileged mark) reads under the name */}
                    <span className="block type-footnote text-label-2 sm:hidden" data-testid="user-role-inline">
                      {u.role_name ? roleLabel(t, { code: u.role, name: u.role_name }) : t("crbs.users.noRole")}
                      {!manageable(u) ? ` · ${t("crbs.users.privileged")}` : ""}
                    </span>
                    {/* phones: the status column is hidden, so a pending / expired / disabled state shows here */}
                    {usersAdmin && idStatus.data && statusView(statusOf(u), u.is_active).word !== "active" ? (
                      <span className="mt-1 block sm:hidden">
                        <IdentityStatusCell view={statusView(statusOf(u), u.is_active)} />
                      </span>
                    ) : null}
                  </TableCell>
                  <TableCell className="hidden text-label-2 md:table-cell">{u.email ?? "—"}</TableCell>
                  <TableCell className="hidden sm:table-cell">
                    <span className="text-label-1">{u.role_name ? roleLabel(t, { code: u.role, name: u.role_name }) : t("crbs.users.noRole")}</span>
                    {!u.is_active ? (
                      <Badge tone="preoccupied" variant="secondary" className="ml-2">
                        {t("crbs.users.disabled")}
                      </Badge>
                    ) : u.force_password_reset ? (
                      <Badge tone="warning" variant="secondary" className="ml-2">
                        {t("crbs.users.mustChange")}
                      </Badge>
                    ) : null}
                    {!manageable(u) ? (
                      <Badge tone="locked" variant="secondary" className="ml-2" title={t("crbs.users.privilegedHint")} data-testid="user-privileged">
                        {t("crbs.users.privileged")}
                      </Badge>
                    ) : null}
                  </TableCell>
                  {usersAdmin && idStatus.data ? (
                    <TableCell className="hidden lg:table-cell">
                      <MethodCell m={methodView(statusOf(u), u.auth_source)} />
                      <MfaMethodTag state={mfaListState(statusOf(u))} graceUntil={mfaGrace(u)} />
                    </TableCell>
                  ) : null}
                  {usersAdmin && idStatus.data ? (
                    <TableCell className="hidden sm:table-cell">
                      <IdentityStatusCell view={statusView(statusOf(u), u.is_active)} inviterName={nameOf(statusOf(u)?.invite?.invited_by)} />
                    </TableCell>
                  ) : null}
                  <TableCell className="hidden text-label-2 xl:table-cell">{u.department_name ?? "—"}</TableCell>
                  <TableCell className="hidden text-label-2 tabular-nums lg:table-cell">{dt(u.last_login_at)}</TableCell>
                  <TableCell className="pr-4 text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" className="pointer-coarse:size-(--control-h-md)" aria-label={t("crbs.users.actionsFor", { name: u.username ?? u.email ?? "" })} />}>
                        <MoreHorizontal />
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        {!manageable(u) ? <p className="max-w-60 px-2 py-1 type-footnote text-label-2">{t("crbs.users.privilegedHint")}</p> : null}
                        <DropdownMenuItem disabled={!manageable(u)} onClick={() => setEditing(u)}>
                          <Pencil aria-hidden />
                          {t("crbs.common.edit")}
                        </DropdownMenuItem>
                        {/* CRBS users_add_side: the access checker for this person (UI gap audit #15) */}
                        <DropdownMenuItem onClick={() => router.push(`/admin/access?user=${u.id}`)} data-testid={`user-check-access-${u.id}`}>
                          <ShieldQuestion aria-hidden />
                          {t("admingaps.access.check")}
                        </DropdownMenuItem>
                        {usersAdmin ? <IdentityMenuItems user={u} s={statusOf(u)} invite={inviteOf.get(u.id)} canManage={manageable(u)} msEnabled={msEnabled} onBind={setBinding} onRevoke={(invite, kind) => setRevoking({ invite, kind })} /> : null}
                        {usersAdmin && manageable(u) ? security.menuItems(secUser(u)) : null}
                        <DropdownMenuSeparator />
                        <DropdownMenuItem variant="destructive" disabled={!manageable(u)} onClick={() => setDeleting(u)}>
                          <Trash2 aria-hidden />
                          {t("crbs.common.delete")}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
              {users.data && rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="px-4 py-6 text-label-2">
                    {t("crbs.users.none")}
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        )}
      </Card>
      {/* HB-23c (helper-file-router.md §8.4): only the admin so far, no filter: the helper reads a user list */}
      {users.data && total === 1 && !q && !role && !dept && !enabled ? <HelperFileLink /> : null}
      {total > PAGE ? (
        <div className="flex items-center justify-between type-callout text-label-2">
          <span>{t("crbs.users.page", { from: page * PAGE + 1, to: Math.min(total, (page + 1) * PAGE), total })}</span>
          <div className="flex gap-2">
            {/* E2EA2-F03: the pressed button disables itself on the first / last page, so focus moves to the other one */}
            <Button ref={prevRef} className="pointer-coarse:h-11" variant="ghost" size="sm" disabled={page === 0} onClick={() => (setPage((p) => p - 1), page - 1 === 0 && requestAnimationFrame(() => nextRef.current?.focus()))}>
              {t("crbs.users.prev")}
            </Button>
            <Button ref={nextRef} className="pointer-coarse:h-11" variant="ghost" size="sm" disabled={(page + 1) * PAGE >= total} onClick={() => (setPage((p) => p + 1), (page + 2) * PAGE >= total && requestAnimationFrame(() => prevRef.current?.focus()))}>
              {t("crbs.users.next")}
            </Button>
          </div>
        </div>
      ) : null}

      <UserDialog
        user={editing}
        prefill={handover}
        onClose={() => setEditing(null)}
        canListRoles={can("setup.roles")}
        identityFor={(u) => (usersAdmin ? { s: statusOf(u), invite: inviteOf.get(u.id), msEnabled, onBind: () => (setEditing(null), setBinding(u)), security: manageable(u) ? security.block(secUser(u)) : null } : null)}
      />
      {security.dialogs}
      <InviteSheet open={inviteOpen} onOpenChange={setInviteOpen} auth={auth} canListRoles={can("setup.roles")} prefill={handover} local={!msEnabled} />
      <BindDialog key={binding?.id ?? "none"} user={binding} privileged={!!binding && privileged(binding)} onClose={() => setBinding(null)} />
      <RevokeDialog value={revoking} onClose={() => setRevoking(null)} />
      <ImportDialog open={importOpen} onOpenChange={setImportOpen} canListRoles={can("setup.roles")} />
      <TokenDialog value={token} onClose={() => setToken(null)} />
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t("crbs.users.deleteTitle", { name: deleting?.username ?? deleting?.email ?? "" })}
        description={t("crbs.users.deleteBody")}
        confirmLabel={t("crbs.common.delete")}
        destructive
        busy={del.isPending}
        onConfirm={() =>
          deleting &&
          del.mutate(deleting, {
            onSuccess: () => {
              toast.success(t("crbs.common.deleted"));
              setDeleting(null);
            },
            onError: toastError,
          })
        }
      />
    </div>
  );
}

/**
 * Role picker for user create/edit and the CSV default role. No escalation (backend rule): a role whose
 * permissions are not all held by the current user is disabled, with what is missing. Without setup.roles
 * the role list is not readable, so only the seeded codes are offered and only Administrator is known to be
 * out of reach; the backend's 403 explains anything else.
 */
function RoleSelect({ value, onChange, canListRoles, id, error }: { value: string; onChange: (v: string) => void; canListRoles: boolean; id?: string; error?: string | null }) {
  const { t } = useI18n();
  const { perms } = usePermissions();
  const roles = useRoles(canListRoles);
  const options = roles.data
    ? roles.data.map((r) => ({ value: `id:${r.id}`, label: roleLabel(t, r), check: roleGrantCheck(perms, r) }))
    : SEEDED.map((r) => ({ value: `code:${r.code}`, label: t(r.key as MessageKey), check: roleGrantCheck(perms, { code: r.code }) }));
  const anyDisabled = options.some((o) => !o.check.allowed);
  // T-R2-32 (R2-M-20, F-11 S01): a missing role is said next to the field, read with it (aria-describedby), not only
  // in the form's alert
  const describedBy = [error && id ? `${id}-error` : null, anyDisabled && id ? `${id}-hint` : null].filter(Boolean).join(" ") || undefined;
  return (
    <>
      <SelectField id={id} value={value} onChange={(e) => onChange(e.target.value)} aria-describedby={describedBy} aria-invalid={error ? true : undefined}>
        <option value="">{t("crbs.users.pickRole")}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value} disabled={!o.check.allowed && o.value !== value}>
            {o.check.allowed ? o.label : t("crbs.users.roleMissing", { role: o.label, list: permissionList(t, o.check.missing) })}
          </option>
        ))}
      </SelectField>
      {error ? (
        <p id={id ? `${id}-error` : undefined} className="type-footnote text-status-infeasible-fg" role="alert" data-testid="role-error">
          {error}
        </p>
      ) : null}
      {anyDisabled ? (
        <p id={id ? `${id}-hint` : undefined} className="type-footnote text-label-3" data-testid="role-disabled-hint">
          {t("crbs.users.roleDisabledHint")}
        </p>
      ) : null}
    </>
  );
}

function roleBody(v: string): Pick<UserIn, "role_id"> & { role?: string } {
  if (v.startsWith("id:")) return { role_id: Number(v.slice(3)) };
  if (v.startsWith("code:")) return { role: v.slice(5) };
  return {};
}

type IdentityProps = { s: UserIdentityStatus | undefined; invite: Invite | undefined; msEnabled: boolean; onBind: () => void; security?: ReactNode } | null;

function UserDialog({ user, onClose, canListRoles, identityFor, prefill = null }: { user: AdminUser | "new" | null; onClose: () => void; canListRoles: boolean; identityFor: (u: AdminUser) => IdentityProps; /** HX-06: a new user's fields from the invite hand-over */ prefill?: InvitePrefill | null }) {
  return (
    <Dialog open={user !== null} onOpenChange={(o) => !o && onClose()}>
      {/* a new user (the button or the `?invite=1` hand-over): focus goes back to "Yeni kullanıcı" */}
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-xl lg:max-w-2xl" finalFocus={user === "new" ? () => document.querySelector<HTMLElement>('[data-testid="users-new"]') ?? true : undefined} data-testid="user-dialog">
        {user !== null ? <UserForm key={user === "new" ? "new" : user.id} user={user === "new" ? null : user} onClose={onClose} canListRoles={canListRoles} identity={user === "new" ? null : identityFor(user)} prefill={user === "new" ? prefill : null} /> : null}
      </DialogContent>
    </Dialog>
  );
}

function UserForm({ user, onClose, canListRoles, identity, prefill = null }: { user: AdminUser | null; onClose: () => void; canListRoles: boolean; identity: IdentityProps; prefill?: InvitePrefill | null }) {
  const { t, locale } = useI18n();
  const departments = useDepartments();
  // P1 "approves for" (wave 1): only an approver who may manage users designates others
  const { can, perms } = usePermissions();
  const canDesignate = can("approvals.decide") && can("setup.users");
  const lookups = useScopeLookups(canDesignate);
  const [approves, setApproves] = useState<Scope[]>(() => (user?.approves_for ?? []).map((x) => ({ type: x.type, id: x.id ?? null, tag: x.tag ?? null })));
  const [approvesDirty, setApprovesDirty] = useState(false);
  const [f, setF] = useState({
    username: user?.username ?? "",
    email: user?.email ?? prefill?.email ?? "",
    firstname: user?.firstname ?? "",
    lastname: user?.lastname ?? "",
    displayname: user?.displayname ?? user?.full_name ?? prefill?.name ?? "",
    ext: user?.ext ?? "",
    role: user?.role_id ? `id:${user.role_id}` : "",
    department: user?.department_id ? String(user.department_id) : (prefill?.department ?? ""),
    is_active: user?.is_active ?? true,
    force_password_reset: user?.force_password_reset ?? false,
    password: "",
    // CRBS users_add "Password (confirm)" (UI gap audit #22)
    password2: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [roleError, setRoleError] = useState<string | null>(null);
  const [advOpen, setAdvOpen] = useState(false);
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((prev) => ({ ...prev, [k]: v }));
  // PER-F03: the "approves for" picker only for a role that holds approvals.decide (the backend refuses the rest);
  // otherwise one sentence with the next step. Unknown role list: the picker stays (the backend still checks)
  const designRoles = useRoles(canDesignate && canListRoles);
  const pickedRole = f.role.startsWith("id:") ? designRoles.data?.find((r) => `id:${r.id}` === f.role) : f.role.startsWith("code:") ? designRoles.data?.find((r) => r.code === f.role.slice(5)) : undefined;
  const targetMayApprove = !pickedRole || pickedRole.permissions.includes("approvals.decide");
  // the hand-over's role once the role list is known, only one this admin may grant (RoleSelect's rule)
  const prefillRoles = useRoles(canListRoles && !!prefill?.role);
  const [rolePrefilled, setRolePrefilled] = useState(!prefill?.role);
  if (!rolePrefilled && (!canListRoles || prefillRoles.data)) {
    setRolePrefilled(true);
    const v = roleValueFor(prefill?.role ?? "", prefillRoles.data);
    const r = v.startsWith("id:") ? prefillRoles.data?.find((x) => `id:${x.id}` === v) : v ? { code: v.slice(5) } : null;
    if (r && roleGrantCheck(perms, r).allowed) setF((prev) => ({ ...prev, role: v }));
  }
  const body = (): UserIn & { role?: string } => ({
    username: f.username.trim() || null,
    email: f.email.trim() || null,
    firstname: f.firstname.trim() || null,
    lastname: f.lastname.trim() || null,
    displayname: f.displayname.trim() || [f.firstname, f.lastname].filter(Boolean).join(" ").trim() || null,
    ext: f.ext.trim() || null,
    department_id: f.department ? Number(f.department) : null,
    is_active: f.is_active,
    force_password_reset: f.force_password_reset,
    ...(f.password ? { password: f.password } : {}),
    ...roleBody(f.role),
    ...(canDesignate && approvesDirty ? { approves_for: normaliseScopes(approves) } : {}),
  });
  const save = useCrbsMutation(() => (user ? crbs.users.update(user.id, body()) : crbs.users.create(body())), [["crbs", "users"]]);
  return (
    <>
      <DialogHeader>
        <DialogTitle>{user ? t("crbs.users.editTitle", { name: user.username ?? user.email ?? "" }) : t("crbs.users.new")}</DialogTitle>
        <DialogDescription>{t("crbs.users.formHint")}</DialogDescription>
      </DialogHeader>
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          if (!f.username.trim() && !f.email.trim()) return setError(t("crbs.users.needIdentity"));
          if (!f.role) {
            setRoleError(t("crbs.users.needRole"));
            document.getElementById("u-role")?.focus();
            return;
          }
          if (f.password !== f.password2) {
            setAdvOpen(true);
            return setError(t("admingaps.users.passwordMismatch"));
          }
          save.mutate(undefined, {
            onSuccess: (u) => {
              toast.success(user ? t("crbs.common.saved") : t("crbs.users.created", { name: u.username ?? u.email ?? "" }));
              onClose();
            },
            // PER-F03: the backend's Turkish sentence in Turkish (it was the English one)
            onError: (e) => setError(bookingErrorMessage(crbsError(e), t, { locale })),
          });
        }}
      >
        {/* mobile-b phase 2 (M-10): columns of at least 280 px; one column at 768, two in the wider desktop dialog */}
        <div className="grid gap-3 sm:grid-cols-[repeat(auto-fit,minmax(17.5rem,1fr))]">
          <Field label={t("crbs.users.email")} htmlFor="u-email">
            <Input id="u-email" type="email" autoComplete="off" value={f.email} onChange={(e) => set("email", e.target.value)} />
          </Field>
          <Field label={t("crbs.users.firstname")} htmlFor="u-first">
            <Input id="u-first" value={f.firstname} onChange={(e) => set("firstname", e.target.value)} />
          </Field>
          <Field label={t("crbs.users.lastname")} htmlFor="u-last">
            <Input id="u-last" value={f.lastname} onChange={(e) => set("lastname", e.target.value)} />
          </Field>
          <Field label={t("crbs.users.role")} htmlFor="u-role">
            <RoleSelect
              id="u-role"
              value={f.role}
              onChange={(v) => {
                set("role", v);
                if (v) setRoleError(null);
              }}
              canListRoles={canListRoles}
              error={roleError}
            />
          </Field>
          <Field label={t("crbs.users.department")} htmlFor="u-dept">
            <SelectField id="u-dept" value={f.department} onChange={(e) => set("department", e.target.value)}>
              <option value="">{t("crbs.book.departmentNone")}</option>
              {(departments.data ?? []).map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </SelectField>
          </Field>
        </div>
        {/* HX12B-F09: e-mail, name, role and department first; the rest of CRBS's form waits behind "Gelişmiş" */}
        <details className="group rounded-xl bg-fill-3 px-3 py-2" open={advOpen} onToggle={(e) => setAdvOpen(e.currentTarget.open)} data-testid="user-advanced">
          <summary className="cursor-pointer list-none type-callout font-medium text-label-1 outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus) pointer-coarse:flex pointer-coarse:min-h-11 pointer-coarse:flex-col pointer-coarse:justify-center">
            {t("crbs.users.advanced")}
            <span className="block type-footnote font-normal text-label-3">{t("crbs.users.advancedHint")}</span>
          </summary>
          <div className="flex flex-col gap-3 pt-3">
            <div className="grid gap-3 sm:grid-cols-[repeat(auto-fit,minmax(17.5rem,1fr))]">
              <Field label={t("crbs.users.username")} htmlFor="u-username" hint={t("crbs.users.usernameHint")}>
                <Input id="u-username" autoComplete="off" value={f.username} onChange={(e) => set("username", e.target.value)} />
              </Field>
              <Field label={t("crbs.users.displayname")} htmlFor="u-display">
                <Input id="u-display" value={f.displayname} onChange={(e) => set("displayname", e.target.value)} />
              </Field>
              <Field label={t("crbs.users.ext")} htmlFor="u-ext">
                <Input id="u-ext" value={f.ext} onChange={(e) => set("ext", e.target.value)} />
              </Field>
              <Field label={user ? t("crbs.users.newPassword") : t("crbs.users.password")} htmlFor="u-password" hint={t("crbs.users.passwordHint")}>
                <Input id="u-password" type="password" autoComplete="new-password" minLength={8} value={f.password} onChange={(e) => set("password", e.target.value)} />
              </Field>
              <Field label={t("admingaps.users.passwordConfirm")} htmlFor="u-password2" error={f.password2 && f.password !== f.password2 ? t("admingaps.users.passwordMismatch") : null}>
                <Input id="u-password2" type="password" autoComplete="new-password" value={f.password2} onChange={(e) => set("password2", e.target.value)} data-testid="user-password-confirm" />
              </Field>
            </div>
            <label className="flex items-center justify-between gap-3 type-callout text-label-1">
              {t("crbs.users.enabled")}
              <Switch checked={f.is_active} onCheckedChange={(v) => set("is_active", v)} aria-label={t("crbs.users.enabled")} />
            </label>
            <label className="flex items-center justify-between gap-3 type-callout text-label-1">
              <span>
                {t("crbs.users.forceReset")}
                <span className="block type-footnote text-label-3">{t("crbs.users.forceResetHint")}</span>
              </span>
              <Switch checked={f.force_password_reset} onCheckedChange={(v) => set("force_password_reset", v)} aria-label={t("crbs.users.forceReset")} />
            </label>
          </div>
        </details>
        {canDesignate ? (
          <details className="group rounded-xl bg-fill-3 px-3 py-2" open={approves.length > 0 || undefined} data-testid="user-approves-for">
            <summary className="cursor-pointer list-none type-callout font-medium text-label-1 outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus) pointer-coarse:flex pointer-coarse:min-h-11 pointer-coarse:flex-col pointer-coarse:justify-center">
              {t("wave1.scope.title")}
              <span className="block type-footnote font-normal text-label-3">{approves.length ? approves.map((x) => scopeLabel(x, lookups, t)).join(", ") : t("wave1.scope.hint")}</span>
            </summary>
            {!targetMayApprove && !approves.length ? (
              <p className="pt-3 type-callout text-label-2" data-testid="user-approves-needs-right">
                {t("wave1.scope.needsRight")}{" "}
                <Link href="/admin/roles" className="font-medium text-tint-text underline-offset-2 hover:underline">
                  {t("wave1.scope.needsRightLink")}
                </Link>
              </p>
            ) : (
            <div className="pt-3">
              <ScopePicker
                value={approves}
                onChange={(v) => {
                  setApproves(v);
                  setApprovesDirty(true);
                }}
                lookups={lookups}
                idPrefix="user"
              />
            </div>
            )}
          </details>
        ) : null}
        {user && identity ? <IdentitiesSection user={user} s={identity.s} invite={identity.invite} msEnabled={identity.msEnabled} onBind={identity.onBind} /> : null}
        {user && identity?.security ? <div className="hairline-t pt-4">{identity.security}</div> : null}
        {user ? <ConstraintsEditor userId={user.id} /> : null}
        {user ? (
          <Link href={`/admin/access?user=${user.id}`} className="inline-flex items-center gap-1.5 self-start type-callout text-tint-text outline-hidden hover:underline focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)" data-testid="user-form-check-access">
            <ShieldQuestion className="size-4" aria-hidden />
            {t("admingaps.access.checkUser")}
          </Link>
        ) : null}
        {error ? <Alert tone="error">{error}</Alert> : null}
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("crbs.common.cancel")}
          </Button>
          <Button type="submit" disabled={save.isPending} data-testid="user-save" aria-busy={save.isPending || undefined}>
            <BusyLabel busy={save.isPending} label={t(user ? "busy.saving" : "busy.creating")}>
            {user ? t("crbs.common.save") : t("crbs.common.create")}</BusyLabel>
          </Button>
        </DialogFooter>
      </form>
    </>
  );
}

const LIMIT_LABEL: Record<LimitKey, MessageKey> = {
  max_active_bookings: "crbs.limits.max_active_bookings",
  range_min: "crbs.limits.range_min",
  range_max: "crbs.limits.range_max",
  recur_max_instances: "crbs.limits.recur_max_instances",
};

/** CRBS `users_constraints`: per limit R (role value), U (this user's value) or X (unlimited). */
function ConstraintsEditor({ userId }: { userId: number }) {
  const { t } = useI18n();
  const q = useUserConstraints(userId);
  const [draft, setDraft] = useState<Constraints | null>(null);
  const value = draft ?? q.data ?? null;
  const toastError = useErrorToast();
  const save = useCrbsMutation((body: Constraints) => crbs.users.putConstraints(userId, body), [["crbs", "constraints", userId]]);
  if (!value) return q.isLoading ? <Loading /> : null;
  return (
    <fieldset className="flex flex-col gap-2 rounded-xl bg-fill-3 p-3 edge-hairline">
      <legend className="sr-only">{t("crbs.users.limits")}</legend>
      <p className="type-headline text-label-1">{t("crbs.users.limits")}</p>
      <p className="type-footnote text-label-3">{t("crbs.users.limitsHint")}</p>
      {LIMIT_KEYS.map((k) => {
        const c = value[k];
        return (
          <div key={k} className="flex flex-wrap items-center justify-between gap-2">
            <span className="type-callout text-label-1">{t(LIMIT_LABEL[k])}</span>
            <span className="flex items-center gap-2">
              <SelectField aria-label={t(LIMIT_LABEL[k])} className="w-40" value={c.type} onChange={(e) => setDraft({ ...value, [k]: { type: e.target.value as "R" | "U" | "X", value: e.target.value === "U" ? (c.value ?? 0) : null } })}>
                <option value="R">{t("crbs.users.useRole")}</option>
                <option value="U">{t("crbs.users.useOwn")}</option>
                <option value="X">{t("crbs.common.unlimited")}</option>
              </SelectField>
              {c.type === "U" ? (
                <Input type="number" min={0} className="w-20" aria-label={t("crbs.users.ownValue")} value={c.value ?? 0} onChange={(e) => setDraft({ ...value, [k]: { type: "U", value: Math.max(0, Number(e.target.value)) } })} />
              ) : null}
            </span>
          </div>
        );
      })}
      {draft ? (
        <div className="flex justify-end">
          <Button className="pointer-coarse:h-11"
            type="button"
            size="sm"
            variant="outline"
            disabled={save.isPending}
            onClick={() =>
              save.mutate(draft, {
                onSuccess: () => {
                  toast.success(t("crbs.common.saved"));
                  setDraft(null);
                },
                onError: toastError,
              })
            }
          >
            {t("crbs.users.saveLimits")}
          </Button>
        </div>
      ) : null}
    </fieldset>
  );
}

function TokenDialog({ value, onClose }: { value: { user: AdminUser; token: ResetToken } | null; onClose: () => void }) {
  const { t } = useI18n();
  const fmt = useBookingFormat();
  const tok = value?.token;
  const expires = fmt.dateTime(tok?.expires_at);
  return (
    <Dialog open={!!value} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md" data-testid="token-dialog">
        <DialogHeader>
          <DialogTitle>{t("crbs.users.resetCodeTitle", { name: value?.user.username ?? value?.user.email ?? "" })}</DialogTitle>
          <DialogDescription>{tok?.emailed ? t("crbs.users.resetEmailed") : t("crbs.users.resetShowOnce")}</DialogDescription>
        </DialogHeader>
        {tok?.token ? (
          <div className="flex gap-2">
            <Input readOnly value={tok.token} className="font-mono" aria-label={t("crbs.users.resetCode")} onFocus={(e) => e.currentTarget.select()} data-testid="reset-token" />
            <Button variant="outline" size="icon" aria-label={t("crbs.feed.copy")} onClick={() => void navigator.clipboard?.writeText(tok.token ?? "").then(() => toast.success(t("crbs.feed.copied")))}>
              <Copy />
            </Button>
          </div>
        ) : null}
        {expires ? <p className="type-footnote text-label-3">{t("crbs.users.resetExpires", { when: expires })}</p> : null}
        <p className="type-footnote text-label-3">{t("crbs.users.resetWhere")}</p>
        <DialogFooter>
          <Button onClick={onClose}>{t("crbs.common.close")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const STATUS_KEYS: Record<string, MessageKey> = {
  success: "crbs.import.status.success",
  username_exists: "crbs.import.status.username_exists",
  username_empty: "crbs.import.status.username_empty",
  password_empty: "crbs.import.status.password_empty",
  invalid: "crbs.import.status.invalid",
  forbidden: "crbs.import.status.forbidden",
  email_exists: "crbs.import.status.email_exists",
};
const STATUS_WORDS: Record<string, MessageKey> = {
  success: "crbs.import.word.success",
  username_exists: "crbs.import.word.username_exists",
  username_empty: "crbs.import.word.username_empty",
  password_empty: "crbs.import.word.password_empty",
  email_exists: "crbs.import.word.email_exists",
  invalid: "crbs.import.word.invalid",
  forbidden: "crbs.import.word.forbidden",
};

/** "3 satır: 1 oluşturuldu, 1 parola yok, 1 e-posta var" (T-R1-33): one line of counts per status, in the UI language. */
export function importSummaryLine(result: Pick<ImportResult, "results">, t: (key: MessageKey, vars?: Record<string, string | number>) => string): string {
  const counts = new Map<string, number>();
  for (const r of result.results) counts.set(r.status, (counts.get(r.status) ?? 0) + 1);
  const parts = Object.keys(STATUS_WORDS)
    .filter((k) => counts.get(k))
    .map((k) => `${counts.get(k)} ${t(STATUS_WORDS[k]!)}`);
  for (const [k, n] of counts) if (!STATUS_WORDS[k]) parts.push(`${n} ${k}`);
  return t("crbs.import.summaryLine", { total: result.results.length, parts: parts.join(", ") });
}

function ImportDialog({ open, onOpenChange, canListRoles }: { open: boolean; onOpenChange: (o: boolean) => void; canListRoles: boolean }) {
  const { t } = useI18n();
  const departments = useDepartments();
  const [file, setFile] = useState<File | null>(null);
  // HB-23c: the CSV the helper handed over (a staged token) replaces the file field until ✕
  const handed = useHelperFileHandoff("admin.users");
  const handedRaw = handed.expired ? null : (handed.handoff?.items[0] ?? null);
  // HELPER_FILE_STAGE=off: the browser's File itself (no token); gone after a reload
  const handedBytes = handedRaw && !handedRaw.token ? handedFile(handedRaw) : null;
  const handedItem = handedRaw && (handedRaw.token || handedBytes) ? handedRaw : null;
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("");
  const [dept, setDept] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [force, setForce] = useState(true);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const m = useCrbsMutation(
    () => crbs.users.import(handedItem?.token ? null : (handedBytes ?? file), { password: password || undefined, role_id: role.startsWith("id:") ? Number(role.slice(3)) : null, department_id: dept ? Number(dept) : null, enabled, force_password_reset: force, upload_token: handedItem?.token ?? undefined }),
    [["crbs", "users"]],
  );
  const close = (o: boolean) => {
    onOpenChange(o);
    if (!o) {
      setResult(null);
      setFile(null);
      setError(null);
    }
  };
  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-2xl" data-testid="import-dialog">
        <DialogHeader>
          <DialogTitle>{t("crbs.import.title")}</DialogTitle>
          <DialogDescription>{t("crbs.import.lead")}</DialogDescription>
        </DialogHeader>
        {!result ? (
          <div className="flex flex-col gap-3">
            <Field label={t("crbs.import.file")} htmlFor="imp-file" hint={`${t("crbs.import.columns")} ${t("crbs.import.headerHint")}`}>
              {handedItem ? (
                <HandedFileRow item={handedItem} onRemove={handed.remove} testId="users-handed-file" />
              ) : (
                <Input id="imp-file" type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              )}
            </Field>
            <p className="type-headline text-label-1">{t("crbs.import.defaults")}</p>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label={t("crbs.users.password")} htmlFor="imp-pw" hint={t("crbs.import.passwordHint")}>
                <Input id="imp-pw" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
              </Field>
              <Field label={t("crbs.users.role")} htmlFor="imp-role">
                <RoleSelect id="imp-role" value={role} onChange={setRole} canListRoles={canListRoles} />
              </Field>
              <Field label={t("crbs.users.department")} htmlFor="imp-dept">
                <SelectField id="imp-dept" value={dept} onChange={(e) => setDept(e.target.value)}>
                  <option value="">{t("crbs.book.departmentNone")}</option>
                  {(departments.data ?? []).map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </SelectField>
              </Field>
            </div>
            <label className="flex items-center gap-2 type-callout text-label-1">
              <Checkbox checked={enabled} onCheckedChange={(v) => setEnabled(v === true)} />
              {t("crbs.import.enabled")}
            </label>
            <label className="flex items-center gap-2 type-callout text-label-1">
              <Checkbox checked={force} onCheckedChange={(v) => setForce(v === true)} />
              {t("crbs.users.forceReset")}
            </label>
            {error ? <Alert tone="error">{error}</Alert> : null}
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <Alert tone={result.created ? "success" : "warning"} testId="import-summary">
              {t("crbs.import.summary", { created: result.created, total: result.results.length })}
              <span className="mt-1 block type-footnote" data-testid="import-summary-line">
                {result.summary_text ?? importSummaryLine(result, t)}
              </span>
            </Alert>
            {result.results.some((r) => r.status === "forbidden") ? (
              <Alert tone="warning" testId="import-forbidden">
                {t("crbs.import.forbiddenHint", { n: result.results.filter((r) => r.status === "forbidden").length })}
              </Alert>
            ) : null}
            <div className="max-h-[50vh] overflow-auto rounded-xl bg-(--mat-thick-solid) edge-hairline">
              <Table data-testid="import-results">
                <TableHeader>
                  <TableRow>
                    <TableHead className="pl-3">{t("crbs.import.line")}</TableHead>
                    <TableHead>{t("crbs.users.username")}</TableHead>
                    <TableHead className="pr-3">{t("crbs.import.result")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {result.results.map((r) => (
                    <TableRow key={r.line}>
                      <TableCell className="pl-3 tabular-nums text-label-2">{r.line}</TableCell>
                      <TableCell className="text-label-1">{r.username || "—"}</TableCell>
                      <TableCell className="pr-3">
                        <Badge variant="secondary" tone={r.status === "success" ? "feasible" : r.status === "invalid" || r.status === "forbidden" ? "infeasible" : "warning"}>
                          {STATUS_KEYS[r.status] ? t(STATUS_KEYS[r.status]!) : r.status}
                        </Badge>
                        {r.error ? (
                          <span className="ml-2 type-footnote text-label-2">{r.error}</span>
                        ) : null}
                        {r.warning ? (
                          <span className="ml-2 type-footnote text-label-2" data-testid="import-row-warning">{r.warning}</span>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        )}
        <DialogFooter>
          <Button variant="ghost" onClick={() => close(false)}>
            {result ? t("crbs.common.close") : t("crbs.common.cancel")}
          </Button>
          {!result ? (
            <Button
              disabled={(!file && !handedItem) || m.isPending}
              onClick={() =>
                m.mutate(undefined, {
                  onSuccess: (r) => {
                    if (handedItem) handed.consumed();
                    setResult(r);
                  },
                  onError: (e) => setError(bookingErrorMessage(crbsError(e), t)),
                })
              }
              data-testid="import-run"
             aria-busy={m.isPending || undefined}>
              <BusyLabel busy={m.isPending} label={t("busy.working")}>
              {t("crbs.import.run")}</BusyLabel>
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
