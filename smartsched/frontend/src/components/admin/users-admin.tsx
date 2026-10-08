"use client";
/**
 * /admin/users (CRBS `Users`): search and filters, add/edit with role, department, names and the
 * force-password-change flag, per-user booking limits (R = role value, U = own value, X = unlimited),
 * one-time reset codes (shown once), delete, and the CSV import with a per-row result table.
 */
import { Copy, KeyRound, Loader2, MoreHorizontal, Pencil, Trash2, Upload, UserPlus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
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
import { usePermissions } from "@/lib/permissions";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import { Alert, ConfirmDialog, Field, Loading, PageTitle, SelectField } from "./kit";
import { useErrorToast } from "./admin-gate";

const PAGE = 25;
const SEEDED = [
  { code: "ADMIN", key: "crbs.users.roleAdmin" },
  { code: "PLANNER", key: "crbs.users.rolePlanner" },
  { code: "VIEWER", key: "crbs.users.roleViewer" },
  { code: "TEACHER", key: "crbs.users.roleTeacher" },
] as const;

export function UsersAdmin() {
  const { t, locale } = useI18n();
  const { can } = usePermissions();
  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [dept, setDept] = useState("");
  const [enabled, setEnabled] = useState("");
  const [sort, setSort] = useState("username");
  const [page, setPage] = useState(0);
  const query = { q: q || undefined, role_id: role ? Number(role) : undefined, department_id: dept ? Number(dept) : undefined, enabled: enabled === "" ? undefined : enabled === "1", sort, limit: PAGE, offset: page * PAGE };
  const users = useUserSearch(query);
  const roles = useRoles(can("setup.roles"));
  const departments = useDepartments();
  const [editing, setEditing] = useState<AdminUser | "new" | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [token, setToken] = useState<{ user: AdminUser; token: ResetToken } | null>(null);
  const [deleting, setDeleting] = useState<AdminUser | null>(null);
  const toastError = useErrorToast();
  const reset = useCrbsMutation((u: AdminUser) => crbs.users.resetToken(u.id));
  const del = useCrbsMutation((u: AdminUser) => crbs.users.remove(u.id), [["crbs", "users"]]);
  const total = users.data?.total ?? 0;
  const dt = (iso: string | null | undefined) => (iso ? new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`).toLocaleString(locale === "tr" ? "tr-TR" : "en-GB", { dateStyle: "medium", timeStyle: "short" }) : "—");

  return (
    <div className="flex flex-col gap-5">
      <PageTitle
        title={t("crbs.admin.users.title")}
        subtitle={users.data ? t("crbs.users.count", { n: total }) : t("crbs.admin.users.lead")}
        actions={
          <>
            <Button variant="outline" onClick={() => setImportOpen(true)} data-testid="users-import">
              <Upload aria-hidden />
              {t("crbs.users.import")}
            </Button>
            <Button onClick={() => setEditing("new")} data-testid="users-new">
              <UserPlus aria-hidden />
              {t("crbs.users.new")}
            </Button>
          </>
        }
      />
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
        <SelectField aria-label={t("crbs.users.role")} value={role} onChange={(e) => (setRole(e.target.value), setPage(0))}>
          <option value="">{t("crbs.users.allRoles")}</option>
          {(roles.data ?? []).map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
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
        <SelectField aria-label={t("crbs.users.sort")} value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="username">{t("crbs.users.sortUsername")}</option>
          <option value="displayname">{t("crbs.users.sortName")}</option>
          <option value="-lastlogin">{t("crbs.users.sortLogin")}</option>
          <option value="role">{t("crbs.users.sortRole")}</option>
        </SelectField>
      </div>
      <Card variant="glass" className="py-0">
        {users.isLoading ? (
          <Loading className="px-4" />
        ) : (
          <Table data-testid="users-table">
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">{t("crbs.users.name")}</TableHead>
                <TableHead className="hidden md:table-cell">{t("crbs.users.email")}</TableHead>
                <TableHead>{t("crbs.users.role")}</TableHead>
                <TableHead className="hidden lg:table-cell">{t("crbs.users.department")}</TableHead>
                <TableHead className="hidden lg:table-cell">{t("crbs.users.lastLogin")}</TableHead>
                <TableHead className="w-10 pr-4">
                  <span className="sr-only">{t("crbs.common.actions")}</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(users.data?.items ?? []).map((u) => (
                <TableRow key={u.id} data-username={u.username ?? u.email ?? ""}>
                  <TableCell className="pl-4">
                    <span className="block font-medium text-label-1">{u.displayname || u.full_name || u.username || u.email}</span>
                    <span className="block type-footnote text-label-3">
                      {u.username ?? u.email}
                      {u.auth_source === "ldap" ? " · LDAP" : ""}
                    </span>
                  </TableCell>
                  <TableCell className="hidden text-label-2 md:table-cell">{u.email ?? "—"}</TableCell>
                  <TableCell>
                    <span className="text-label-1">{u.role_name ?? t("crbs.users.noRole")}</span>
                    {!u.is_active ? (
                      <Badge tone="preoccupied" variant="secondary" className="ml-2">
                        {t("crbs.users.disabled")}
                      </Badge>
                    ) : u.force_password_reset ? (
                      <Badge tone="warning" variant="secondary" className="ml-2">
                        {t("crbs.users.mustChange")}
                      </Badge>
                    ) : null}
                  </TableCell>
                  <TableCell className="hidden text-label-2 lg:table-cell">{u.department_name ?? "—"}</TableCell>
                  <TableCell className="hidden text-label-2 tabular-nums lg:table-cell">{dt(u.last_login_at)}</TableCell>
                  <TableCell className="pr-4 text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={t("crbs.users.actionsFor", { name: u.username ?? u.email ?? "" })} />}>
                        <MoreHorizontal />
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => setEditing(u)}>
                          <Pencil aria-hidden />
                          {t("crbs.common.edit")}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={() =>
                            reset.mutate(u, {
                              onSuccess: (tok) => setToken({ user: u, token: tok }),
                              onError: toastError,
                            })
                          }
                        >
                          <KeyRound aria-hidden />
                          {t("crbs.users.resetCode")}
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem variant="destructive" onClick={() => setDeleting(u)}>
                          <Trash2 aria-hidden />
                          {t("crbs.common.delete")}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
              {users.data && users.data.items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="px-4 py-6 text-label-2">
                    {t("crbs.users.none")}
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        )}
      </Card>
      {total > PAGE ? (
        <div className="flex items-center justify-between type-callout text-label-2">
          <span>{t("crbs.users.page", { from: page * PAGE + 1, to: Math.min(total, (page + 1) * PAGE), total })}</span>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
              {t("crbs.users.prev")}
            </Button>
            <Button variant="ghost" size="sm" disabled={(page + 1) * PAGE >= total} onClick={() => setPage((p) => p + 1)}>
              {t("crbs.users.next")}
            </Button>
          </div>
        </div>
      ) : null}

      <UserDialog user={editing} onClose={() => setEditing(null)} canListRoles={can("setup.roles")} />
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

function RoleSelect({ value, onChange, canListRoles, id }: { value: string; onChange: (v: string) => void; canListRoles: boolean; id?: string }) {
  const { t } = useI18n();
  const roles = useRoles(canListRoles);
  return (
    <SelectField id={id} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{t("crbs.users.pickRole")}</option>
      {roles.data
        ? roles.data.map((r) => (
            <option key={r.id} value={`id:${r.id}`}>
              {r.name}
            </option>
          ))
        : SEEDED.map((r) => (
            <option key={r.code} value={`code:${r.code}`}>
              {t(r.key as MessageKey)}
            </option>
          ))}
    </SelectField>
  );
}

function roleBody(v: string): Pick<UserIn, "role_id"> & { role?: string } {
  if (v.startsWith("id:")) return { role_id: Number(v.slice(3)) };
  if (v.startsWith("code:")) return { role: v.slice(5) };
  return {};
}

function UserDialog({ user, onClose, canListRoles }: { user: AdminUser | "new" | null; onClose: () => void; canListRoles: boolean }) {
  return (
    <Dialog open={user !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-xl" data-testid="user-dialog">
        {user !== null ? <UserForm key={user === "new" ? "new" : user.id} user={user === "new" ? null : user} onClose={onClose} canListRoles={canListRoles} /> : null}
      </DialogContent>
    </Dialog>
  );
}

function UserForm({ user, onClose, canListRoles }: { user: AdminUser | null; onClose: () => void; canListRoles: boolean }) {
  const { t } = useI18n();
  const departments = useDepartments();
  const [f, setF] = useState({
    username: user?.username ?? "",
    email: user?.email ?? "",
    firstname: user?.firstname ?? "",
    lastname: user?.lastname ?? "",
    displayname: user?.displayname ?? user?.full_name ?? "",
    ext: user?.ext ?? "",
    role: user?.role_id ? `id:${user.role_id}` : "",
    department: user?.department_id ? String(user.department_id) : "",
    is_active: user?.is_active ?? true,
    force_password_reset: user?.force_password_reset ?? false,
    password: "",
  });
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((prev) => ({ ...prev, [k]: v }));
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
          if (!f.role) return setError(t("crbs.users.needRole"));
          save.mutate(undefined, {
            onSuccess: (u) => {
              toast.success(user ? t("crbs.common.saved") : t("crbs.users.created", { name: u.username ?? u.email ?? "" }));
              onClose();
            },
            onError: (e) => setError(bookingErrorMessage(crbsError(e), t)),
          });
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("crbs.users.username")} htmlFor="u-username" hint={t("crbs.users.usernameHint")}>
            <Input id="u-username" autoComplete="off" value={f.username} onChange={(e) => set("username", e.target.value)} />
          </Field>
          <Field label={t("crbs.users.email")} htmlFor="u-email">
            <Input id="u-email" type="email" autoComplete="off" value={f.email} onChange={(e) => set("email", e.target.value)} />
          </Field>
          <Field label={t("crbs.users.firstname")} htmlFor="u-first">
            <Input id="u-first" value={f.firstname} onChange={(e) => set("firstname", e.target.value)} />
          </Field>
          <Field label={t("crbs.users.lastname")} htmlFor="u-last">
            <Input id="u-last" value={f.lastname} onChange={(e) => set("lastname", e.target.value)} />
          </Field>
          <Field label={t("crbs.users.displayname")} htmlFor="u-display">
            <Input id="u-display" value={f.displayname} onChange={(e) => set("displayname", e.target.value)} />
          </Field>
          <Field label={t("crbs.users.ext")} htmlFor="u-ext">
            <Input id="u-ext" value={f.ext} onChange={(e) => set("ext", e.target.value)} />
          </Field>
          <Field label={t("crbs.users.role")} htmlFor="u-role">
            <RoleSelect id="u-role" value={f.role} onChange={(v) => set("role", v)} canListRoles={canListRoles} />
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
          <Field label={user ? t("crbs.users.newPassword") : t("crbs.users.password")} htmlFor="u-password" hint={t("crbs.users.passwordHint")}>
            <Input id="u-password" type="password" autoComplete="new-password" minLength={8} value={f.password} onChange={(e) => set("password", e.target.value)} />
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
        {user ? <ConstraintsEditor userId={user.id} /> : null}
        {error ? <Alert tone="error">{error}</Alert> : null}
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("crbs.common.cancel")}
          </Button>
          <Button type="submit" disabled={save.isPending} data-testid="user-save">
            {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {user ? t("crbs.common.save") : t("crbs.common.create")}
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
    <fieldset className="flex flex-col gap-2 rounded-xl bg-fill-3 p-3 shadow-[inset_0_0_0_1px_var(--hairline)]">
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
          <Button
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
  const { t, locale } = useI18n();
  const tok = value?.token;
  const expires = tok?.expires_at ? new Date(tok.expires_at.endsWith("Z") ? tok.expires_at : `${tok.expires_at}Z`).toLocaleString(locale === "tr" ? "tr-TR" : "en-GB", { dateStyle: "medium", timeStyle: "short" }) : "";
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
};

function ImportDialog({ open, onOpenChange, canListRoles }: { open: boolean; onOpenChange: (o: boolean) => void; canListRoles: boolean }) {
  const { t } = useI18n();
  const departments = useDepartments();
  const [file, setFile] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("");
  const [dept, setDept] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [force, setForce] = useState(true);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const m = useCrbsMutation(
    () => crbs.users.import(file as File, { password: password || undefined, role_id: role.startsWith("id:") ? Number(role.slice(3)) : null, department_id: dept ? Number(dept) : null, enabled, force_password_reset: force }),
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
            <Field label={t("crbs.import.file")} htmlFor="imp-file" hint={t("crbs.import.columns")}>
              <Input id="imp-file" type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
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
            <Alert tone={result.created ? "success" : "warning"}>{t("crbs.import.summary", { created: result.created, total: result.results.length })}</Alert>
            <div className="max-h-[50vh] overflow-auto rounded-xl bg-(--mat-thick-solid) shadow-[0_0_0_1px_var(--hairline)]">
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
                        <Badge variant="secondary" tone={r.status === "success" ? "feasible" : r.status === "invalid" ? "infeasible" : "warning"}>
                          {STATUS_KEYS[r.status] ? t(STATUS_KEYS[r.status]!) : r.status}
                        </Badge>
                        {r.error ? <span className="ml-2 type-footnote text-label-2">{r.error}</span> : null}
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
              disabled={!file || m.isPending}
              onClick={() =>
                m.mutate(undefined, {
                  onSuccess: setResult,
                  onError: (e) => setError(bookingErrorMessage(crbsError(e), t)),
                })
              }
              data-testid="import-run"
            >
              {m.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              {t("crbs.import.run")}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
