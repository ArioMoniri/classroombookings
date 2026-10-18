"use client";
/**
 * HX-15 (helper.md §2.3 group 1, §17.1 #6; API.md HB-D §3): **Son işlemler** — the person's own confirmed helper
 * actions (`GET /helper/actions/recent?limit=5`, newest first). Shown in the empty sheet (all 5) and first in the
 * empty palette (at most 3, before the starters). Each row: the server's label (worded TR / EN from database values
 * only), when ("5 dakika önce"), the status ("Yapıldı" / "Geri alındı"), and "Geri al" while the server says
 * `undoable`. "Geri al" posts the row's `undo_token` to `POST /helper/actions/undo`, which re-checks everything; a
 * refusal (409 `too_old` / `conflict` / `already_undone`) shows the server's own text under the row. Only a trusted
 * click or key undoes (as on a result card). Hidden while the list is empty. After an undo the list is refetched and,
 * for a note, Profil › Yardımcı too ({@link invalidateAfterHelperWrite}).
 */
import { History, RotateCcw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId, useRef, useState } from "react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { CommandGroup, CommandItem } from "@/components/ui/command";
import { helperApi, helperRefusal, invalidateAfterHelperWrite, RECENT_LIMIT, useHelperRecent, type RecentAction } from "@/lib/api/helper";
import { usePermissions } from "@/lib/api/shell-extra";
import { intlLocale, translate, type Locale } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { useUiStore } from "@/stores/ui";
import { pickText } from "./cards/context";
import { canOpenFeature, featureById, featureHref } from "./feature-links";
import { useHelperStore } from "./helper-store";
import { activation } from "./use-helper-runner";

/** At most 3 rows in the palette (helper.md §2.3); the sheet shows all {@link RECENT_LIMIT}. */
export const PALETTE_RECENT = 3;

/** "az önce" / "5 dakika önce" / "dün" / "12 Şubat". The server's times are naive UTC. */
export function whenLabel(at: string, locale: Locale, now: number = Date.now()): string {
  const iso = /(?:[zZ]|[+-]\d\d:?\d\d)$/.test(at) ? at : `${at}Z`;
  const time = Date.parse(iso);
  if (!Number.isFinite(time)) return "";
  const sec = Math.round((time - now) / 1000);
  if (Math.abs(sec) < 45) return translate(locale, "helper.recent.now");
  const rtf = new Intl.RelativeTimeFormat(intlLocale(locale), { numeric: "auto" });
  const min = Math.round(sec / 60);
  if (Math.abs(min) < 60) return rtf.format(min, "minute");
  const hr = Math.round(min / 60);
  if (Math.abs(hr) < 24) return rtf.format(hr, "hour");
  const day = Math.round(hr / 24);
  if (Math.abs(day) < 7) return rtf.format(day, "day");
  return new Intl.DateTimeFormat(intlLocale(locale), { day: "numeric", month: "long" }).format(time);
}

/** "Geri al" for a row: the busy row, the server's refusal per row, and the rows undone here (before the refetch). */
function useRecentUndo() {
  const qc = useQueryClient();
  const { locale } = useI18n();
  const [busy, setBusy] = useState<number | null>(null);
  const [errors, setErrors] = useState<Record<number, string>>({});
  const [undone, setUndone] = useState<ReadonlySet<number>>(() => new Set());
  const undo = async (r: RecentAction, event: { nativeEvent?: Event } | Event | undefined): Promise<"skipped" | "ok" | "refused"> => {
    if (!r.undo_token || busy !== null || !activation.trusted(event)) return "skipped";
    setBusy(r.id);
    setErrors((e) => {
      const rest = { ...e };
      delete rest[r.id];
      return rest;
    });
    let out: "ok" | "refused" = "refused";
    try {
      const card = await helperApi.undo(r.undo_token);
      out = "ok";
      setUndone((s) => new Set(s).add(r.id));
      toast(card.type === "result" ? pickText(card.message, locale) : translate(locale, "helper.card.undone"));
    } catch (err) {
      const x = helperRefusal(err);
      const text = (locale === "en" ? x.en : x.tr) ?? x.tr ?? x.en ?? translate(locale, x.status === 0 ? "helper.card.network" : "helper.error.provider");
      setErrors((e) => ({ ...e, [r.id]: text }));
      if (x.code === "already_undone") setUndone((s) => new Set(s).add(r.id));
    } finally {
      setBusy(null);
      invalidateAfterHelperWrite(qc, r.action);
    }
    return out;
  };
  const view = (r: RecentAction) => {
    const isUndone = r.status === "undone" || undone.has(r.id);
    return {
      label: pickText(r.label, locale),
      meta: [whenLabel(r.at, locale), translate(locale, isUndone ? "helper.recent.undone" : "helper.recent.done")].filter(Boolean).join(" · "),
      canUndo: r.undoable && !!r.undo_token && !isUndone,
      busy: busy === r.id,
      error: errors[r.id] ?? null,
    };
  };
  return { undo, view };
}

/** The sheet's group (empty thread): heading, up to 5 rows, "Geri al" per undoable row. */
export function RecentActions() {
  const { t } = useI18n();
  const recent = useHelperRecent();
  const { undo, view } = useRecentUndo();
  const headingId = useId();
  const listRef = useRef<HTMLUListElement>(null);
  const list = (recent.data ?? []).slice(0, RECENT_LIMIT);
  if (!list.length) return null;
  // the button goes away after an undo: its row's status line takes the focus (never <body>)
  const refocus = (id: number) =>
    requestAnimationFrame(() => {
      const root = listRef.current;
      (root?.querySelector<HTMLElement>(`[data-recent-undo="${id}"]`) ?? root?.querySelector<HTMLElement>(`[data-recent-status="${id}"]`))?.focus();
    });
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-1" data-testid="helper-recent">
      <h3 id={headingId} className="type-footnote font-medium text-label-2">
        {t("helper.palette.groups.recent")}
      </h3>
      <ul ref={listRef} className="flex flex-col">
        {list.map((r) => {
          const v = view(r);
          return (
            <li key={r.id} className="flex min-h-11 items-center gap-2 py-1.5 not-last:edge-hairline-b" data-testid={`helper-recent-${r.id}`}>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="break-words type-callout text-label-1">{v.label}</span>
                <span tabIndex={-1} data-recent-status={r.id} data-testid={`helper-recent-status-${r.id}`} className="rounded-sm type-footnote text-label-3 outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)">
                  {v.meta}
                </span>
                {v.error ? (
                  <span role="alert" className="type-footnote text-status-warning-fg" data-testid={`helper-recent-error-${r.id}`}>
                    {v.error}
                  </span>
                ) : null}
              </span>
              {v.canUndo ? (
                <Button
                  size="md"
                  variant="ghost"
                  className="shrink-0"
                  aria-label={t("helper.recent.undoName", { label: v.label })}
                  aria-disabled={v.busy || undefined}
                  aria-busy={v.busy || undefined}
                  data-recent-undo={r.id}
                  data-testid={`helper-recent-undo-${r.id}`}
                  onClick={(e) => {
                    if (v.busy) return;
                    void undo(r, e).then((ran) => {
                      if (ran !== "skipped") refocus(r.id);
                    });
                  }}
                >
                  {v.busy ? t("busy.working") : t("helper.card.undo")}
                </Button>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

const ROW = "h-auto min-h-11 py-1.5 max-sm:min-h-14";

/** The palette's group (empty query, first): at most 3 rows; Enter opens the object, "Geri al" undoes. */
export function RecentPaletteGroup() {
  const { t } = useI18n();
  const router = useRouter();
  const { can } = usePermissions();
  const recent = useHelperRecent();
  const { undo, view } = useRecentUndo();
  const list = (recent.data ?? []).slice(0, PALETTE_RECENT);
  if (!list.length) return null;
  const open = (r: RecentAction) => {
    const e = featureById(r.feature_id);
    const href = e && canOpenFeature(e, can) ? featureHref(r.feature_id) : null;
    useUiStore.getState().setPaletteOpen(false);
    if (href) router.push(href);
    else requestAnimationFrame(() => useHelperStore.getState().openSheet());
  };
  // the palette keeps its keyboard model: after "Geri al" the focus goes back to its field
  const backToField = () => requestAnimationFrame(() => document.querySelector<HTMLElement>("[cmdk-input]")?.focus());
  return (
    <CommandGroup heading={t("helper.palette.groups.recent")} data-testid="palette-group-recent">
      {list.map((r) => {
        const v = view(r);
        return (
          <CommandItem key={r.id} value={`helper-recent-${r.id}`} onSelect={() => open(r)} className={ROW} data-testid={`palette-recent-${r.id}`} keywords={[v.label]}>
            <History aria-hidden />
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="truncate">{v.label}</span>
              <span className="truncate type-footnote text-label-3">{v.meta}</span>
              {v.error ? (
                <span role="status" className="type-footnote text-status-warning-fg" data-testid={`palette-recent-error-${r.id}`}>
                  {v.error}
                </span>
              ) : null}
            </span>
            {v.canUndo ? (
              <Button
                size="sm"
                variant="ghost"
                className="ml-auto shrink-0"
                aria-label={t("helper.recent.undoName", { label: v.label })}
                aria-disabled={v.busy || undefined}
                aria-busy={v.busy || undefined}
                data-testid={`palette-recent-undo-${r.id}`}
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  // the row's own select (open the page) must not run
                  e.stopPropagation();
                  e.preventDefault();
                  if (v.busy) return;
                  void undo(r, e).then((ran) => {
                    if (ran !== "skipped") backToField();
                  });
                }}
              >
                <RotateCcw aria-hidden />
                {v.busy ? t("busy.working") : t("helper.card.undo")}
              </Button>
            ) : null}
          </CommandItem>
        );
      })}
    </CommandGroup>
  );
}
