"use client";
/**
 * Yönetim › KVKK › Veri envanteri (`GET /admin/kvkk/inventory`, setup.settings): what SmartSched keeps, in which tables,
 * how many rows, on which legal basis and for how long — the starting point of the VERBİS record. CSV for the officer.
 * A table on wide screens, one card per data class on phones (MOBILE.md M-01).
 */
import { Download } from "lucide-react";
import { Alert, Loading } from "@/components/admin/kit";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { inventoryCsv, useInventory, type InventoryClass } from "@/lib/api/kvkk";
import { errorText, wave1Error } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";
import { useDateTime } from "@/components/privacy/privacy-section";

function rowsOf(c: InventoryClass): number {
  return Object.values(c.rows).reduce((a, b) => a + b, 0);
}

export function InventoryTable() {
  const { t, locale, n } = useI18n();
  const q = useInventory();
  const when = useDateTime();
  const inv = q.data;
  const kept = (c: InventoryClass) => {
    const r = c.retention;
    if (r) return r.enabled ? (r.legal_hold ? t("kvkk.inventory.held") : t("kvkk.inventory.days", { n: r.retain_days, action: t(r.action === "anonymise" ? "kvkk.retention.anonymise" : "kvkk.retention.delete") })) : t("kvkk.inventory.retentionOff");
    return c.kept ?? "–";
  };
  const download = () => {
    if (!inv) return;
    const blob = new Blob([inventoryCsv(inv, locale)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `smartsched-kvkk-envanter-${(inv.generated_at ?? "").slice(0, 10) || "export"}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return (
    <div className="flex flex-col gap-4" data-testid="kvkk-inventory">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-2xl type-callout text-label-2">{t("kvkk.inventory.lead")}</p>
        <Button size="sm" variant="outline" onClick={download} disabled={!inv} data-testid="inventory-csv">
          <Download aria-hidden />
          {t("kvkk.inventory.csv")}
        </Button>
      </div>
      {q.isLoading ? <Loading /> : null}
      {q.isError ? <Alert tone="error">{errorText(wave1Error(q.error), locale)}</Alert> : null}
      {inv ? (
        <>
          <div className="hidden overflow-x-auto rounded-xl bg-(--mat-thick-solid) edge-hairline md:block">
            <table className="w-full type-callout">
              <thead className="text-left type-footnote text-label-2">
                <tr className="edge-hairline-b">
                  <th scope="col" className="px-3 py-2 font-medium">{t("kvkk.inventory.data")}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t("kvkk.inventory.tables")}</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">{t("kvkk.inventory.rows")}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t("kvkk.inventory.basis")}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t("kvkk.inventory.kept")}</th>
                </tr>
              </thead>
              <tbody>
                {inv.classes.map((c) => (
                  <tr key={c.code} className="align-top not-last:edge-hairline-b" data-testid={`inventory-${c.code}`}>
                    <td className="px-3 py-2 text-label-1">{locale === "tr" ? c.label_tr : c.label_en}</td>
                    <td className="px-3 py-2 font-mono type-footnote text-label-2">{c.tables.join(", ") || "–"}</td>
                    <td className="px-3 py-2 text-right text-label-1">{c.tables.length ? n(rowsOf(c)) : "–"}</td>
                    <td className="px-3 py-2 text-label-2">{c.legal_basis}</td>
                    <td className="px-3 py-2 text-label-2">{kept(c)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="flex flex-col gap-2 md:hidden">
            {inv.classes.map((c) => (
              <li key={c.code}>
                <Card className="gap-1 px-4 py-3" data-testid={`inventory-card-${c.code}`}>
                  <p className="type-callout font-medium text-label-1">{locale === "tr" ? c.label_tr : c.label_en}</p>
                  <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 type-footnote">
                    <dt className="text-label-3">{t("kvkk.inventory.rows")}</dt>
                    <dd className="text-label-1" data-numeric>{c.tables.length ? n(rowsOf(c)) : "–"}</dd>
                    <dt className="text-label-3">{t("kvkk.inventory.basis")}</dt>
                    <dd className="text-label-2">{c.legal_basis}</dd>
                    <dt className="text-label-3">{t("kvkk.inventory.kept")}</dt>
                    <dd className="text-label-2">{kept(c)}</dd>
                    <dt className="text-label-3">{t("kvkk.inventory.tables")}</dt>
                    <dd className="font-mono break-all text-label-2">{c.tables.join(", ") || "–"}</dd>
                  </dl>
                </Card>
              </li>
            ))}
          </ul>
          {inv.generated_at ? <p className="type-footnote text-label-3">{t("kvkk.inventory.generated", { date: when(inv.generated_at.replace(/Z$/, ""), true) })}</p> : null}
        </>
      ) : null}
    </div>
  );
}
