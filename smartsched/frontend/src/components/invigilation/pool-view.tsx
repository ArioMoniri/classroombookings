"use client";
/**
 * The invigilator pool of the exam run's term (rows of this term plus the rows for every term): staff, research
 * assistants and instructors with their own rules. The exam instructors are in every plan's pool by default
 * (`instructor_pool`); a row here adds a person, or carries an instructor's rules (unavailability, caps, load
 * factor). Add / edit in a dialog (bottom sheet on phones), delete with a confirm.
 */
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { ResponsiveDialog } from "@/components/moderation/responsive-dialog";
import { Alert } from "@/components/ui/alert";
import { BusyButton } from "@/components/ui/busy-label";
import { Button, IconButton } from "@/components/ui/button";
import { DataTable, StatusDot, type DataColumn } from "@/components/ui/data-table";
import { Skeleton } from "@/components/ui/skeleton";
import { errorText } from "@/lib/api/analytics";
import { useMe } from "@/lib/api/hooks";
import { useDeleteMember, usePool, type PoolMember, type Unavailable } from "@/lib/api/invigilation";
import { useI18n } from "@/lib/i18n/provider";
import { dayName, formatDate, PERIODS } from "@/lib/time";
import { PoolMemberDialog } from "./pool-form";

export function useUnavailText() {
  const { t, locale } = useI18n();
  return (u: Unavailable) => {
    const when = u.date ? formatDate(u.date, locale, { day: "2-digit", month: "2-digit", year: "numeric" }) : t("invigilation.pool.everyN", { day: dayName(u.day ?? 1, locale) });
    const span = u.start_period ? `${PERIODS[u.start_period - 1]?.start ?? u.start_period}–${PERIODS[(u.end_period ?? u.start_period) - 1]?.end ?? u.end_period}` : t("invigilation.pool.wholeDay");
    return `${when} ${span}${u.note ? ` (${u.note})` : ""}`;
  };
}

export function PoolView({ termId, canEdit }: { termId: number | null; canEdit: boolean }) {
  const { t, n, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const me = useMe();
  const pool = usePool(termId);
  const del = useDeleteMember();
  const unavail = useUnavailText();
  const [editing, setEditing] = useState<PoolMember | "new" | null>(null);
  const [deleting, setDeleting] = useState<PoolMember | null>(null);
  const [delError, setDelError] = useState<string | null>(null);

  const columns = useMemo<DataColumn<PoolMember>[]>(
    () => [
      { id: "name", header: t("invigilation.pool.name"), pin: "left", priority: 1, grow: 2, minSize: 150, text: (m) => m.full_name, sortValue: (m) => m.full_name, cell: (m) => <span className="truncate font-medium">{m.full_name}</span> },
      { id: "kind", header: t("invigilation.pool.kind"), priority: 2, text: (m) => t(`invigilation.kind.${m.kind}`), sortValue: (m) => m.kind, cell: (m) => t(`invigilation.kind.${m.kind}`) },
      { id: "active", header: t("common.status"), priority: 2, text: (m) => t(m.active ? "invigilation.pool.isActive" : "invigilation.pool.isInactive"), extra: 16, sortValue: (m) => (m.active ? 1 : 0), cell: (m) => <StatusDot tone={m.active ? "feasible" : "neutral"}>{t(m.active ? "invigilation.pool.isActive" : "invigilation.pool.isInactive")}</StatusDot> },
      { id: "scope", header: t("invigilation.pool.scope"), priority: 4, text: (m) => t(m.term_id === null ? "invigilation.pool.allTerms" : "invigilation.pool.thisTerm"), cell: (m) => t(m.term_id === null ? "invigilation.pool.allTerms" : "invigilation.pool.thisTerm") },
      { id: "caps", header: t("invigilation.pool.caps"), priority: 3, text: (m) => `${m.max_duties ?? "—"} / ${m.max_per_day ?? "—"}`, cell: (m) => <span className="tnum">{`${m.max_duties ?? "—"} / ${m.max_per_day ?? "—"}`}</span> },
      { id: "factor", header: t("invigilation.pool.loadFactor"), align: "end", priority: 3, text: (m) => `%${m.load_factor}`, sortValue: (m) => m.load_factor, cell: (m) => <span className="tnum">{lang === "tr" ? `%${m.load_factor}` : `${m.load_factor}%`}</span> },
      {
        id: "unavailable",
        header: t("invigilation.pool.unavailable"),
        priority: 2,
        grow: 2,
        minSize: 140,
        maxSize: 420,
        text: (m) => m.unavailable.map(unavail).join("; ") || "—",
        sortValue: (m) => m.unavailable.length,
        cell: (m) => <span className="truncate" title={m.unavailable.map(unavail).join("\n")}>{m.unavailable.length ? `${n(m.unavailable.length)} · ${unavail(m.unavailable[0]!)}${m.unavailable.length > 1 ? " …" : ""}` : "—"}</span>,
      },
      ...(canEdit
        ? [
            {
              id: "act",
              header: t("common.actions"),
              hideable: false,
              priority: 1 as const,
              size: 76,
              cell: (m: PoolMember) => (
                <span className="flex gap-1">
                  <IconButton size="xs" label={t("invigilation.pool.edit", { name: m.full_name })} onClick={(e) => (e.stopPropagation(), setEditing(m))} data-testid="pool-edit">
                    <Pencil aria-hidden />
                  </IconButton>
                  <IconButton size="xs" label={t("invigilation.pool.delete", { name: m.full_name })} onClick={(e) => (e.stopPropagation(), setDelError(null), setDeleting(m))} data-testid="pool-delete">
                    <Trash2 aria-hidden />
                  </IconButton>
                </span>
              ),
            },
          ]
        : []),
    ],
    [t, n, lang, canEdit, unavail],
  );

  const confirmDelete = async () => {
    if (!deleting) return;
    try {
      await del.mutateAsync(deleting.id);
      toast.success(t("invigilation.pool.deleted", { name: deleting.full_name }));
      setDeleting(null);
    } catch (e) {
      setDelError(errorText(e, lang));
    }
  };

  return (
    <section className="flex flex-col gap-3" aria-labelledby="pool-title" data-testid="invig-pool">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="min-w-0">
          <h2 id="pool-title" className="type-title-3">{t("invigilation.pool.title")}</h2>
          <p className="type-footnote text-label-2">{t("invigilation.pool.lead")}</p>
        </div>
        {canEdit ? (
          <Button onClick={() => setEditing("new")} data-testid="pool-add">
            <Plus aria-hidden />
            {t("invigilation.pool.add")}
          </Button>
        ) : null}
      </div>
      {pool.isError ? (
        <Alert tone="error">{errorText(pool.error, lang)}</Alert>
      ) : pool.isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : (
        <DataTable
          tableId="invig-pool"
          userId={me.data?.id}
          label={t("invigilation.pool.title")}
          columns={columns}
          rows={pool.data}
          getRowId={(m) => String(m.id)}
          onRowActivate={canEdit ? (m) => setEditing(m) : undefined}
          rowProps={() => ({ "data-testid": "pool-row" })}
          defaultSort={[{ id: "name", desc: false }]}
          empty={<p className="px-3 py-6 type-callout text-label-2">{t("invigilation.pool.empty")}</p>}
        />
      )}
      <PoolMemberDialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)} termId={termId} member={editing === "new" ? null : editing} />
      <ResponsiveDialog
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        alert
        title={deleting ? t("invigilation.pool.deleteTitle", { name: deleting.full_name }) : ""}
        description={t("invigilation.pool.deleteBody")}
        testId="pool-delete-dialog"
        footer={
          <>
            <Button variant="ghost" className="max-md:h-11" onClick={() => setDeleting(null)}>{t("common.cancel")}</Button>
            <BusyButton busy={del.isPending} busyLabel={t("busy.deleting")} variant="destructive" className="max-md:h-11" onClick={() => void confirmDelete()} data-testid="pool-delete-ok">{t("common.delete")}</BusyButton>
          </>
        }
      >
        {delError ? <Alert tone="error">{delError}</Alert> : null}
      </ResponsiveDialog>
    </section>
  );
}
