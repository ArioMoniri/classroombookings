"use client";
/**
 * /admin/roles (CRBS `Roles`): the role list with member counts, and an editor with the four booking
 * limits and the permission matrix grouped like CRBS (`Permissions_model::get_scoped`): system and setup
 * permissions as lists, booking permissions as a table with single and recurring side by side.
 * Phones (< 640 px; dense grids on phones 2026-10-16): one role at a time (a role picker instead of the list) and
 * the booking permissions as two groups (single / recurring, the CRBS groups) of 44 px labelled checkbox rows
 * instead of the 3-column table (MOBILE.md M-02).
 */
import { ChevronRight, Plus, ShieldCheck, Trash2 } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { BusyLabel } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { crbs, crbsError, usePermissionCatalogue, useCrbsMutation, useRoles, useUserSearch, type PermissionCatalogue, type Role, type RoleIn } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { permissionLabel, permissionList, roleDescription, roleLabel } from "@/lib/i18n/roles";
import { cn } from "@/lib/utils";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import { roleEditCheck, usePermissions } from "@/lib/permissions";
import { Alert, ConfirmDialog, Field, LimitInput, Loading, PageTitle } from "./kit";
import { useErrorToast } from "./admin-gate";
import { BareButton } from "@/components/shell/bare-button";
import { NativeSelect } from "@/components/ui/native-select";
import { useIsPhone } from "@/components/bookings/use-is-phone";

const GROUP_KEYS: Record<string, MessageKey> = {
  system: "crbs.perm.group.system",
  setup: "crbs.perm.group.setup",
  planning: "crbs.perm.group.planning",
  room: "crbs.perm.group.room",
  book_single: "crbs.perm.group.book_single",
  book_recur: "crbs.perm.group.book_recur",
  // wave 1 groups (admin persona M-36: shown as raw "rooms", "audit", "approvals")
  rooms: "crbs.perm.group.rooms",
  audit: "crbs.perm.group.audit",
  approvals: "crbs.perm.group.approvals",
  // approval-first bookings (bookings.skip_approval)
  bookings: "approvals.perm.group_bookings",
};
const BOOK_ACTIONS = ["create", "edit_other_booking", "cancel_other_booking", "set_user", "set_department", "view_other_notes", "view_other_users"] as const;

/** Translated label for a permission name; falls back to the backend description (lib/i18n/roles). */
export const permLabel = permissionLabel;

export function RolesAdmin() {
  const { t } = useI18n();
  const roles = useRoles();
  const [selectedId, setSelectedId] = useState<number | "new" | null>(null);
  const current = selectedId === "new" ? null : (roles.data?.find((r) => r.id === selectedId) ?? roles.data?.[0] ?? null);
  const editing = selectedId === "new" ? "new" : current;
  const phone = useIsPhone();
  return (
    <div className="flex flex-col gap-5">
      <PageTitle
        title={t("crbs.admin.roles.title")}
        subtitle={t("crbs.roles.lead")}
        actions={
          <Button onClick={() => setSelectedId("new")} data-testid="roles-new">
            <Plus aria-hidden />
            {t("crbs.roles.new")}
          </Button>
        }
      />
      {roles.isLoading ? (
        <Loading />
      ) : (
        <div className="grid gap-5 lg:grid-cols-[260px_1fr]">
          {phone ? (
            <NativeSelect
              aria-label={t("crbs.admin.roles.title")}
              data-testid="roles-picker"
              value={editing === "new" ? "new" : editing ? String(editing.id) : ""}
              onChange={(e) => setSelectedId(e.target.value === "new" ? "new" : Number(e.target.value))}
            >
              {editing === "new" ? <option value="new">{t("crbs.roles.new")}</option> : null}
              {(roles.data ?? []).map((r) => (
                <option key={r.id} value={r.id}>
                  {`${roleLabel(t, r)} · ${t("crbs.roles.summary", { users: r.user_count, perms: r.permissions.length })}`}
                </option>
              ))}
            </NativeSelect>
          ) : (
          <nav aria-label={t("crbs.admin.roles.title")}>
            <Card className="py-1">
              <ul>
                {(roles.data ?? []).map((r) => {
                  const active = editing !== "new" && editing?.id === r.id;
                  return (
                    <li key={r.id}>
                      <BareButton
                        aria-current={active ? "true" : undefined}
                        onClick={() => setSelectedId(r.id)}
                        className={cn("flex w-full items-center justify-between gap-2 px-4 py-2 text-left focus-visible:-outline-offset-2", active ? "bg-tint-soft" : "hover:bg-fill-3")}
                      >
                        <span className="min-w-0">
                          <span className="block truncate type-headline text-label-1">{roleLabel(t, r)}</span>
                          <span className="block type-footnote text-label-3">{t("crbs.roles.summary", { users: r.user_count, perms: r.permissions.length })}</span>
                        </span>
                        {r.code === "ADMIN" ? <ShieldCheck className="size-4 shrink-0 text-label-2" aria-label={t("crbs.roles.locked")} /> : null}
                      </BareButton>
                    </li>
                  );
                })}
              </ul>
            </Card>
          </nav>
          )}
          {editing ? <RoleEditor key={editing === "new" ? "new" : editing.id} role={editing === "new" ? null : editing} onSaved={(r) => setSelectedId(r.id)} onDeleted={() => setSelectedId(null)} /> : null}
        </div>
      )}
    </div>
  );
}

function RoleEditor({ role, onSaved, onDeleted }: { role: Role | null; onSaved: (r: Role) => void; onDeleted: () => void }) {
  const { t } = useI18n();
  const catalogue = usePermissionCatalogue();
  const { perms: mine } = usePermissions();
  const held = useMemo(() => new Set(mine ?? []), [mine]);
  const locked = role?.code === "ADMIN";
  // no escalation (backend rule): a role with permissions the editor does not hold is read-only, not deletable
  const editCheck = roleEditCheck(mine, role);
  const readOnly = locked || !editCheck.allowed;
  // a built-in role still named as shipped ("Teacher") is edited under its display name ("Öğretim elemanı"); the
  // stored name is sent back unless the administrator renames it
  const shownName = role ? roleLabel(t, role) : "";
  const shownDescription = role ? roleDescription(t, role) : "";
  const [name, setName] = useState(shownName);
  const [description, setDescription] = useState(shownDescription);
  const [limits, setLimits] = useState({
    max_active_bookings: role?.max_active_bookings ?? null,
    range_min: role?.range_min ?? null,
    range_max: role?.range_max ?? null,
    recur_max_instances: role?.recur_max_instances ?? null,
  });
  const [perms, setPerms] = useState<Set<string>>(new Set(role?.permissions ?? ["room.view", "book_single.create"]));
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const toastError = useErrorToast();
  const body = (): RoleIn => ({
    name: role && name.trim() === shownName ? role.name : name.trim(),
    description: role && description.trim() === shownDescription ? role.description : description.trim() || null,
    ...limits,
    permissions: [...perms].sort(),
  });
  const save = useCrbsMutation(() => (role ? crbs.roles.update(role.id, body()) : crbs.roles.create(body())), [["crbs", "roles"]]);
  const del = useCrbsMutation(() => crbs.roles.remove(role?.id ?? 0), [["crbs", "roles"]]);
  const toggle = (p: string, on: boolean) =>
    setPerms((prev) => {
      const next = new Set(prev);
      if (on) next.add(p);
      else next.delete(p);
      return next;
    });

  return (
    <Card className="gap-5 px-5" data-testid="role-editor" data-readonly={readOnly ? "true" : undefined}>
      {!locked && !editCheck.allowed ? (
        <Alert tone="warning" testId="role-readonly">
          {t("crbs.roles.readOnly", { list: permissionList(t, editCheck.missing, 6) })}
        </Alert>
      ) : null}
      <fieldset disabled={readOnly && !locked ? true : undefined} className="contents">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("crbs.common.name")} htmlFor="role-name">
          <Input id="role-name" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label={t("crbs.common.description")} htmlFor="role-desc">
          <Input id="role-desc" value={description} maxLength={255} onChange={(e) => setDescription(e.target.value)} />
        </Field>
      </div>
      {role ? <RoleUsers role={role} /> : null}
      <section aria-labelledby="role-limits">
        <h3 id="role-limits" className="type-headline text-label-1">
          {t("crbs.users.limits")}
        </h3>
        <p className="mb-2 type-footnote text-label-3">{t("crbs.roles.limitsHint")}</p>
        <div className="grid gap-2 sm:grid-cols-2">
          {(["max_active_bookings", "range_min", "range_max", "recur_max_instances"] as const).map((k) => (
            <label key={k} className="flex items-center justify-between gap-3 rounded-lg bg-fill-3 px-3 py-2 type-callout text-label-1">
              {t(`crbs.limits.${k}` as MessageKey)}
              <LimitInput label={t(`crbs.limits.${k}` as MessageKey)} placeholder={t("crbs.common.unlimited")} value={limits[k]} onChange={(v) => setLimits((l) => ({ ...l, [k]: v }))} />
            </label>
          ))}
        </div>
      </section>
      {locked ? <Alert tone="info">{t("crbs.roles.adminLocked")}</Alert> : null}
      {catalogue.data ? <PermissionMatrix catalogue={catalogue.data} value={perms} onToggle={toggle} disabled={readOnly} held={held} /> : <Loading />}
      </fieldset>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <div className="flex flex-wrap justify-between gap-2">
        {role && !readOnly ? (
          <Button variant="ghost" className="text-status-infeasible-fg" onClick={() => setConfirmDelete(true)}>
            <Trash2 aria-hidden />
            {t("crbs.roles.delete")}
          </Button>
        ) : (
          <span />
        )}
        <Button
          disabled={save.isPending || !name.trim() || (readOnly && !locked)}
          data-testid="role-save"
          onClick={() => {
            setError(null);
            save.mutate(undefined, {
              onSuccess: (r) => {
                toast.success(t("crbs.common.saved"));
                onSaved(r);
              },
              onError: (e) => setError(bookingErrorMessage(crbsError(e), t)),
            });
          }}
         aria-busy={save.isPending || undefined}>
          <BusyLabel busy={save.isPending} label={t("busy.saving")}>
          {role ? t("crbs.common.save") : t("crbs.roles.create")}</BusyLabel>
        </Button>
      </div>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={t("crbs.roles.deleteTitle", { name: role ? roleLabel(t, role) : "" })}
        description={t("crbs.roles.deleteBody", { n: role?.user_count ?? 0 })}
        confirmLabel={t("crbs.common.delete")}
        destructive
        busy={del.isPending}
        onConfirm={() =>
          del.mutate(undefined, {
            onSuccess: () => {
              setConfirmDelete(false);
              onDeleted();
            },
            onError: toastError,
          })
        }
      />
    </Card>
  );
}

const ROLE_USERS_SHOWN = 24;

/** CRBS `V/roles/user_list.php`: who holds the role (UI gap audit #16). Needs setup.users to read people. */
function RoleUsers({ role }: { role: Role }) {
  const { t } = useI18n();
  const { can } = usePermissions();
  const allowed = can("setup.users");
  const users = useUserSearch({ role_id: role.id, limit: ROLE_USERS_SHOWN, sort: "displayname" }, allowed && role.user_count > 0);
  const total = users.data?.total ?? role.user_count;
  return (
    <section aria-labelledby="role-users" data-testid="role-users">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 id="role-users" className="type-headline text-label-1">
          {t("admingaps.roles.users", { n: total })}
        </h3>
        {allowed && total > 0 ? (
          <Link href={`/admin/users?role=${role.id}`} className="inline-flex min-h-11 items-center gap-1 type-callout text-tint-text outline-hidden hover:underline pointer-fine:min-h-0 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)" data-testid="role-users-all">
            {t("admingaps.roles.openInUsers")}
            <ChevronRight className="size-4" aria-hidden />
          </Link>
        ) : null}
      </div>
      {role.user_count === 0 ? (
        <p className="type-callout text-label-2">{t("admingaps.roles.noUsers")}</p>
      ) : !allowed ? (
        <p className="type-callout text-label-2">{t("admingaps.roles.usersNeedPermission")}</p>
      ) : users.isLoading ? (
        <Loading />
      ) : (
        <ul className="flex flex-wrap gap-1.5">
          {(users.data?.items ?? []).map((u) => (
            <li key={u.id} className="rounded-full bg-fill-2 px-2.5 py-1 type-footnote text-label-1" title={u.email ?? u.username ?? undefined}>
              {u.displayname || u.full_name || u.username || u.email}
              {!u.is_active ? <span className="ml-1 text-label-3">· {t("crbs.users.disabled")}</span> : null}
            </li>
          ))}
          {total > ROLE_USERS_SHOWN ? <li className="px-1 py-1 type-footnote text-label-3">{t("admingaps.roles.more", { n: total - ROLE_USERS_SHOWN })}</li> : null}
        </ul>
      )}
    </section>
  );
}

/** T-R1-33 (R1-M-21, F-11 S04): the reason a permission cannot be granted, as text under its label, not only in a tooltip (M-11). */
function DisabledHint({ why }: { why: string | undefined }) {
  const { t } = useI18n();
  if (!why) return null;
  return (
    <span className="block type-caption text-label-3" data-testid="role-disabled-hint">
      {t("crbs.roles.notHeldHint")}
    </span>
  );
}

export function PermissionMatrix({
  catalogue,
  value,
  onToggle,
  disabled,
  only,
  held,
}: {
  catalogue: PermissionCatalogue;
  value: ReadonlySet<string>;
  onToggle: (p: string, on: boolean) => void;
  disabled?: boolean;
  only?: "bookings";
  /** the editor's own permissions: anything else is disabled (no escalation); omitted = no such limit */
  held?: ReadonlySet<string>;
}) {
  const { t } = useI18n();
  const phone = useIsPhone();
  const off = (name: string) => !!disabled || (!!held && !held.has(name));
  const why = (name: string) => (!disabled && held && !held.has(name) ? t("crbs.roles.notHeld") : undefined);
  const book = catalogue.bookings;
  return (
    <div className="flex flex-col gap-5">
      {only !== "bookings"
        ? Object.entries(catalogue.system).map(([group, items]) => (
            <fieldset key={group}>
              <legend className="mb-2 type-headline text-label-1">{GROUP_KEYS[group] ? t(GROUP_KEYS[group]!) : group}</legend>
              <div className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
                {items.map((p) => (
                  <label key={p.name} className={cn("flex items-start gap-2 type-callout text-label-1", off(p.name) && "text-label-3")} title={why(p.name) ?? p.name} data-not-held={why(p.name) ? "true" : undefined} data-permission={p.name}>
                    <Checkbox className="mt-0.5" checked={value.has(p.name)} disabled={off(p.name)} onCheckedChange={(v) => onToggle(p.name, v === true)} />
                    {/* the API key is in the tooltip, not under every label (UI/UX review §3) */}
                    <span>
                      {permLabel(t, p.name, p.description)}
                      <DisabledHint why={why(p.name)} />
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
          ))
        : null}
      <fieldset>
        <legend className="mb-2 type-headline text-label-1">{t("crbs.perm.bookingsScope")}</legend>
        {book.room ? (
          <div className="mb-2 flex flex-col gap-1.5">
            {book.room.map((p) => (
              <label key={p.name} className={cn("flex items-center gap-2 type-callout text-label-1", off(p.name) && "text-label-3")} title={why(p.name)}>
                <Checkbox checked={value.has(p.name)} disabled={off(p.name)} onCheckedChange={(v) => onToggle(p.name, v === true)} />
                <span>
                  {permLabel(t, p.name, p.description)}
                  <DisabledHint why={why(p.name)} />
                </span>
              </label>
            ))}
          </div>
        ) : null}
        {phone ? (
          <div className="flex flex-col gap-4" data-testid="perm-book-groups">
            {(["book_single", "book_recur"] as const).map((g) => (
              <fieldset key={g} className="rounded-xl bg-(--mat-thick-solid) px-3 py-1 edge-hairline">
                <legend className="px-1 type-callout font-semibold text-label-1">{t(GROUP_KEYS[g]!)}</legend>
                {BOOK_ACTIONS.map((a) => {
                  const name = `${g}.${a}`;
                  return (
                    <label key={a} className={cn("flex min-h-11 items-center gap-3 type-callout text-label-1 not-last:hairline-b", off(name) && "text-label-3")} title={why(name)} data-not-held={why(name) ? "true" : undefined} data-permission={name}>
                      <Checkbox checked={value.has(name)} disabled={off(name)} onCheckedChange={(v) => onToggle(name, v === true)} />
                      <span>
                        {t(`crbs.perm.action_${a}` as MessageKey)}
                        <DisabledHint why={why(name)} />
                      </span>
                    </label>
                  );
                })}
              </fieldset>
            ))}
          </div>
        ) : (
        <div className="overflow-x-auto rounded-xl bg-(--mat-thick-solid) edge-hairline">
          <table className="w-full border-separate border-spacing-0 type-callout">
            <thead>
              <tr>
                <th scope="col" className="px-3 py-2 text-left font-medium text-label-3 edge-hairline-b">
                  {t("crbs.perm.action")}
                </th>
                <th scope="col" className="w-28 px-3 py-2 text-center font-medium text-label-1 edge-hairline-b">
                  {t("crbs.perm.group.book_single")}
                </th>
                <th scope="col" className="w-28 px-3 py-2 text-center font-medium text-label-1 edge-hairline-b">
                  {t("crbs.perm.group.book_recur")}
                </th>
              </tr>
            </thead>
            <tbody>
              {BOOK_ACTIONS.map((a) => (
                <tr key={a}>
                  <th scope="row" className="px-3 py-1.5 text-left font-normal text-label-1 edge-hairline-b">
                    {t(`crbs.perm.action_${a}` as MessageKey)}
                  </th>
                  {(["book_single", "book_recur"] as const).map((g) => {
                    const name = `${g}.${a}`;
                    return (
                      <td key={g} className="px-3 py-1.5 text-center edge-hairline-b">
                        <span className="inline-flex flex-col items-center gap-0.5" title={why(name)}>
                          <Checkbox aria-label={`${t(GROUP_KEYS[g]!)}: ${t(`crbs.perm.action_${a}` as MessageKey)}`} checked={value.has(name)} disabled={off(name)} onCheckedChange={(v) => onToggle(name, v === true)} />
                          <DisabledHint why={why(name)} />
                        </span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        )}
      </fieldset>
    </div>
  );
}
