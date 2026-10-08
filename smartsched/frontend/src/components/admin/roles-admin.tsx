"use client";
/**
 * /admin/roles (CRBS `Roles`): the role list with member counts, and an editor with the four booking
 * limits and the permission matrix grouped like CRBS (`Permissions_model::get_scoped`): system and setup
 * permissions as lists, booking permissions as a table with single and recurring side by side.
 */
import { Loader2, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { crbs, crbsError, usePermissionCatalogue, useCrbsMutation, useRoles, type PermissionCatalogue, type Role, type RoleIn } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import { Alert, ConfirmDialog, Field, LimitInput, Loading, PageTitle } from "./kit";
import { useErrorToast } from "./admin-gate";

const GROUP_KEYS: Record<string, MessageKey> = {
  system: "crbs.perm.group.system",
  setup: "crbs.perm.group.setup",
  planning: "crbs.perm.group.planning",
  room: "crbs.perm.group.room",
  book_single: "crbs.perm.group.book_single",
  book_recur: "crbs.perm.group.book_recur",
};
const BOOK_ACTIONS = ["create", "edit_other_booking", "cancel_other_booking", "set_user", "set_department", "view_other_notes", "view_other_users"] as const;

/** Translated label for a permission name; falls back to the backend description. */
export function permLabel(t: (k: MessageKey) => string, name: string, description?: string | null): string {
  const key = `crbs.perm.${name.replace(".", "_")}` as MessageKey;
  const out = t(key);
  return out === key ? (description ?? name) : out;
}

export function RolesAdmin() {
  const { t } = useI18n();
  const roles = useRoles();
  const [selectedId, setSelectedId] = useState<number | "new" | null>(null);
  const current = selectedId === "new" ? null : (roles.data?.find((r) => r.id === selectedId) ?? roles.data?.[0] ?? null);
  const editing = selectedId === "new" ? "new" : current;
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
          <nav aria-label={t("crbs.admin.roles.title")}>
            <Card variant="glass" className="py-1">
              <ul>
                {(roles.data ?? []).map((r) => {
                  const active = editing !== "new" && editing?.id === r.id;
                  return (
                    <li key={r.id}>
                      <button
                        type="button"
                        aria-current={active ? "true" : undefined}
                        onClick={() => setSelectedId(r.id)}
                        className={cn("flex w-full items-center justify-between gap-2 px-4 py-2 text-left outline-none focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus)", active ? "bg-tint-soft" : "hover:bg-fill-3")}
                      >
                        <span className="min-w-0">
                          <span className="block truncate type-headline text-label-1">{r.name}</span>
                          <span className="block type-footnote text-label-3">{t("crbs.roles.summary", { users: r.user_count, perms: r.permissions.length })}</span>
                        </span>
                        {r.code === "ADMIN" ? <ShieldCheck className="size-4 shrink-0 text-label-2" aria-label={t("crbs.roles.locked")} /> : null}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </Card>
          </nav>
          {editing ? <RoleEditor key={editing === "new" ? "new" : editing.id} role={editing === "new" ? null : editing} onSaved={(r) => setSelectedId(r.id)} onDeleted={() => setSelectedId(null)} /> : null}
        </div>
      )}
    </div>
  );
}

function RoleEditor({ role, onSaved, onDeleted }: { role: Role | null; onSaved: (r: Role) => void; onDeleted: () => void }) {
  const { t } = useI18n();
  const catalogue = usePermissionCatalogue();
  const locked = role?.code === "ADMIN";
  const [name, setName] = useState(role?.name ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
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
  const body = (): RoleIn => ({ name: name.trim(), description: description.trim() || null, ...limits, permissions: [...perms].sort() });
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
    <Card variant="glass" className="gap-5 px-5" data-testid="role-editor">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("crbs.common.name")} htmlFor="role-name">
          <Input id="role-name" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label={t("crbs.common.description")} htmlFor="role-desc">
          <Input id="role-desc" value={description} maxLength={255} onChange={(e) => setDescription(e.target.value)} />
        </Field>
      </div>
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
      {catalogue.data ? <PermissionMatrix catalogue={catalogue.data} value={perms} onToggle={toggle} disabled={locked} /> : <Loading />}
      {error ? <Alert tone="error">{error}</Alert> : null}
      <div className="flex flex-wrap justify-between gap-2">
        {role && !locked ? (
          <Button variant="ghost" className="text-status-infeasible-fg" onClick={() => setConfirmDelete(true)}>
            <Trash2 aria-hidden />
            {t("crbs.roles.delete")}
          </Button>
        ) : (
          <span />
        )}
        <Button
          disabled={save.isPending || !name.trim()}
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
        >
          {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
          {role ? t("crbs.common.save") : t("crbs.roles.create")}
        </Button>
      </div>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={t("crbs.roles.deleteTitle", { name: role?.name ?? "" })}
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

export function PermissionMatrix({ catalogue, value, onToggle, disabled, only }: { catalogue: PermissionCatalogue; value: ReadonlySet<string>; onToggle: (p: string, on: boolean) => void; disabled?: boolean; only?: "bookings" }) {
  const { t } = useI18n();
  const book = catalogue.bookings;
  const desc = useMemo(() => {
    const m = new Map<string, string | null | undefined>();
    for (const scope of [catalogue.system, catalogue.bookings]) for (const items of Object.values(scope)) for (const p of items) m.set(p.name, p.description);
    return m;
  }, [catalogue]);
  return (
    <div className="flex flex-col gap-5">
      {only !== "bookings"
        ? Object.entries(catalogue.system).map(([group, items]) => (
            <fieldset key={group}>
              <legend className="mb-2 type-headline text-label-1">{GROUP_KEYS[group] ? t(GROUP_KEYS[group]!) : group}</legend>
              <div className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
                {items.map((p) => (
                  <label key={p.name} className="flex items-start gap-2 type-callout text-label-1">
                    <Checkbox className="mt-0.5" checked={value.has(p.name)} disabled={disabled} onCheckedChange={(v) => onToggle(p.name, v === true)} />
                    <span>
                      {permLabel(t, p.name, p.description)}
                      <span className="block font-mono type-caption text-label-3">{p.name}</span>
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
              <label key={p.name} className="flex items-center gap-2 type-callout text-label-1">
                <Checkbox checked={value.has(p.name)} disabled={disabled} onCheckedChange={(v) => onToggle(p.name, v === true)} />
                {permLabel(t, p.name, p.description)}
              </label>
            ))}
          </div>
        ) : null}
        <div className="overflow-x-auto rounded-xl bg-(--mat-thick-solid) shadow-[0_0_0_1px_var(--hairline)]">
          <table className="w-full border-separate border-spacing-0 type-callout">
            <thead>
              <tr>
                <th scope="col" className="px-3 py-2 text-left font-medium text-label-3 shadow-[inset_0_-1px_0_var(--hairline)]">
                  {t("crbs.perm.action")}
                </th>
                <th scope="col" className="w-28 px-3 py-2 text-center font-medium text-label-1 shadow-[inset_0_-1px_0_var(--hairline)]">
                  {t("crbs.perm.group.book_single")}
                </th>
                <th scope="col" className="w-28 px-3 py-2 text-center font-medium text-label-1 shadow-[inset_0_-1px_0_var(--hairline)]">
                  {t("crbs.perm.group.book_recur")}
                </th>
              </tr>
            </thead>
            <tbody>
              {BOOK_ACTIONS.map((a) => (
                <tr key={a}>
                  <th scope="row" className="px-3 py-1.5 text-left font-normal text-label-1 shadow-[inset_0_-1px_0_var(--hairline)]">
                    {t(`crbs.perm.action_${a}` as MessageKey)}
                  </th>
                  {(["book_single", "book_recur"] as const).map((g) => {
                    const name = `${g}.${a}`;
                    return (
                      <td key={g} className="px-3 py-1.5 text-center shadow-[inset_0_-1px_0_var(--hairline)]">
                        <span className="inline-flex">
                          <Checkbox aria-label={`${t(GROUP_KEYS[g]!)}: ${desc.get(name) ?? name}`} checked={value.has(name)} disabled={disabled} onCheckedChange={(v) => onToggle(name, v === true)} />
                        </span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </fieldset>
    </div>
  );
}
