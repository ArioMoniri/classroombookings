"use client";
/**
 * Department view of the reservation panel (departments = programmes). A department picker (the user's own
 * first and the default), a colour legend of the departments booking on this view (the user's first, with
 * counts; a legend entry selects that department), and the rooms the chosen department uses most
 * (`GET /bookings/departments/{id}/rooms`). The choice is remembered per user in localStorage.
 *
 * Colour is never the only cue (G4): every legend entry carries the name and count, and each booked cell's
 * accessible name says its department.
 */
import { useQuery } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import { useCallback, useMemo, useSyncExternalStore } from "react";
import { Chip } from "@/components/ui/chip";
import { crbs, useCrbsMe, useDepartments, type Grid } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { SelectField } from "@/components/admin/kit";
import { departmentColor, departmentTally, deptStorageKey, parseDepartmentLens, type DepartmentLens } from "./reserve-model";

const listeners = new Set<() => void>();

/** The remembered department lens of the signed-in user; the default is the user's own department. */
export function useDepartmentLens(): [DepartmentLens, (v: DepartmentLens) => void, number | null] {
  const me = useCrbsMe();
  const uid = me.data?.id;
  const mine = me.data?.department_id ?? null;
  const raw = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => void listeners.delete(cb);
    },
    () => {
      if (!uid) return null;
      try {
        return window.localStorage.getItem(deptStorageKey(uid));
      } catch {
        return null;
      }
    },
    () => null,
  );
  const value: DepartmentLens = parseDepartmentLens(raw) ?? mine ?? "all";
  const set = useCallback(
    (v: DepartmentLens) => {
      if (!uid) return;
      try {
        window.localStorage.setItem(deptStorageKey(uid), String(v));
      } catch {
        /* storage blocked: the choice lasts until reload */
      }
      for (const l of listeners) l();
    },
    [uid],
  );
  return [value, set, mine];
}

export function DepartmentBar({ grid, value, onChange, mine, termId, onRoomInfo }: { grid: Grid | undefined; value: DepartmentLens; onChange: (v: DepartmentLens) => void; mine: number | null; termId?: number; onRoomInfo: (roomId: number) => void }) {
  const { t, locale } = useI18n();
  const departments = useDepartments();
  const collator = useMemo(() => new Intl.Collator(locale), [locale]);
  const tally = useMemo(() => departmentTally(grid, mine, collator), [collator, grid, mine]);
  const chosen = value === "all" ? null : value;
  const top = useQuery({
    queryKey: ["crbs", "department-rooms", chosen, termId],
    queryFn: () => crbs.bookings.departmentRooms(chosen ?? 0, termId, 8),
    enabled: chosen !== null,
    retry: false,
    staleTime: 60_000,
  });
  const list = useMemo(() => departments.data ?? [], [departments.data]);
  const nameOf = (id: number) => list.find((d) => d.id === id)?.name ?? tally.find((d) => d.id === id)?.name ?? `#${id}`;
  const ordered = useMemo(() => [...list.filter((d) => d.id === mine), ...list.filter((d) => d.id !== mine)], [list, mine]);

  return (
    <section aria-label={t("reserve.dept.label")} className="flex flex-col gap-2" data-print-hide data-testid="department-bar">
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 type-footnote font-medium text-label-2">
          <Building2 className="size-4" aria-hidden />
          {t("reserve.dept.label")}
          <SelectField value={String(value)} onChange={(e) => onChange(e.target.value === "all" ? "all" : Number(e.target.value))} className="min-w-44" data-testid="department-select">
            <option value="all">{t("reserve.dept.all")}</option>
            {ordered.map((d) => (
              <option key={d.id} value={d.id}>
                {d.id === mine ? t("reserve.dept.mine", { name: d.name }) : d.name}
              </option>
            ))}
          </SelectField>
        </label>
        <ul className="-mx-1 flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto px-1 py-0.5 scrollbar-thin" aria-label={t("reserve.dept.legend")} data-testid="department-legend">
          {tally.length === 0 ? <li className="type-footnote text-label-3">{t("reserve.dept.legendEmpty")}</li> : null}
          {tally.map((d) => (
            <li key={d.id}>
              <Chip
                size="sm"
                selected={value === d.id}
                onSelectedChange={(on) => onChange(on ? d.id : "all")}
                icon={<span aria-hidden className="inline-block size-2.5 rounded-full" style={{ background: departmentColor(d.id) ?? undefined }} />}
                aria-label={`${value === d.id ? t("reserve.dept.clear") : t("reserve.dept.show", { name: d.name })} (${t("reserve.dept.count", { n: d.count })})`}
                data-department-id={d.id}
              >
                {d.id === mine ? t("reserve.dept.mine", { name: d.name }) : d.name}
                <span className="font-normal text-label-3 tabular-nums">{d.count}</span>
              </Chip>
            </li>
          ))}
        </ul>
      </div>
      {chosen !== null ? (
        // one fixed-height strip (scrolls sideways): the top rooms arrive after the grid and must not push it down
        <div className="-mx-1 flex h-12 items-center gap-2 overflow-x-auto px-1 type-footnote whitespace-nowrap text-label-2 scrollbar-thin sm:h-7" aria-live="polite">
          <span data-testid="department-filtering">{t("reserve.dept.filtering", { name: nameOf(chosen) })}</span>
          {top.data ? (
            top.data.rooms.length ? (
              <span className="flex items-center gap-1.5" data-testid="department-top-rooms">
                <span className="text-label-3">{t("reserve.dept.topRooms", { name: nameOf(chosen) })}:</span>
                {top.data.rooms.map((r) => (
                  <button
                    key={r.room_id}
                    type="button"
                    onClick={() => onRoomInfo(r.room_id)}
                    title={t("reserve.dept.roomUse", { bookings: r.bookings, classes: r.classes })}
                    aria-label={`${t("crbs.roomInfo.open", { name: r.name })} · ${t("reserve.dept.roomUse", { bookings: r.bookings, classes: r.classes })}`}
                    className="h-11 shrink-0 rounded-full bg-fill-2 px-2.5 font-medium text-label-1 outline-none hover:bg-fill-1 focus-visible:outline-2 focus-visible:outline-(--focus) sm:h-6"
                  >
                    {r.name}
                  </button>
                ))}
              </span>
            ) : (
              <span>{t("reserve.dept.noRooms", { name: nameOf(chosen) })}</span>
            )
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
