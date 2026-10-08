"use client";
/**
 * /admin/access (CRBS `setup/Access_checker`): one user in one room, each booking permission and its source.
 * `?user=<id>&room=<id>` preselect either side (CRBS `access_checker/user/<id>` and `/room/<id>`), so the user
 * and room admin rows can open it (UI gap audit #15); the URL follows the pickers, so a result can be shared.
 */
import { useQuery } from "@tanstack/react-query";
import { Check, Minus } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { crbs, crbsError, useUserSearch } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import { usePermissions } from "@/lib/permissions";
import { Alert, Field, Loading, PageTitle, SelectField } from "./kit";
import { permLabel } from "./roles-admin";

export function AccessChecker() {
  const { t } = useI18n();
  const { can } = usePermissions();
  const [q, setQ] = useState("");
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [userId, setUserIdState] = useState(() => (params.get("user") ?? "").replace(/\D/g, ""));
  const [roomId, setRoomIdState] = useState(() => (params.get("room") ?? "").replace(/\D/g, ""));
  const sync = (user: string, room: string) => {
    const next = new URLSearchParams();
    if (user) next.set("user", user);
    if (room) next.set("room", room);
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };
  const setUserId = (v: string) => (setUserIdState(v), sync(v, roomId));
  const setRoomId = (v: string) => (setRoomIdState(v), sync(userId, v));
  const users = useUserSearch({ q: q || undefined, limit: 50, sort: "username" }, can("setup.users"));
  // a deep-linked user may not be in the first 50 search results: load it so the picker can show it
  const picked = useQuery({ queryKey: ["crbs", "user", userId], queryFn: () => crbs.users.get(Number(userId)), enabled: !!userId && can("setup.users"), retry: false });
  const userOptions = [...(users.data?.items ?? [])];
  if (picked.data && !userOptions.some((u) => u.id === picked.data.id)) userOptions.unshift(picked.data);
  const rooms = useQuery({ queryKey: ["crbs", "admin-rooms"], queryFn: () => crbs.roomAdmin.rooms(), enabled: can("setup.rooms"), retry: false });
  const roomsLite = useQuery({ queryKey: ["crbs", "booking-rooms"], queryFn: () => crbs.bookings.rooms(), enabled: !can("setup.rooms"), retry: false });
  const roomList = rooms.data?.map((r) => ({ id: r.id, name: r.display_name })) ?? roomsLite.data?.map((r) => ({ id: r.id, name: r.name })) ?? [];
  const check = useQuery({
    queryKey: ["crbs", "access-check", userId, roomId],
    queryFn: () => crbs.bookingAdmin.accessCheck(Number(userId), Number(roomId)),
    enabled: !!userId && !!roomId,
    retry: false,
  });
  return (
    <div className="flex flex-col gap-5">
      <PageTitle title={t("crbs.admin.access.title")} subtitle={t("crbs.admin.access.lead")} />
      <div className="grid gap-3 sm:grid-cols-3">
        {can("setup.users") ? (
          <Field label={t("crbs.access.find")} htmlFor="ac-q">
            <Input id="ac-q" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("crbs.users.searchHint")} />
          </Field>
        ) : null}
        <Field label={t("crbs.access.user")} htmlFor="ac-user">
          {can("setup.users") ? (
            <SelectField id="ac-user" data-testid="access-user" value={userId} onChange={(e) => setUserId(e.target.value)}>
              <option value="">{t("crbs.acl.pick")}</option>
              {userOptions.map((u) => (
                <option key={u.id} value={u.id}>
                  {(u.displayname || u.username || u.email) + (u.role_name ? ` · ${u.role_name}` : "")}
                </option>
              ))}
            </SelectField>
          ) : (
            <Input id="ac-user" inputMode="numeric" placeholder={t("crbs.acl.idHint")} value={userId} onChange={(e) => setUserId(e.target.value.replace(/\D/g, ""))} />
          )}
        </Field>
        <Field label={t("crbs.toolbar.room")} htmlFor="ac-room">
          <SelectField id="ac-room" data-testid="access-room" value={roomId} onChange={(e) => setRoomId(e.target.value)}>
            <option value="">{t("crbs.acl.pick")}</option>
            {roomList.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </SelectField>
        </Field>
      </div>
      {check.isLoading && userId && roomId ? <Loading /> : null}
      {check.isError ? <Alert tone="error">{bookingErrorMessage(crbsError(check.error), t)}</Alert> : null}
      {check.data ? (
        <Card variant="glass" className="gap-3 px-4" data-testid="access-result">
          <p className="type-callout text-label-2">
            {t("crbs.access.role", { role: check.data.role ?? t("crbs.users.noRole") })}
            {!check.data.room_bookable ? ` · ${t("crbs.rooms.notBookable")}` : ""}
          </p>
          {Object.entries(check.data.effective).map(([group, perms]) => (
            <section key={group}>
              <h3 className="mb-1 type-headline text-label-1">{t(`crbs.perm.group.${group}` as MessageKey)}</h3>
              <ul className="flex flex-col">
                {Object.entries(perms).map(([name, on]) => {
                  const src = check.data.from_role.includes(name) ? "role" : check.data.from_acl.includes(name) ? "acl" : null;
                  return (
                    <li key={name} className="flex items-center gap-2 py-1 type-callout shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none">
                      {on ? <Check className="size-4 text-status-feasible-fg" aria-hidden /> : <Minus className="size-4 text-label-3" aria-hidden />}
                      <span className={on ? "flex-1 text-label-1" : "flex-1 text-label-3"}>{permLabel(t, name)}</span>
                      <span className="type-footnote text-label-2">{on ? (src === "role" ? t("crbs.access.fromRole") : t("crbs.access.fromAcl")) : t("crbs.access.no")}</span>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </Card>
      ) : null}
    </div>
  );
}
