"use client";
/** /admin/departments (CRBS `Departments`): a department is a programme of the planning lists. */
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { crbs, crbsError, useCrbsMutation, useDepartments, type Department } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import { Alert, ConfirmDialog, Field, Loading, PageTitle } from "./kit";
import { useErrorToast } from "./admin-gate";

const fold = (s: string) => s.toLocaleLowerCase("tr-TR");

export function DepartmentsAdmin() {
  const { t } = useI18n();
  const list = useDepartments();
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<Department | "new" | null>(null);
  const [deleting, setDeleting] = useState<Department | null>(null);
  const toastError = useErrorToast();
  const del = useCrbsMutation((d: Department) => crbs.departments.remove(d.id), [["crbs", "departments"]]);
  const rows = useMemo(() => (list.data ?? []).filter((d) => !q || fold(d.name).includes(fold(q))), [list.data, q]);
  return (
    <div className="flex flex-col gap-5">
      <PageTitle
        title={t("crbs.admin.departments.title")}
        subtitle={t("crbs.departments.lead", { n: list.data?.length ?? 0 })}
        actions={
          <Button onClick={() => setEditing("new")}>
            <Plus aria-hidden />
            {t("crbs.departments.new")}
          </Button>
        }
      />
      <Input type="search" className="max-w-sm" aria-label={t("crbs.common.search")} placeholder={t("crbs.departments.search")} value={q} onChange={(e) => setQ(e.target.value)} />
      <Card variant="glass" className="py-0">
        {list.isLoading ? (
          <Loading className="px-4" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">{t("crbs.common.name")}</TableHead>
                <TableHead className="hidden md:table-cell">{t("crbs.common.description")}</TableHead>
                <TableHead className="text-right">{t("crbs.departments.users")}</TableHead>
                <TableHead className="w-24 pr-4">
                  <span className="sr-only">{t("crbs.common.actions")}</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((d) => (
                <TableRow key={d.id}>
                  <TableCell className="pl-4 font-medium text-label-1">{d.name}</TableCell>
                  <TableCell className="hidden text-label-2 md:table-cell">{d.description ?? ""}</TableCell>
                  <TableCell className="text-right tabular-nums text-label-2">{d.user_count}</TableCell>
                  <TableCell className="pr-4 text-right whitespace-nowrap">
                    <Button variant="ghost" size="icon-sm" aria-label={t("crbs.departments.editNamed", { name: d.name })} onClick={() => setEditing(d)}>
                      <Pencil />
                    </Button>
                    <Button variant="ghost" size="icon-sm" aria-label={t("crbs.departments.deleteNamed", { name: d.name })} onClick={() => setDeleting(d)}>
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
        <DialogContent>{editing !== null ? <DepartmentForm key={editing === "new" ? "new" : editing.id} dep={editing === "new" ? null : editing} onClose={() => setEditing(null)} /> : null}</DialogContent>
      </Dialog>
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t("crbs.departments.deleteTitle", { name: deleting?.name ?? "" })}
        description={t("crbs.departments.deleteBody")}
        confirmLabel={t("crbs.common.delete")}
        destructive
        busy={del.isPending}
        onConfirm={() => deleting && del.mutate(deleting, { onSuccess: () => setDeleting(null), onError: (e) => (toastError(e), setDeleting(null)) })}
      />
    </div>
  );
}

function DepartmentForm({ dep, onClose }: { dep: Department | null; onClose: () => void }) {
  const { t } = useI18n();
  const [name, setName] = useState(dep?.name ?? "");
  const [description, setDescription] = useState(dep?.description ?? "");
  const [error, setError] = useState<string | null>(null);
  const body = { name: name.trim(), description: description.trim() || null };
  const save = useCrbsMutation(() => (dep ? crbs.departments.update(dep.id, body) : crbs.departments.create(body)), [["crbs", "departments"]]);
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined, { onSuccess: () => (toast.success(t("crbs.common.saved")), onClose()), onError: (err) => setError(bookingErrorMessage(crbsError(err), t)) });
      }}
    >
      <DialogHeader>
        <DialogTitle>{dep ? dep.name : t("crbs.departments.new")}</DialogTitle>
      </DialogHeader>
      <Field label={t("crbs.common.name")} htmlFor="dep-name">
        <Input id="dep-name" required maxLength={255} value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label={t("crbs.common.description")} htmlFor="dep-desc">
        <Input id="dep-desc" maxLength={255} value={description} onChange={(e) => setDescription(e.target.value)} />
      </Field>
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
