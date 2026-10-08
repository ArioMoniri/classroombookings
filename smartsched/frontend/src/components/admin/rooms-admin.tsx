"use client";
/**
 * /admin/rooms (CRBS `setup/rooms/{Groups,Rooms,Fields,Acl}`): room groups with drag reorder and members,
 * each room's booking details (group, owner, location, icon, notes, photo, bookable, custom field values),
 * custom fields (TEXT / CHECKBOX / SELECT) and the access-control list per room or room group.
 * New rooms (code, name, group, capacity) are created here and deleted here (CRBS `Rooms::add/delete`, UI gap
 * audit #4; `POST/DELETE /rooms` accept setup.rooms); later capacity changes stay on /rooms (the room master).
 * `?tab=rooms&new=1` (⌘K "New room") opens the create form.
 */
import { Building2, ImageUp, Loader2, Maximize2, Pencil, Plus, ShieldQuestion, Trash2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  crbs,
  crbsAdmin,
  crbsError,
  useAcl,
  useBookingContext,
  useAdminRooms,
  useCrbsMutation,
  useCustomFields,
  useDepartments,
  usePermissionCatalogue,
  useRoles,
  useRoomFieldValues,
  useRoomGroups,
  useUserSearch,
  type AclIn,
  type AdminRoom,
  type CustomField,
  type RoomGroup,
} from "@/lib/api/crbs";
import { usePermissions } from "@/lib/permissions";
import { useI18n } from "@/lib/i18n/provider";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import { useIsPhone } from "@/components/bookings/use-is-phone";
import { Alert, ConfirmDialog, Field, Loading, PageTitle, SelectField } from "./kit";
import { useErrorToast } from "./admin-gate";
import { EntityIcon, IconPicker } from "./icons";
import { permLabel } from "./roles-admin";
import { SortableList } from "./sortable-list";

const fold = (s: string) => s.toLocaleLowerCase("tr-TR");

export function RoomsAdmin() {
  const { t } = useI18n();
  const { can } = usePermissions();
  const rooms = can("setup.rooms");
  const acl = can("setup.rooms_acl");
  const params = useSearchParams();
  const asked = params.get("tab");
  const [tab, setTab] = useState(() => (asked && ["groups", "rooms", "fields", "acl"].includes(asked) && (asked === "acl" ? acl : rooms) ? asked : rooms ? "groups" : "acl"));
  return (
    <div className="flex flex-col gap-5">
      <PageTitle title={t("crbs.admin.rooms.title")} subtitle={t("crbs.admin.rooms.lead")} />
      <Tabs value={tab} onValueChange={(v) => setTab(String(v))}>
        <TabsList aria-label={t("crbs.admin.rooms.title")}>
          {rooms ? <TabsTrigger value="groups">{t("crbs.rooms.tabGroups")}</TabsTrigger> : null}
          {rooms ? <TabsTrigger value="rooms">{t("crbs.rooms.tabRooms")}</TabsTrigger> : null}
          {rooms ? <TabsTrigger value="fields">{t("crbs.rooms.tabFields")}</TabsTrigger> : null}
          {acl ? <TabsTrigger value="acl">{t("crbs.rooms.tabAcl")}</TabsTrigger> : null}
        </TabsList>
        {rooms ? (
          <TabsContent value="groups">
            <GroupsTab />
          </TabsContent>
        ) : null}
        {rooms ? (
          <TabsContent value="rooms">
            <RoomsTab />
          </TabsContent>
        ) : null}
        {rooms ? (
          <TabsContent value="fields">
            <FieldsTab />
          </TabsContent>
        ) : null}
        {acl ? (
          <TabsContent value="acl">
            <AclTab />
          </TabsContent>
        ) : null}
      </Tabs>
    </div>
  );
}

/* ------------------------------------------------------------------------------------- groups */

function GroupsTab() {
  const { t } = useI18n();
  const groups = useRoomGroups();
  const rooms = useAdminRooms();
  const [order, setOrder] = useState<RoomGroup[] | null>(null);
  const [editing, setEditing] = useState<RoomGroup | "new" | null>(null);
  const [deleting, setDeleting] = useState<RoomGroup | null>(null);
  const toastError = useErrorToast();
  const keys = [["crbs", "room-groups"], ["crbs", "admin-rooms"], ["crbs", "context"], ["crbs", "grid"]];
  const save = useCrbsMutation((ids: number[]) => crbs.roomAdmin.orderGroups(ids), keys);
  const fromBuildings = useCrbsMutation(() => crbs.roomAdmin.groupsFromBuildings(), keys);
  const del = useCrbsMutation((g: RoomGroup) => crbs.roomAdmin.deleteGroup(g.id), keys);
  const list = order ?? groups.data ?? [];
  const ungrouped = (rooms.data ?? []).filter((r) => r.room_group_id == null).length;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="type-callout text-label-2">{t("crbs.rooms.groupsLead", { n: ungrouped })}</p>
        <div className="flex gap-2">
          <Button variant="outline" disabled={fromBuildings.isPending} onClick={() => fromBuildings.mutate(undefined, { onSuccess: (g) => toast.success(t("crbs.rooms.fromBuildingsDone", { n: g.length })), onError: toastError })} data-testid="groups-from-buildings">
            <Building2 aria-hidden />
            {t("crbs.rooms.fromBuildings")}
          </Button>
          <Button onClick={() => setEditing("new")}>
            <Plus aria-hidden />
            {t("crbs.rooms.newGroup")}
          </Button>
        </div>
      </div>
      <Card variant="glass" className="overflow-hidden py-0">
        {groups.isLoading ? (
          <Loading className="px-4" />
        ) : list.length === 0 ? (
          <p className="px-4 py-5 type-callout text-label-2">{t("crbs.rooms.noGroups")}</p>
        ) : (
          <SortableList
            label={t("crbs.rooms.tabGroups")}
            items={list.map((g) => ({ ...g, label: g.name }))}
            onReorder={(next) => {
              setOrder(next);
              save.mutate(
                next.map((g) => g.id),
                { onSuccess: () => setOrder(null), onError: (e) => (toastError(e), setOrder(null)) },
              );
            }}
            render={(g) => (
              <div className="flex items-center justify-between gap-2">
                <span className="min-w-0">
                  <span className="block type-headline text-label-1">{g.name}</span>
                  <span className="block truncate type-footnote text-label-2">{[t("crbs.rooms.roomCount", { n: g.room_count }), g.description].filter(Boolean).join(" · ")}</span>
                </span>
                <span className="flex shrink-0">
                  <Button variant="ghost" size="icon-sm" aria-label={t("crbs.rooms.editNamed", { name: g.name })} onClick={() => setEditing(g)}>
                    <Pencil />
                  </Button>
                  <Button variant="ghost" size="icon-sm" aria-label={t("crbs.rooms.deleteNamed", { name: g.name })} onClick={() => setDeleting(g)}>
                    <Trash2 />
                  </Button>
                </span>
              </div>
            )}
          />
        )}
      </Card>
      <p className="type-footnote text-label-3">{t("crbs.sort.hint")}</p>
      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-lg">{editing !== null ? <GroupForm key={editing === "new" ? "new" : editing.id} group={editing === "new" ? null : editing} rooms={rooms.data ?? []} onClose={() => setEditing(null)} /> : null}</DialogContent>
      </Dialog>
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t("crbs.rooms.deleteGroupTitle", { name: deleting?.name ?? "" })}
        description={t("crbs.rooms.deleteGroupBody")}
        confirmLabel={t("crbs.common.delete")}
        destructive
        busy={del.isPending}
        onConfirm={() => deleting && del.mutate(deleting, { onSuccess: () => setDeleting(null), onError: toastError })}
      />
    </div>
  );
}

function GroupForm({ group, rooms, onClose }: { group: RoomGroup | null; rooms: AdminRoom[]; onClose: () => void }) {
  const { t } = useI18n();
  const [name, setName] = useState(group?.name ?? "");
  const [description, setDescription] = useState(group?.description ?? "");
  const [members, setMembers] = useState<Set<number>>(new Set(group?.room_ids ?? []));
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);
  const body = { name: name.trim(), description: description.trim() || null, room_ids: [...members] };
  const save = useCrbsMutation(() => (group ? crbs.roomAdmin.updateGroup(group.id, body) : crbs.roomAdmin.createGroup(body)), [["crbs", "room-groups"], ["crbs", "admin-rooms"], ["crbs", "context"], ["crbs", "grid"]]);
  const shown = rooms.filter((r) => !q || fold(`${r.code} ${r.display_name}`).includes(fold(q)));
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined, { onSuccess: () => (toast.success(t("crbs.common.saved")), onClose()), onError: (err) => setError(bookingErrorMessage(crbsError(err), t)) });
      }}
    >
      <DialogHeader>
        <DialogTitle>{group ? group.name : t("crbs.rooms.newGroup")}</DialogTitle>
        <DialogDescription>{t("crbs.rooms.membersHint")}</DialogDescription>
      </DialogHeader>
      <Field label={t("crbs.common.name")} htmlFor="grp-name">
        <Input id="grp-name" required maxLength={32} value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label={t("crbs.common.description")} htmlFor="grp-desc">
        <Input id="grp-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
      </Field>
      <Field label={t("crbs.rooms.members", { n: members.size })} htmlFor="grp-q">
        <Input id="grp-q" type="search" placeholder={t("crbs.rooms.searchRooms")} value={q} onChange={(e) => setQ(e.target.value)} />
      </Field>
      <ul className="grid max-h-60 grid-cols-2 gap-1 overflow-auto rounded-xl bg-fill-3 p-2 sm:grid-cols-3">
        {shown.map((r) => (
          <li key={r.id}>
            <label className="flex items-center gap-2 rounded-md px-1.5 py-1 type-callout text-label-1 hover:bg-fill-2">
              <Checkbox
                checked={members.has(r.id)}
                onCheckedChange={(v) =>
                  setMembers((prev) => {
                    const next = new Set(prev);
                    if (v === true) next.add(r.id);
                    else next.delete(r.id);
                    return next;
                  })
                }
              />
              <span className="truncate">{r.display_name}</span>
              {r.room_group_id && r.room_group_id !== group?.id ? <span className="truncate type-caption text-label-3">{r.room_group}</span> : null}
            </label>
          </li>
        ))}
      </ul>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose}>
          {t("crbs.common.cancel")}
        </Button>
        <Button type="submit" disabled={!name.trim() || save.isPending}>
          {t("crbs.common.save")}
        </Button>
      </DialogFooter>
    </form>
  );
}

/* -------------------------------------------------------------------------------------- rooms */

function RoomsTab() {
  const { t } = useI18n();
  const rooms = useAdminRooms();
  const groups = useRoomGroups();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [creating, setCreating] = useState(() => params.get("new") === "1");
  const [deleting, setDeleting] = useState<AdminRoom | null>(null);
  const closeCreate = () => {
    setCreating(false);
    if (params.get("new")) router.replace(`${pathname}?tab=rooms`, { scroll: false });
  };
  const [group, setGroup] = useState("all");
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<AdminRoom | null>(null);
  const [order, setOrder] = useState<AdminRoom[] | null>(null);
  const toastError = useErrorToast();
  const saveOrder = useCrbsMutation((ids: number[]) => crbs.roomAdmin.orderRooms(ids), [["crbs", "admin-rooms"], ["crbs", "grid"]]);
  const filtered = useMemo(
    () => (rooms.data ?? []).filter((r) => (group === "all" ? true : group === "none" ? r.room_group_id == null : r.room_group_id === Number(group))).filter((r) => !q || fold(`${r.code} ${r.display_name} ${r.location ?? ""}`).includes(fold(q))),
    [rooms.data, group, q],
  );
  const sortable = group !== "all" && group !== "none" && !q;
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-2 sm:grid-cols-[1fr_220px_auto]">
        <Input type="search" aria-label={t("crbs.rooms.searchRooms")} placeholder={t("crbs.rooms.searchRooms")} value={q} onChange={(e) => setQ(e.target.value)} />
        <SelectField aria-label={t("crbs.export.group")} value={group} onChange={(e) => setGroup(e.target.value)}>
          <option value="all">{t("crbs.export.allGroups")}</option>
          {(groups.data ?? []).map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
          <option value="none">{t("crbs.rooms.noGroup")}</option>
        </SelectField>
        <Button onClick={() => setCreating(true)} data-testid="room-new">
          <Plus aria-hidden />
          {t("admingaps.rooms.new")}
        </Button>
      </div>
      <Card variant="glass" className="overflow-hidden py-0">
        {rooms.isLoading ? (
          <Loading className="px-4" />
        ) : sortable ? (
          <SortableList
            label={t("crbs.rooms.tabRooms")}
            items={(order ?? filtered).map((r) => ({ ...r, label: r.display_name }))}
            onReorder={(next) => {
              setOrder(next);
              saveOrder.mutate(
                next.map((r) => r.id),
                { onSuccess: () => setOrder(null), onError: (e) => (toastError(e), setOrder(null)) },
              );
            }}
            render={(r) => <RoomRow room={r} onEdit={() => setEditing(r)} onDelete={() => setDeleting(r)} />}
          />
        ) : (
          <ul>
            {filtered.map((r) => (
              <li key={r.id} className="px-4 py-2 shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none">
                <RoomRow room={r} onEdit={() => setEditing(r)} onDelete={() => setDeleting(r)} />
              </li>
            ))}
          </ul>
        )}
      </Card>
      {sortable ? <p className="type-footnote text-label-3">{t("crbs.sort.hint")}</p> : <p className="type-footnote text-label-3">{t("crbs.rooms.orderHint")}</p>}
      <RoomSheet room={editing} onClose={() => setEditing(null)} />
      <Dialog open={creating} onOpenChange={(o) => !o && closeCreate()}>
        <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-lg" data-testid="room-create-dialog">
          {creating ? <RoomCreateForm groups={groups.data ?? []} defaultGroup={group !== "all" && group !== "none" ? group : ""} onClose={closeCreate} /> : null}
        </DialogContent>
      </Dialog>
      <DeleteRoomDialog room={deleting} onClose={() => setDeleting(null)} />
    </div>
  );
}

const ROOM_KEYS = [["crbs", "admin-rooms"], ["crbs", "room-groups"], ["crbs", "grid"], ["crbs", "context"], ["crbs", "booking-rooms"], ["rooms"]];

/** CRBS `rooms_add.php` (create): code, display name, group, capacity and bookable; the rest is in the edit sheet. */
function RoomCreateForm({ groups, defaultGroup, onClose }: { groups: RoomGroup[]; defaultGroup: string; onClose: () => void }) {
  const { t } = useI18n();
  const [f, setF] = useState({ code: "", display_name: "", room_group_id: defaultGroup, capacity: "", is_bookable: true });
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((p) => ({ ...p, [k]: v }));
  const save = useCrbsMutation(async () => {
    const room = await crbsAdmin.rooms.create({ code: f.code.trim(), display_name: f.display_name.trim() || null, capacity: f.capacity ? Math.max(0, Number(f.capacity)) : 0, is_bookable: f.is_bookable });
    if (f.room_group_id) await crbs.roomAdmin.updateRoom(room.id, { room_group_id: Number(f.room_group_id) });
    return room;
  }, ROOM_KEYS);
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        save.mutate(undefined, {
          onSuccess: (r) => (toast.success(t("admingaps.rooms.created", { name: r.display_name })), onClose()),
          onError: (err) => {
            const ce = crbsError(err);
            setError(ce.status === 409 ? t("admingaps.rooms.codeTaken", { code: f.code.trim() }) : bookingErrorMessage(ce, t));
          },
        });
      }}
    >
      <DialogHeader>
        <DialogTitle>{t("admingaps.rooms.new")}</DialogTitle>
        <DialogDescription>{t("admingaps.rooms.newHint")}</DialogDescription>
      </DialogHeader>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("admingaps.rooms.code")} htmlFor="rm-new-code" hint={t("admingaps.rooms.codeHint")}>
          <Input id="rm-new-code" required maxLength={32} autoComplete="off" placeholder="A 101" value={f.code} onChange={(e) => set("code", e.target.value)} data-testid="room-new-code" />
        </Field>
        <Field label={t("crbs.rooms.displayName")} htmlFor="rm-new-name" hint={t("admingaps.rooms.nameHint")}>
          <Input id="rm-new-name" maxLength={64} value={f.display_name} onChange={(e) => set("display_name", e.target.value)} data-testid="room-new-name" />
        </Field>
        <Field label={t("crbs.export.group")} htmlFor="rm-new-group" hint={t("crbs.rooms.groupHint")}>
          <SelectField id="rm-new-group" value={f.room_group_id} onChange={(e) => set("room_group_id", e.target.value)} data-testid="room-new-group">
            <option value="">{t("crbs.rooms.noGroup")}</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </SelectField>
        </Field>
        <Field label={t("admingaps.rooms.capacity")} htmlFor="rm-new-cap">
          <Input id="rm-new-cap" type="number" min={0} inputMode="numeric" value={f.capacity} onChange={(e) => set("capacity", e.target.value)} data-testid="room-new-capacity" />
        </Field>
      </div>
      <label className="flex items-center justify-between gap-3 type-callout text-label-1">
        {t("crbs.rooms.bookable")}
        <Switch checked={f.is_bookable} onCheckedChange={(v) => set("is_bookable", v)} aria-label={t("crbs.rooms.bookable")} />
      </label>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose}>
          {t("crbs.common.cancel")}
        </Button>
        <Button type="submit" disabled={!f.code.trim() || save.isPending} data-testid="room-create">
          {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
          {t("crbs.common.create")}
        </Button>
      </DialogFooter>
    </form>
  );
}

/** CRBS `room.delete.warning`; the backend refuses while bookings exist (their history stays), so say why. */
function DeleteRoomDialog({ room, onClose }: { room: AdminRoom | null; onClose: () => void }) {
  const { t } = useI18n();
  const [error, setError] = useState<string | null>(null);
  const del = useCrbsMutation((id: number) => crbsAdmin.rooms.remove(id), ROOM_KEYS);
  return (
    <ConfirmDialog
      open={!!room}
      onOpenChange={(o) => !o && (setError(null), onClose())}
      title={t("admingaps.rooms.deleteTitle", { name: room?.display_name ?? "" })}
      description={t("admingaps.rooms.deleteBody")}
      confirmLabel={t("crbs.common.delete")}
      destructive
      busy={del.isPending}
      onConfirm={() =>
        room &&
        del.mutate(room.id, {
          onSuccess: () => (toast.success(t("crbs.common.deleted")), setError(null), onClose()),
          onError: (err) => {
            const ce = crbsError(err);
            setError(
              ce.code === "room_has_bookings"
                ? t("admingaps.rooms.hasBookings", { n: Number(ce.data.bookings ?? 0), active: Number(ce.data.active_bookings ?? 0) })
                : bookingErrorMessage(ce, t),
            );
          },
        })
      }
    >
      {error ? (
        <Alert tone="warning" testId="room-delete-refused">
          {error}
        </Alert>
      ) : null}
    </ConfirmDialog>
  );
}

function RoomRow({ room: r, onEdit, onDelete }: { room: AdminRoom; onEdit: () => void; onDelete: () => void }) {
  const { t } = useI18n();
  const { can } = usePermissions();
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="flex min-w-0 items-center gap-2">
        <EntityIcon name={r.icon} />
        <span className="min-w-0">
          <span className="block type-headline text-label-1">
            {r.display_name}
            <span className="ml-2 type-footnote font-normal text-label-3">{t("crbs.grid.seats", { n: r.capacity })}</span>
          </span>
          <span className="block truncate type-footnote text-label-2">{[r.room_group ?? t("crbs.rooms.noGroup"), r.location, r.owner_name ? t("crbs.detail.owner", { name: r.owner_name }) : null].filter(Boolean).join(" · ")}</span>
        </span>
      </span>
      <span className="flex shrink-0 items-center gap-2">
        {!r.is_bookable ? (
          <Badge variant="secondary" tone="preoccupied">
            {t("crbs.rooms.notBookable")}
          </Badge>
        ) : null}
        {can(["setup.rooms_acl", "setup.users"]) ? (
          <Button variant="ghost" size="icon-sm" render={<Link href={`/admin/access?room=${r.id}`} />} nativeButton={false} aria-label={t("admingaps.access.checkRoom", { name: r.display_name })} data-testid={`room-check-access-${r.code}`}>
            <ShieldQuestion />
          </Button>
        ) : null}
        <Button variant="ghost" size="icon-sm" aria-label={t("crbs.rooms.editNamed", { name: r.display_name })} onClick={onEdit} data-testid={`room-edit-${r.code}`}>
          <Pencil />
        </Button>
        <Button variant="ghost" size="icon-sm" aria-label={t("crbs.rooms.deleteNamed", { name: r.display_name })} onClick={onDelete} data-testid={`room-delete-${r.code}`}>
          <Trash2 />
        </Button>
      </span>
    </div>
  );
}

function RoomSheet({ room, onClose }: { room: AdminRoom | null; onClose: () => void }) {
  const phone = useIsPhone();
  return (
    <Sheet open={!!room} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side={phone ? "bottom" : "right"} className="gap-0 data-[side=right]:sm:max-w-lg">
        {room ? <RoomForm key={room.id} room={room} onClose={onClose} /> : null}
      </SheetContent>
    </Sheet>
  );
}

function RoomForm({ room, onClose }: { room: AdminRoom; onClose: () => void }) {
  const { t } = useI18n();
  const { can } = usePermissions();
  const groups = useRoomGroups();
  const fields = useCustomFields();
  const values = useRoomFieldValues(room.id);
  const users = useUserSearch({ limit: 500, enabled: true, sort: "displayname" }, can("setup.users"));
  const [f, setF] = useState({
    display_name: room.display_name,
    room_group_id: room.room_group_id ? String(room.room_group_id) : "",
    owner_user_id: room.owner_user_id ? String(room.owner_user_id) : "",
    location: room.location ?? "",
    icon: room.icon ?? null,
    notes: room.notes ?? "",
    is_bookable: room.is_bookable,
  });
  const [fieldDraft, setFieldDraft] = useState<Record<string, unknown>>({});
  const [error, setError] = useState<string | null>(null);
  const keys = [["crbs", "admin-rooms"], ["crbs", "room-groups"], ["crbs", "grid"], ["crbs", "context"], ["crbs", "room-fields", room.id]];
  const save = useCrbsMutation(async () => {
    const out = await crbs.roomAdmin.updateRoom(room.id, {
      display_name: f.display_name.trim() || null,
      ...(f.room_group_id ? { room_group_id: Number(f.room_group_id) } : {}),
      owner_user_id: f.owner_user_id ? Number(f.owner_user_id) : null,
      location: f.location.trim() || null,
      icon: f.icon,
      notes: f.notes.trim() || null,
      is_bookable: f.is_bookable,
    });
    if (Object.keys(fieldDraft).length) await crbs.roomAdmin.putRoomFields(room.id, fieldDraft);
    return out;
  }, keys);
  const photo = useCrbsMutation((file: File) => crbs.roomAdmin.uploadPhoto(room.id, file), keys);
  const dropPhoto = useCrbsMutation(() => crbs.roomAdmin.deletePhoto(room.id), keys);
  const [photoUrl, setPhotoUrl] = useState(room.photo_url);
  // CRBS Rooms::photo opens the full image (UI gap audit #25)
  const [zoom, setZoom] = useState(false);
  const toastError = useErrorToast();
  const val = (fid: number) => (String(fid) in fieldDraft ? fieldDraft[String(fid)] : values.data?.[String(fid)]);
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((p) => ({ ...p, [k]: v }));
  return (
    <>
      <SheetHeader className="px-5 pt-5">
        <SheetTitle className="type-title-3">{room.display_name}</SheetTitle>
        <p className="type-footnote text-label-3">
          {room.code} · {t("crbs.grid.seats", { n: room.capacity })}
        </p>
      </SheetHeader>
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-5 pb-4">
        <Field label={t("crbs.rooms.displayName")} htmlFor="rm-name">
          <Input id="rm-name" maxLength={64} value={f.display_name} onChange={(e) => set("display_name", e.target.value)} />
        </Field>
        <Field label={t("crbs.export.group")} htmlFor="rm-group" hint={t("crbs.rooms.groupHint")}>
          <SelectField id="rm-group" value={f.room_group_id} onChange={(e) => set("room_group_id", e.target.value)}>
            {!f.room_group_id ? <option value="">{t("crbs.rooms.noGroup")}</option> : null}
            {(groups.data ?? []).map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </SelectField>
        </Field>
        <Field label={t("crbs.rooms.owner")} htmlFor="rm-owner" hint={t("crbs.rooms.ownerHint")}>
          <SelectField id="rm-owner" value={f.owner_user_id} onChange={(e) => set("owner_user_id", e.target.value)}>
            <option value="">{t("crbs.common.none")}</option>
            {room.owner_user_id && !users.data ? <option value={room.owner_user_id}>{room.owner_name}</option> : null}
            {(users.data?.items ?? []).map((u) => (
              <option key={u.id} value={u.id}>
                {u.displayname || u.username || u.email}
              </option>
            ))}
          </SelectField>
        </Field>
        <Field label={t("crbs.rooms.location")} htmlFor="rm-loc">
          <Input id="rm-loc" maxLength={64} value={f.location} onChange={(e) => set("location", e.target.value)} />
        </Field>
        <Field label={t("crbs.icons.label")} htmlFor="rm-icon">
          <IconPicker id="rm-icon" value={f.icon} onChange={(v) => set("icon", v)} />
        </Field>
        <Field label={t("crbs.book.notes")} htmlFor="rm-notes">
          <Textarea id="rm-notes" maxLength={255} rows={2} value={f.notes} onChange={(e) => set("notes", e.target.value)} />
        </Field>
        <label className="flex items-center justify-between gap-3 type-callout text-label-1">
          {t("crbs.rooms.bookable")}
          <Switch checked={f.is_bookable} onCheckedChange={(v) => set("is_bookable", v)} aria-label={t("crbs.rooms.bookable")} />
        </label>
        <section aria-label={t("crbs.rooms.photo")} className="flex flex-col gap-2">
          <p className="type-headline text-label-1">{t("crbs.rooms.photo")}</p>
          {photoUrl ? (
            <button type="button" onClick={() => setZoom(true)} aria-label={t("admingaps.rooms.enlargePhoto", { name: room.display_name })} className="group relative block overflow-hidden rounded-xl outline-none focus-visible:outline-2 focus-visible:outline-(--focus)" data-testid="room-photo-enlarge">
              {/* eslint-disable-next-line @next/next/no-img-element -- uploaded by an administrator, served by the backend */}
              <img src={photoUrl} alt={t("crbs.rooms.photoAlt", { name: room.display_name })} className="max-h-48 w-full object-cover" />
              <span className="absolute right-2 bottom-2 flex size-7 items-center justify-center rounded-full bg-(--mat-thick-solid) text-label-1 shadow-[0_0_0_1px_var(--hairline)]" aria-hidden>
                <Maximize2 className="size-3.5" />
              </span>
            </button>
          ) : null}
          <div className="flex gap-2">
            <Button variant="outline" size="sm" render={<label />} nativeButton={false}>
              <ImageUp aria-hidden />
              {photo.isPending ? t("crbs.common.loading") : t("crbs.rooms.uploadPhoto")}
              <input
                type="file"
                accept="image/jpeg,image/png,image/gif,image/webp"
                className="sr-only"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) photo.mutate(file, { onSuccess: (r) => setPhotoUrl(r.photo_url ? `${r.photo_url}?v=${Date.now()}` : null), onError: toastError });
                }}
              />
            </Button>
            {photoUrl ? (
              <Button variant="ghost" size="sm" onClick={() => dropPhoto.mutate(undefined, { onSuccess: () => setPhotoUrl(null), onError: toastError })}>
                <Trash2 aria-hidden />
                {t("crbs.rooms.removePhoto")}
              </Button>
            ) : null}
          </div>
        </section>
        {(fields.data ?? []).length ? (
          <section aria-label={t("crbs.rooms.tabFields")} className="flex flex-col gap-2">
            <p className="type-headline text-label-1">{t("crbs.rooms.tabFields")}</p>
            {(fields.data ?? []).map((cf) => (
              <CustomFieldInput key={cf.id} field={cf} value={val(cf.id)} onChange={(v) => setFieldDraft((d) => ({ ...d, [String(cf.id)]: v }))} />
            ))}
          </section>
        ) : null}
        {error ? <Alert tone="error">{error}</Alert> : null}
      </div>
      <Dialog open={zoom && !!photoUrl} onOpenChange={setZoom}>
        <DialogContent className="w-auto max-w-[min(96vw,1200px)] p-2 sm:max-w-[min(96vw,1200px)]" data-testid="room-photo-lightbox">
          <DialogTitle className="sr-only">{t("crbs.rooms.photoAlt", { name: room.display_name })}</DialogTitle>
          {/* eslint-disable-next-line @next/next/no-img-element -- uploaded by an administrator, served by the backend */}
          {photoUrl ? <img src={photoUrl} alt={t("crbs.rooms.photoAlt", { name: room.display_name })} className="max-h-[85dvh] w-auto max-w-full rounded-xl object-contain" /> : null}
        </DialogContent>
      </Dialog>
      <SheetFooter className="hairline-t flex-row justify-end gap-2 px-5 py-3">
        <Button variant="ghost" onClick={onClose}>
          {t("crbs.common.cancel")}
        </Button>
        <Button
          disabled={save.isPending}
          data-testid="room-save"
          onClick={() => save.mutate(undefined, { onSuccess: () => (toast.success(t("crbs.common.saved")), onClose()), onError: (e) => setError(bookingErrorMessage(crbsError(e), t)) })}
        >
          {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
          {t("crbs.common.save")}
        </Button>
      </SheetFooter>
    </>
  );
}

function CustomFieldInput({ field, value, onChange }: { field: CustomField; value: unknown; onChange: (v: unknown) => void }) {
  const { t } = useI18n();
  const id = `cf-${field.id}`;
  if (field.type === "CHECKBOX")
    return (
      <label className="flex items-center gap-2 type-callout text-label-1">
        <Checkbox checked={value === true} onCheckedChange={(v) => onChange(v === true)} />
        {field.name}
      </label>
    );
  if (field.type === "SELECT")
    return (
      <Field label={field.name} htmlFor={id}>
        <SelectField id={id} value={value == null ? "" : String(value)} onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}>
          <option value="">{t("crbs.common.none")}</option>
          {field.options.map((o) => (
            <option key={o.id} value={o.id}>
              {o.value}
            </option>
          ))}
        </SelectField>
      </Field>
    );
  return (
    <Field label={field.name} htmlFor={id}>
      <Input id={id} maxLength={255} value={typeof value === "string" ? value : ""} onChange={(e) => onChange(e.target.value)} />
    </Field>
  );
}

/* ------------------------------------------------------------------------------------- fields */

function FieldsTab() {
  const { t } = useI18n();
  const fields = useCustomFields();
  const [editing, setEditing] = useState<CustomField | "new" | null>(null);
  const [deleting, setDeleting] = useState<CustomField | null>(null);
  const toastError = useErrorToast();
  const del = useCrbsMutation((f: CustomField) => crbs.roomAdmin.deleteField(f.id), [["crbs", "fields"], ["crbs", "room-fields"]]);
  const typeLabel = { TEXT: t("crbs.fields.text"), CHECKBOX: t("crbs.fields.checkbox"), SELECT: t("crbs.fields.select") };
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <p className="type-callout text-label-2">{t("crbs.fields.lead")}</p>
        <Button onClick={() => setEditing("new")}>
          <Plus aria-hidden />
          {t("crbs.fields.new")}
        </Button>
      </div>
      <Card variant="glass" className="py-0">
        {fields.isLoading ? (
          <Loading className="px-4" />
        ) : (fields.data ?? []).length === 0 ? (
          <p className="px-4 py-5 type-callout text-label-2">{t("crbs.fields.none")}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">{t("crbs.common.name")}</TableHead>
                <TableHead>{t("crbs.fields.type")}</TableHead>
                <TableHead className="hidden sm:table-cell">{t("crbs.fields.options")}</TableHead>
                <TableHead className="w-24 pr-4">
                  <span className="sr-only">{t("crbs.common.actions")}</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(fields.data ?? []).map((f) => (
                <TableRow key={f.id}>
                  <TableCell className="pl-4 font-medium text-label-1">{f.name}</TableCell>
                  <TableCell className="text-label-2">{typeLabel[f.type]}</TableCell>
                  <TableCell className="hidden text-label-2 sm:table-cell">{f.options.map((o) => o.value).join(", ")}</TableCell>
                  <TableCell className="pr-4 text-right whitespace-nowrap">
                    <Button variant="ghost" size="icon-sm" aria-label={t("crbs.rooms.editNamed", { name: f.name })} onClick={() => setEditing(f)}>
                      <Pencil />
                    </Button>
                    <Button variant="ghost" size="icon-sm" aria-label={t("crbs.rooms.deleteNamed", { name: f.name })} onClick={() => setDeleting(f)}>
                      <Trash2 />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>
      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent>{editing !== null ? <FieldForm key={editing === "new" ? "new" : editing.id} field={editing === "new" ? null : editing} onClose={() => setEditing(null)} /> : null}</DialogContent>
      </Dialog>
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t("crbs.fields.deleteTitle", { name: deleting?.name ?? "" })}
        description={t("crbs.fields.deleteBody")}
        confirmLabel={t("crbs.common.delete")}
        destructive
        busy={del.isPending}
        onConfirm={() => deleting && del.mutate(deleting, { onSuccess: () => setDeleting(null), onError: toastError })}
      />
    </div>
  );
}

function FieldForm({ field, onClose }: { field: CustomField | null; onClose: () => void }) {
  const { t } = useI18n();
  const [name, setName] = useState(field?.name ?? "");
  const [type, setType] = useState<CustomField["type"]>(field?.type ?? "TEXT");
  const [options, setOptions] = useState((field?.options ?? []).map((o) => o.value).join("\n"));
  const [error, setError] = useState<string | null>(null);
  const body = { name: name.trim(), type, options: options.split("\n").map((s) => s.trim()).filter(Boolean) };
  const save = useCrbsMutation(() => (field ? crbs.roomAdmin.updateField(field.id, body) : crbs.roomAdmin.createField(body)), [["crbs", "fields"], ["crbs", "room-fields"]]);
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined, { onSuccess: () => (toast.success(t("crbs.common.saved")), onClose()), onError: (err) => setError(bookingErrorMessage(crbsError(err), t)) });
      }}
    >
      <DialogHeader>
        <DialogTitle>{field ? field.name : t("crbs.fields.new")}</DialogTitle>
      </DialogHeader>
      <Field label={t("crbs.common.name")} htmlFor="fld-name">
        <Input id="fld-name" required maxLength={64} value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label={t("crbs.fields.type")} htmlFor="fld-type">
        <SelectField id="fld-type" value={type} onChange={(e) => setType(e.target.value as CustomField["type"])}>
          <option value="TEXT">{t("crbs.fields.text")}</option>
          <option value="CHECKBOX">{t("crbs.fields.checkbox")}</option>
          <option value="SELECT">{t("crbs.fields.select")}</option>
        </SelectField>
      </Field>
      {type === "SELECT" ? (
        <Field label={t("crbs.fields.options")} htmlFor="fld-opts" hint={t("crbs.fields.optionsHint")}>
          <Textarea id="fld-opts" rows={4} value={options} onChange={(e) => setOptions(e.target.value)} />
        </Field>
      ) : null}
      {error ? <Alert tone="error">{error}</Alert> : null}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose}>
          {t("crbs.common.cancel")}
        </Button>
        <Button type="submit" disabled={!name.trim() || (type === "SELECT" && !body.options.length) || save.isPending}>
          {t("crbs.common.save")}
        </Button>
      </DialogFooter>
    </form>
  );
}

/* ---------------------------------------------------------------------------------------- ACL */

function AclTab() {
  const { t } = useI18n();
  const { can } = usePermissions();
  const rooms = useAdminRooms(can("setup.rooms"));
  const groupsAdmin = useRoomGroups(can("setup.rooms"));
  const ctxGroups = useBookingContext();
  const roomsLite = useQuery({ queryKey: ["crbs", "booking-rooms"], queryFn: () => crbs.bookings.rooms(), enabled: !can("setup.rooms"), retry: false });
  const groups = { data: groupsAdmin.data ?? ctxGroups.data?.room_groups.filter((g) => g.id !== 0) };
  const [entity, setEntity] = useState("");
  const [entityType, entityIdStr] = entity.split(":");
  const filter = entity ? { entity_type: entityType, entity_id: Number(entityIdStr) } : {};
  const acl = useAcl(filter);
  const catalogue = usePermissionCatalogue();
  const toastError = useErrorToast();
  const keys = [["crbs", "acl"], ["crbs", "grid"]];
  const update = useCrbsMutation(({ id, perms }: { id: number; perms: string[] }) => crbs.roomAdmin.updateAcl(id, perms), keys);
  const remove = useCrbsMutation((id: number) => crbs.roomAdmin.deleteAcl(id), keys);
  const bookingPerms = useMemo(() => Object.values(catalogue.data?.bookings ?? {}).flat(), [catalogue.data]);
  const roomOptions = rooms.data?.map((r) => ({ id: r.id, name: r.display_name })) ?? roomsLite.data?.map((r) => ({ id: r.id, name: r.name })) ?? [];
  return (
    <div className="flex flex-col gap-4">
      <p className="type-callout text-label-2">{t("crbs.acl.lead")}</p>
      <div className="max-w-sm">
        <Field label={t("crbs.acl.entity")} htmlFor="acl-entity">
          <SelectField id="acl-entity" value={entity} onChange={(e) => setEntity(e.target.value)}>
            <option value="">{t("crbs.acl.allEntries")}</option>
            <optgroup label={t("crbs.rooms.tabGroups")}>
              {(groups.data ?? []).map((g) => (
                <option key={g.id} value={`room_group:${g.id}`}>
                  {g.name}
                </option>
              ))}
            </optgroup>
            <optgroup label={t("crbs.rooms.tabRooms")}>
              {roomOptions.map((r) => (
                <option key={r.id} value={`room:${r.id}`}>
                  {r.name}
                </option>
              ))}
            </optgroup>
          </SelectField>
        </Field>
      </div>
      <Card variant="glass" className="py-0">
        {acl.isLoading ? (
          <Loading className="px-4" />
        ) : (acl.data ?? []).length === 0 ? (
          <p className="px-4 py-5 type-callout text-label-2">{t("crbs.acl.none")}</p>
        ) : (
          <ul data-testid="acl-list">
            {(acl.data ?? []).map((a) => (
              <li key={a.id} className="flex flex-col gap-2 px-4 py-3 shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none">
                <div className="flex items-start justify-between gap-2">
                  <p className="type-headline text-label-1">
                    {a.entity_label} <span className="font-normal text-label-3">←</span> {t(`crbs.acl.ctx.${a.context_type}`)}: {a.context_label}
                  </p>
                  <Button variant="ghost" size="icon-sm" aria-label={t("crbs.acl.remove")} onClick={() => remove.mutate(a.id, { onError: toastError })}>
                    <Trash2 />
                  </Button>
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-1">
                  {bookingPerms.map((p) => (
                    <label key={p.name} className="flex items-center gap-1.5 type-footnote text-label-1">
                      <Checkbox
                        checked={a.permissions.includes(p.name)}
                        onCheckedChange={(v) => update.mutate({ id: a.id, perms: v === true ? [...a.permissions, p.name] : a.permissions.filter((x) => x !== p.name) }, { onError: toastError })}
                      />
                      {permLabel(t, p.name, p.description)}
                    </label>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
      {entity ? <AclAdd entityType={entityType as "room" | "room_group"} entityId={Number(entityIdStr)} /> : <p className="type-footnote text-label-3">{t("crbs.acl.pickToAdd")}</p>}
    </div>
  );
}

function AclAdd({ entityType, entityId }: { entityType: "room" | "room_group"; entityId: number }) {
  const { t } = useI18n();
  const { can } = usePermissions();
  const [ctx, setCtx] = useState<AclIn["context_type"]>("role");
  const [ctxId, setCtxId] = useState("");
  const [perms, setPerms] = useState<string[]>(["room.view", "book_single.create"]);
  const roles = useRoles(can("setup.roles"));
  const departments = useDepartments();
  const users = useUserSearch({ limit: 500, enabled: true, sort: "displayname" }, can("setup.users") && ctx === "user");
  const catalogue = usePermissionCatalogue();
  const toastError = useErrorToast();
  const add = useCrbsMutation(() => crbs.roomAdmin.createAcl({ entity_type: entityType, entity_id: entityId, context_type: ctx, context_id: Number(ctxId), permissions: perms }), [["crbs", "acl"], ["crbs", "grid"]]);
  const options = ctx === "role" ? (roles.data ?? []).map((r) => ({ id: r.id, name: r.name })) : ctx === "department" ? (departments.data ?? []).map((d) => ({ id: d.id, name: d.name })) : (users.data?.items ?? []).map((u) => ({ id: u.id, name: u.displayname || u.username || u.email || String(u.id) }));
  return (
    <section aria-labelledby="acl-add" className="flex flex-col gap-3">
      <h3 id="acl-add" className="type-title-3 text-label-1">
        {t("crbs.acl.add")}
      </h3>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("crbs.acl.context")} htmlFor="acl-ctx">
          <SelectField id="acl-ctx" value={ctx} onChange={(e) => (setCtx(e.target.value as AclIn["context_type"]), setCtxId(""))}>
            <option value="role">{t("crbs.acl.ctx.role")}</option>
            <option value="department">{t("crbs.acl.ctx.department")}</option>
            <option value="user">{t("crbs.acl.ctx.user")}</option>
          </SelectField>
        </Field>
        <Field label={t(`crbs.acl.ctx.${ctx}`)} htmlFor="acl-ctx-id">
          {options.length ? (
            <SelectField id="acl-ctx-id" value={ctxId} onChange={(e) => setCtxId(e.target.value)}>
              <option value="">{t("crbs.acl.pick")}</option>
              {options.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </SelectField>
          ) : (
            <Input id="acl-ctx-id" inputMode="numeric" placeholder={t("crbs.acl.idHint")} value={ctxId} onChange={(e) => setCtxId(e.target.value.replace(/\D/g, ""))} />
          )}
        </Field>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {Object.values(catalogue.data?.bookings ?? {})
          .flat()
          .map((p) => (
            <label key={p.name} className="flex items-center gap-1.5 type-footnote text-label-1">
              <Checkbox checked={perms.includes(p.name)} onCheckedChange={(v) => setPerms((prev) => (v === true ? [...prev, p.name] : prev.filter((x) => x !== p.name)))} />
              {permLabel(t, p.name, p.description)}
            </label>
          ))}
      </div>
      <div>
        <Button disabled={!ctxId || !perms.length || add.isPending} onClick={() => add.mutate(undefined, { onSuccess: () => (toast.success(t("crbs.common.saved")), setCtxId("")), onError: toastError })} data-testid="acl-add">
          <Plus aria-hidden />
          {t("crbs.acl.add")}
        </Button>
      </div>
    </section>
  );
}
