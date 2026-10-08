"use client";

import { AlertTriangle, Loader2, TableProperties } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { NativeSelect } from "@/components/common/native-select";
import { Button } from "@/components/ui/button";
import type { MappingColumns, MappingProposals, MappingRole, MappingSpec, RoomRule } from "@/lib/api/studio-schemas";
import { MAPPING_ROLES } from "@/lib/api/studio-schemas";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { Segmented } from "./segmented";

const ROLE_KEY: Record<MappingRole, MessageKey> = {
  course: "studio.mapping.role.course",
  section: "studio.mapping.role.section",
  program: "studio.mapping.role.program",
  year: "studio.mapping.role.year",
  enrolment: "studio.mapping.role.enrolment",
  day: "studio.mapping.role.day",
  time: "studio.mapping.role.time",
  room: "studio.mapping.role.room",
  building: "studio.mapping.role.building",
  mode: "studio.mapping.role.mode",
  note: "studio.mapping.role.note",
};

/** column index → role, from the backend's `suggested_mapping.columns` (role → index) */
export function invertMapping(columns: Partial<Record<string, number>>): Record<number, MappingRole> {
  const out: Record<number, MappingRole> = {};
  for (const [role, idx] of Object.entries(columns)) if (typeof idx === "number" && (MAPPING_ROLES as readonly string[]).includes(role)) out[idx] = role as MappingRole;
  return out;
}

export function toSpec(byColumn: Record<number, MappingRole | "">, roomRule: RoomRule, hardness: "hard" | "soft", weight: number, headerRow?: number | null, sheet?: string | null): MappingSpec {
  const columns: Partial<Record<MappingRole, number>> = {};
  for (const [idx, role] of Object.entries(byColumn)) if (role) columns[role] = Number(idx);
  return { columns, room_rule: roomRule, hardness, weight, header_row: headerRow ?? null, sheet: sheet ?? null };
}

/**
 * No-AI fallback for Excel/CSV preference sheets (open question 5): the planner tells SmartSched which
 * column is which, then `POST /terms/{id}/studio/preferences/mapping` turns rows into rule cards.
 */
export function MappingStep({
  filename,
  load,
  submit,
  onDone,
  onCancel,
}: {
  filename: string;
  load: () => Promise<MappingColumns>;
  submit: (spec: MappingSpec) => Promise<MappingProposals>;
  onDone: (res: MappingProposals) => void;
  onCancel: () => void;
}) {
  const { t, locale } = useI18n();
  const [cols, setCols] = useState<MappingColumns | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [byColumn, setByColumn] = useState<Record<number, MappingRole | "">>({});
  const [roomRule, setRoomRule] = useState<RoomRule>("prefer");
  const [hardness, setHardness] = useState<"hard" | "soft">("soft");
  const [busy, setBusy] = useState(false);
  // read the columns once per file (callers pass inline functions)
  const loadOnce = useRef(load);

  useEffect(() => {
    let alive = true;
    loadOnce.current()
      .then((c) => {
        if (!alive) return;
        setCols(c);
        setByColumn(invertMapping(c.suggested_mapping.columns));
        setRoomRule(c.suggested_mapping.room_rule);
        setHardness(c.suggested_mapping.hardness);
      })
      .catch((e: unknown) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, []);

  const used = useMemo(() => new Set(Object.values(byColumn).filter(Boolean)), [byColumn]);
  const canRead = used.has("course") || used.has("program");

  const read = async () => {
    if (!cols) return;
    setBusy(true);
    setError(null);
    try {
      onDone(await submit(toSpec(byColumn, roomRule, hardness, cols.suggested_mapping.weight, cols.header_row, cols.sheet)));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-labelledby="mapping-title" className="space-y-3 rounded-lg border bg-card p-3" data-testid="mapping-step">
      <div className="flex items-start gap-2">
        <TableProperties className="mt-0.5 size-4 text-primary" aria-hidden />
        <div>
          <h4 id="mapping-title" className="text-sm font-semibold">
            {t("studio.mapping.title", { file: filename })}
          </h4>
          <p className="text-xs text-muted-foreground">{t("studio.mapping.help")}</p>
        </div>
      </div>
      {!cols && !error ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <Loader2 className="size-4 animate-spin" aria-hidden /> {t("studio.mapping.loading")}
        </p>
      ) : null}
      {cols ? (
        <>
          <p className="text-xs text-muted-foreground">{t("studio.mapping.found", { n: cols.row_count, sheet: cols.sheet ?? "—" })}</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground">
                  <th className="py-1 pr-2 font-medium">{t("studio.mapping.column")}</th>
                  <th className="py-1 pr-2 font-medium">{t("studio.mapping.samples")}</th>
                  <th className="py-1 font-medium">{t("studio.mapping.means")}</th>
                </tr>
              </thead>
              <tbody>
                {cols.columns.map((c) => (
                  <tr key={c.index} className="border-t align-top" data-testid="mapping-row">
                    <td className="py-1.5 pr-2 font-medium">{c.header || `#${c.index + 1}`}</td>
                    <td className="max-w-48 py-1.5 pr-2 text-xs text-muted-foreground">
                      <span className="line-clamp-2" lang="tr">
                        {c.samples.join(" · ") || "—"}
                      </span>
                    </td>
                    <td className="py-1.5">
                      <NativeSelect
                        aria-label={t("studio.mapping.meansFor", { col: c.header || `#${c.index + 1}` })}
                        value={byColumn[c.index] ?? ""}
                        onChange={(e) => {
                          const role = e.target.value as MappingRole | "";
                          setByColumn((m) => {
                            const next = { ...m };
                            // one column per role
                            if (role) for (const [k, v] of Object.entries(next)) if (v === role) next[Number(k)] = "";
                            next[c.index] = role;
                            return next;
                          });
                        }}
                        data-testid={`mapping-role-${c.index}`}
                      >
                        <option value="">{t("studio.mapping.ignore")}</option>
                        {MAPPING_ROLES.map((r) => (
                          <option key={r} value={r}>
                            {cols.roles[r]?.[locale] ?? t(ROLE_KEY[r])}
                          </option>
                        ))}
                      </NativeSelect>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {used.has("room") ? (
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="grid gap-1">
                <span id="map-room-rule" className="text-xs font-medium">
                  {t("studio.mapping.roomRule")}
                </span>
                <Segmented
                  size="sm"
                  labelledBy="map-room-rule"
                  value={roomRule}
                  onChange={(v) => {
                    setRoomRule(v);
                    setHardness(v === "prefer" ? "soft" : "hard");
                  }}
                  options={[
                    { value: "prefer", label: t("studio.mapping.prefer") },
                    { value: "pin", label: t("studio.mapping.pin") },
                    { value: "forbid", label: t("studio.mapping.forbid") },
                  ]}
                />
              </div>
              <div className="grid gap-1">
                <span id="map-hard" className="text-xs font-medium">
                  {t("studio.rule.mustOrTry")}
                </span>
                <Segmented
                  size="sm"
                  labelledBy="map-hard"
                  value={hardness}
                  onChange={setHardness}
                  options={[
                    { value: "hard", label: t("studio.rule.must") },
                    { value: "soft", label: t("studio.rule.try") },
                  ]}
                />
              </div>
            </div>
          ) : null}
          {!canRead ? <p className="text-xs text-status-warning-fg">{t("studio.mapping.needCourse")}</p> : null}
        </>
      ) : null}
      {error ? (
        <p role="alert" className="flex items-center gap-1.5 text-xs text-status-infeasible-fg">
          <AlertTriangle className="size-3.5" aria-hidden /> {error}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={() => void read()} disabled={!cols || !canRead || busy} data-testid="mapping-read">
          {busy ? <Loader2 className="animate-spin" aria-hidden /> : null} {t("studio.mapping.read")}
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
      </div>
    </section>
  );
}
