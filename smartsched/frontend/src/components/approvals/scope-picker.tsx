"use client";
/**
 * "Approves for" (P1 designation): every room, or some room groups, room types (solver tags such as TIP or
 * PC) and single rooms. Used in the user form (`approves_for`) and the approvers list
 * (`PUT /approvals/approvers/{id}`). Native controls, so it works with the keyboard and screen readers.
 */
import { X } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Switch } from "@/components/ui/switch";
import { SelectField } from "@/components/admin/kit";
import { useBookingContext, crbs } from "@/lib/api/crbs";
import type { Scope } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";
import { useQuery } from "@tanstack/react-query";
import { scopeKey, toggleScope } from "./approvals-model";

export function useScopeLookups(enabled = true) {
  const ctx = useBookingContext();
  const rooms = useQuery({ queryKey: ["crbs", "booking-rooms"], queryFn: () => crbs.bookings.rooms(), enabled, retry: false, staleTime: 60_000 });
  return useMemo(() => {
    const groups = (ctx.data?.room_groups ?? []).filter((g) => g.id !== 0).map((g) => ({ id: g.id, name: g.name }));
    const roomList = (rooms.data ?? []).map((r) => ({ id: r.id, name: r.name, tags: r.tags, groupId: r.room_group_id ?? null }));
    const tags = [...new Set(roomList.flatMap((r) => r.tags))].sort((a, b) => a.localeCompare(b, "tr"));
    const sessions = (ctx.data?.sessions ?? []).map((s) => ({ id: s.id, name: s.name }));
    const roomName = new Map(roomList.map((r) => [r.id, r.name]));
    const groupName = new Map(groups.map((g) => [g.id, g.name]));
    const termName = new Map(sessions.map((s) => [s.id, s.name]));
    return {
      groups,
      rooms: roomList,
      tags,
      sessions,
      room: (id: number) => roomName.get(id),
      group: (id: number) => groupName.get(id),
      term: (id: number) => termName.get(id),
      loading: ctx.isLoading || rooms.isLoading,
    };
  }, [ctx.data, ctx.isLoading, rooms.data, rooms.isLoading]);
}

export type ScopeLookups = ReturnType<typeof useScopeLookups>;

export function scopeLabel(s: Pick<Scope, "type" | "id" | "tag">, l: Pick<ScopeLookups, "room" | "group">, t: ReturnType<typeof useI18n>["t"]): string {
  if (s.type === "all") return t("wave1.scope.all");
  if (s.type === "tag") return t("wave1.scope.tagN", { tag: s.tag ?? "" });
  if (s.type === "room_group") return t("wave1.scope.groupN", { name: (s.id != null && l.group(s.id)) || `#${s.id ?? ""}` });
  return (s.id != null && l.room(s.id)) || `#${s.id ?? ""}`;
}

export function ScopePicker({ value, onChange, lookups, idPrefix }: { value: Scope[]; onChange: (v: Scope[]) => void; lookups: ScopeLookups; idPrefix: string }) {
  const { t } = useI18n();
  const all = value.some((s) => s.type === "all");
  const [room, setRoom] = useState("");
  const picked = new Set(value.map(scopeKey));
  return (
    <div className="flex flex-col gap-3" data-testid={`${idPrefix}-scopes`}>
      <label className="flex items-center justify-between gap-3 type-callout text-label-1">
        <span>
          {t("wave1.scope.all")}
          <span className="block type-footnote text-label-3">{t("wave1.scope.allHint")}</span>
        </span>
        <Switch checked={all} onCheckedChange={(on) => onChange(on ? [{ type: "all" }] : [])} aria-label={t("wave1.scope.all")} data-testid={`${idPrefix}-scope-all`} />
      </label>
      {!all ? (
        <>
          {lookups.groups.length ? (
            <div className="flex flex-col gap-1.5" role="group" aria-label={t("wave1.scope.groups")}>
              <span className="type-footnote font-medium text-label-2">{t("wave1.scope.groups")}</span>
              <div className="flex flex-wrap gap-1.5">
                {lookups.groups.map((g) => {
                  const s: Scope = { type: "room_group", id: g.id };
                  return (
                    <Chip key={g.id} size="sm" selected={picked.has(scopeKey(s))} onSelectedChange={(on) => onChange(toggleScope(value, s, on))}>
                      {g.name}
                    </Chip>
                  );
                })}
              </div>
            </div>
          ) : null}
          {lookups.tags.length ? (
            <div className="flex flex-col gap-1.5" role="group" aria-label={t("wave1.scope.tags")}>
              <span className="type-footnote font-medium text-label-2">{t("wave1.scope.tags")}</span>
              <div className="flex flex-wrap gap-1.5">
                {lookups.tags.map((tag) => {
                  const s: Scope = { type: "tag", tag };
                  return (
                    <Chip key={tag} size="sm" selected={picked.has(scopeKey(s))} onSelectedChange={(on) => onChange(toggleScope(value, s, on))} data-testid={`${idPrefix}-tag-${tag}`}>
                      {tag}
                    </Chip>
                  );
                })}
              </div>
            </div>
          ) : null}
          <div className="flex flex-col gap-1.5">
            <label htmlFor={`${idPrefix}-room`} className="type-footnote font-medium text-label-2">
              {t("wave1.scope.rooms")}
            </label>
            <div className="flex gap-2">
              <SelectField id={`${idPrefix}-room`} value={room} onChange={(e) => setRoom(e.target.value)} className="min-w-0 flex-1">
                <option value="">{t("wave1.scope.pickRoom")}</option>
                {lookups.rooms
                  .filter((r) => !picked.has(scopeKey({ type: "room", id: r.id })))
                  .map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
              </SelectField>
              <Button
                type="button"
                variant="outline"
                disabled={!room}
                onClick={() => {
                  onChange(toggleScope(value, { type: "room", id: Number(room) }, true));
                  setRoom("");
                }}
              >
                {t("wave1.scope.add")}
              </Button>
            </div>
            {value.some((s) => s.type === "room") ? (
              <ul className="flex flex-wrap gap-1.5">
                {value
                  .filter((s) => s.type === "room")
                  .map((s) => (
                    <li key={scopeKey(s)}>
                      <span className="inline-flex h-7 items-center gap-1 rounded-full bg-fill-2 pr-1 pl-2.5 type-footnote text-label-1">
                        {scopeLabel(s, lookups, t)}
                        <button type="button" onClick={() => onChange(toggleScope(value, s, false))} className="flex size-5 items-center justify-center rounded-full outline-hidden hover:bg-fill-1 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)" aria-label={t("wave1.scope.remove", { name: scopeLabel(s, lookups, t) })}>
                          <X className="size-3" aria-hidden />
                        </button>
                      </span>
                    </li>
                  ))}
              </ul>
            ) : null}
          </div>
        </>
      ) : null}
    </div>
  );
}
