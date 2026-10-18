"use client";
/**
 * HX-02 (helper.md §2.3, §8): "Ara veya sor" — the helper's groups inside the ⌘K palette (cmdk).
 *
 * Order with a query: **Sayfalar ve ayarlar** → **Nerede?** → the palette's own data groups → **Kısayollar** →
 * **Yardımcıya sor** (first and preselected when the text reads as a question: the server's `question` flag).
 * `<HelperPaletteTop/>` renders the first two (and a question's ask row), `<HelperPaletteBottom/>` the rest; with an
 * empty query the top shows "Son işlemler" (HX-15, recent.tsx) and the bottom the role starters. Pages and "Nerede?" come from `GET /helper/search` (no AI),
 * permission-filtered by the server and again by the client's link map. Enter on a page opens it, Enter on a
 * "Nerede?" row (or Shift+Enter on a page) opens it **and** rings the control ("Göster"). With AI off there is no
 * ask row (Nerede? and Kısayollar stay); at a hard limit the ask row is disabled with the reason.
 */
import { CornerDownLeft, FileText, MapPin, MessageCircleQuestion, Zap } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useCommandState } from "cmdk";
import { CommandGroup, CommandItem } from "@/components/ui/command";
import { KbdHint } from "@/components/ui/kbd-hint";
import { helperApi, trackHelper, useHelperActions, useHelperSearch } from "@/lib/api/helper";
import { usePermissions } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";
import { useUiStore } from "@/stores/ui";
import { canOpenFeature, featureById, featureHref, pathLine } from "./feature-links";
import { useHelperStore } from "./helper-store";
import { parseIntent } from "./intents";
import { RecentPaletteGroup } from "./recent";
import type { NavCard } from "./schema.gen";
import { useIntentAllowed, useShortcutLabel } from "./shortcut-label";
import { starterRole, useStarters } from "./starters";
import { StatusWordChip, useChipWord, useHelperMode } from "./status-chip";

const PER_GROUP = 6;
const ROW = "h-auto min-h-11 py-1.5 max-sm:min-h-14";

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

/** The visible trigger the sheet returns the focus to (desktop field or the phone's round button). */
function triggerElement(): HTMLElement | null {
  const all = [...document.querySelectorAll<HTMLElement>('[data-testid="helper-trigger"], [data-testid="open-palette-mobile"], [data-testid="open-palette-narrow"]')];
  return all.find((el) => el.getClientRects().length > 0) ?? null;
}

/** The index hits of the palette text: pages / settings and "Nerede?" controls this person may open. */
export function useHelperPaletteSearch(query: string) {
  const text = useDebounced(query.trim(), 150);
  const search = useHelperSearch(text.startsWith(">") ? "" : text);
  const { can } = usePermissions();
  const keep = (n: NavCard) => {
    const e = featureById(n.feature_id);
    return !!e && !!featureHref(n.feature_id) && canOpenFeature(e, can);
  };
  const pages = text ? (search.data?.pages ?? []).filter(keep).slice(0, PER_GROUP) : [];
  const where = text ? (search.data?.where ?? []).filter(keep).slice(0, PER_GROUP) : [];
  const pageHrefs = new Set(pages.map((p) => featureHref(p.feature_id)!.split("#")[0]!));
  return { text, pages, where, question: !!search.data?.question && !!text, pageHrefs, loading: search.isFetching };
}

function usePaletteActions() {
  const router = useRouter();
  const close = () => useUiStore.getState().setPaletteOpen(false);
  return {
    open: (n: NavCard, show: boolean, q: string) => {
      const href = featureHref(n.feature_id);
      if (!href) return;
      close();
      trackHelper({ kind: "nav_click", feature_id: n.feature_id });
      void helperApi.searchFinal(q).catch(() => undefined);
      if (show && (n.anchor ?? featureById(n.feature_id)?.anchor)) useHelperStore.getState().startShowMe(n.feature_id, false);
      else router.push(href);
    },
    ask: (q: string) => {
      close();
      const opener = triggerElement();
      requestAnimationFrame(() => useHelperStore.getState().openSheet({ opener, ask: q }));
    },
    run: (action: string, args: Record<string, string | number>, hints?: { time?: string; period?: number }) => {
      close();
      const opener = triggerElement();
      requestAnimationFrame(() => useHelperStore.getState().openSheet({ opener, action: { action, args, hints } }));
    },
  };
}

/** Shift+Enter on a helper row = Göster (cmdk would select it as a plain Enter). */
function useShiftEnter(onShow: (value: string) => boolean) {
  const selected = useCommandState((s) => s.value);
  const latest = useRef({ selected, onShow });
  useEffect(() => {
    latest.current = { selected, onShow };
  });
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Enter" || !e.shiftKey || e.isComposing) return;
      if (latest.current.onShow(latest.current.selected)) {
        e.preventDefault();
        e.stopPropagation();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, []);
}

function NavRow({ n, kind, onSelect }: { n: NavCard; kind: "page" | "where"; onSelect: (show: boolean) => void }) {
  const { t, locale } = useI18n();
  const e = featureById(n.feature_id)!;
  const title = (locale === "en" ? n.title?.en : n.title?.tr) || e.title[locale] || e.title.tr;
  const path = pathLine(n.path, locale) || pathLine(e.path, locale);
  const Icon = kind === "where" ? MapPin : FileText;
  return (
    <CommandItem value={`helper-${kind}-${n.feature_id}`} onSelect={() => onSelect(kind === "where")} className={ROW} data-testid={`palette-${kind}-${n.feature_id}`} keywords={[title, path]}>
      <Icon aria-hidden />
      <span className="flex min-w-0 flex-col">
        <span className="truncate">{title}</span>
        {path ? <span className="truncate type-footnote text-label-3">{path}</span> : null}
      </span>
      {n.anchor ?? e.anchor ? (
        kind === "where" ? (
          <span className="ml-auto pl-3 type-footnote text-label-3">{t("helper.palette.showHint")}</span>
        ) : (
          // HB18-F11: keycaps mean nothing on a touch phone (no Shift); the "Nerede?" row says "Göster" there
          <span className="ml-auto pl-3 type-footnote text-label-3 pointer-coarse:hidden" data-testid="palette-kbd-hint">
            <KbdHint keys={["shift", "enter"]} aria-hidden />
          </span>
        )
      ) : null}
    </CommandItem>
  );
}

function AskRow({ q }: { q: string }) {
  const { t } = useI18n();
  const mode = useHelperMode();
  const word = useChipWord(mode);
  const act = usePaletteActions();
  if (!mode.status?.enabled || !mode.ai) return null;
  return (
    <CommandGroup heading={t("helper.palette.groups.ask")} data-testid="palette-group-ask">
      <CommandItem
        value="helper-ask"
        disabled={mode.blocked}
        onSelect={() => act.ask(q)}
        className={ROW}
        data-testid="palette-ask"
        aria-label={mode.blocked ? t("helper.palette.askBlocked") : t("helper.palette.askName", { q, state: word })}
      >
        <MessageCircleQuestion aria-hidden />
        <span className="min-w-0 flex-1 truncate">{mode.blocked ? t("helper.palette.askBlocked") : t("helper.palette.ask", { q })}</span>
        <StatusWordChip mode={mode} className="ml-auto" />
      </CommandItem>
    </CommandGroup>
  );
}

/** HX-15: "Son işlemler" first in the empty palette, while the helper is on for this person. */
function RecentRows() {
  const mode = useHelperMode();
  if (!mode.status?.enabled) return null;
  return <RecentPaletteGroup />;
}

/** Groups 1 and 2 (and a question's ask row on top); "Son işlemler" for an empty query. */
export function HelperPaletteTop({ query }: { query: string }) {
  const { t } = useI18n();
  const { text, pages, where, question } = useHelperPaletteSearch(query);
  const act = usePaletteActions();
  useShiftEnter((value) => {
    const m = /^helper-(page|where)-(.+)$/.exec(value);
    if (!m) return false;
    const n = [...pages, ...where].find((x) => x.feature_id === m[2]);
    if (!n) return false;
    act.open(n, true, text);
    return true;
  });
  if (!query.trim()) return <RecentRows />;
  if (!text || text.startsWith(">")) return null;
  return (
    <>
      {question ? <AskRow q={text} /> : null}
      {pages.length ? (
        <CommandGroup heading={t("helper.palette.groups.pages")} data-testid="palette-group-pages">
          {pages.map((n) => (
            <NavRow key={n.id} n={n} kind="page" onSelect={(show) => act.open(n, show, text)} />
          ))}
        </CommandGroup>
      ) : null}
      {where.length ? (
        <CommandGroup heading={t("helper.palette.groups.where")} data-testid="palette-group-where">
          {where.map((n) => (
            <NavRow key={n.id} n={n} kind="where" onSelect={(show) => act.open(n, show, text)} />
          ))}
        </CommandGroup>
      ) : null}
    </>
  );
}

function ShortcutRow({ q }: { q: string }) {
  const { t } = useI18n();
  const actions = useHelperActions();
  const allowed = useIntentAllowed();
  const act = usePaletteActions();
  const intent = parseIntent(q);
  const label = useShortcutLabel(intent);
  const set = actions.data ? new Set(actions.data.map((a) => a.name)) : null;
  if (!intent || !label || !allowed(intent, set)) return null;
  return (
    <CommandGroup heading={t("helper.palette.groups.shortcuts")} data-testid="palette-group-shortcuts">
      <CommandItem value={`helper-shortcut-${intent.action}`} onSelect={() => act.run(intent.action, intent.args, intent.hints)} className={ROW} data-testid={`palette-shortcut-${intent.action}`}>
        <Zap aria-hidden />
        <span className="min-w-0 flex-1 truncate">{label}</span>
        <CornerDownLeft aria-hidden className="ml-auto" />
      </CommandItem>
    </CommandGroup>
  );
}

function StarterRows() {
  const { t } = useI18n();
  const { can } = usePermissions();
  const mode = useHelperMode();
  const starters = useStarters(starterRole(can));
  const act = usePaletteActions();
  if (!mode.status?.enabled) return null;
  return (
    <CommandGroup heading={t("helper.palette.groups.starters")} data-testid="palette-group-starters">
      {starters.map((s, i) => (
        <CommandItem key={s} value={`helper-starter-${i}`} onSelect={() => act.ask(s)} className={ROW}>
          <MessageCircleQuestion aria-hidden />
          <span className="min-w-0 truncate">{s}</span>
        </CommandItem>
      ))}
    </CommandGroup>
  );
}

/** Groups 4 and 5 (Kısayollar, the ask row); the role starters for an empty query. */
export function HelperPaletteBottom({ query }: { query: string }) {
  const { text, question } = useHelperPaletteSearch(query);
  if (query.trim().startsWith(">")) return null;
  if (!query.trim()) return <StarterRows />;
  return (
    <>
      <ShortcutRow q={text || query.trim()} />
      {question ? null : <AskRow q={text || query.trim()} />}
    </>
  );
}

/**
 * HX-18 m7 (helper.md §2.3, §9 rule 14): the palette's empty state. No hits: "“…” için sonuç yok." and, when the
 * helper runs in index mode (AI off), the next step ("Yardımcı şu an kapalı. Yazımı kontrol edin …"). The shell's
 * `<CommandEmpty>` renders it.
 */
export function HelperPaletteEmpty({ query, loading }: { query: string; loading: boolean }) {
  const { t } = useI18n();
  const mode = useHelperMode();
  if (loading) return <>{t("glass.palette.searching")}</>;
  const off = !mode.loading && !!mode.status && !mode.ai;
  return (
    <span className="flex flex-col items-center gap-1" data-testid="palette-none">
      <span>{t("helper.palette.none", { q: query })}</span>
      {off ? <span className="type-footnote text-label-2">{t("helper.palette.offHint")}</span> : null}
    </span>
  );
}
