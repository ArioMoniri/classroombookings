"use client";

import { BookOpen, CalendarSearch, FileUp, GraduationCap, Languages, ListChecks, Monitor, PlayCircle, UserRound, Warehouse } from "lucide-react";
import { LayoutGroup, motion } from "motion/react";
import { useRouter } from "next/navigation";
import { useDeferredValue, useEffect, useMemo, useState, type ReactNode } from "react";
import { StatusBadge } from "@/components/common/status-badge";
import { runStatusBadge } from "@/components/runs/runs-list";
import { Command, CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { KbdHint } from "@/components/ui/kbd-hint";
import { useRooms, useRuns } from "@/lib/api/hooks";
import { normaliseQuery, usePermissions, useShellSearch } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";
import { springs, useReduce } from "@/lib/motion";
import { useUiStore } from "@/stores/ui";
import { visibleNavGroups, type NavItem } from "./nav-config";
import { useActiveTerm } from "./term-switcher";
import { useCycleTheme } from "./theme-toggle";

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

/** Turkish-aware, diacritic-insensitive fold ("Şube" ~ "sube", "İLAÇ" ~ "ilac", "PHAR240" ~ "phar 240"). */
export function fold(text: string): string {
  return text
    .toLocaleLowerCase("tr-TR")
    .replace(/ı/g, "i")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/\s+/g, "");
}

export function matches(query: string, ...haystack: (string | null | undefined)[]): boolean {
  const q = fold(query);
  if (!q) return true;
  return haystack.some((h) => h && fold(h).includes(q));
}

/** One gliding highlight for the selected row (motion pattern §18): snappy, a fill (no glass on glass). */
function Row({ selected, children }: { selected: boolean; children: ReactNode }) {
  const reduce = useReduce();
  return (
    <>
      {selected ? <motion.span layoutId="palette-row" aria-hidden className="pointer-events-none absolute inset-0 -z-10 rounded-[10px] bg-fill-1" transition={reduce ? { duration: 0 } : springs.snappy} /> : null}
      {children}
    </>
  );
}

export function CommandPalette() {
  const open = useUiStore((s) => s.paletteOpen);
  // the store update is synchronous (useSyncExternalStore); rendering the result groups in a deferred,
  // time-sliced pass keeps the opening frame short (motion audit: LoAF on open)
  const listReady = useDeferredValue(open);
  const setOpen = useUiStore((s) => s.setPaletteOpen);
  const router = useRouter();
  const { t, locale, setLocale, languages } = useI18n();
  const cycleTheme = useCycleTheme();
  const { term } = useActiveTerm();
  const { can } = usePermissions();
  const planner = can("planning.view");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState("");
  const debounced = normaliseQuery(useDebounced(query, 150));
  const actionsOnly = query.startsWith(">");
  const text = actionsOnly ? query.slice(1).trim() : query.trim();
  const live = !actionsOnly && debounced.length >= 2 ? debounced : "";
  const search = useShellSearch(planner ? live : "", term?.id);
  const rooms = useRooms(live ? { q: live } : { q: "__none__" });
  const runs = useRuns();

  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (!open) setQuery("");
  }

  const go = (href: string) => {
    setOpen(false);
    router.push(href);
  };

  const actions = [
    { value: "action-generate", icon: PlayCircle, label: t("palette.generateWeek"), keys: ["G", "G"], run: () => go("/generate"), words: "generate oluştur plan solve", allowed: can("planning.edit") },
    { value: "action-import", icon: FileUp, label: t("palette.importFile"), keys: ["G", "I"], run: () => go("/import"), words: "import içe aktar excel", allowed: can("planning.edit") },
    // the create form lives in Admin → Rooms (setup.rooms; POST /rooms also accepts it, UI gap audit #4)
    // T1 (wave 1): "boş derslik" / "find a room", for every signed-in user
    { value: "action-find-room", icon: CalendarSearch, label: t("wave1.find.palette"), run: () => go("/find-room"), words: "boş derslik bul find free room oda ara salon amfi", allowed: true },
    { value: "action-room", icon: Warehouse, label: t("palette.newRoom"), run: () => go("/admin/rooms?tab=rooms&new=1"), words: "room derslik yeni new oda", allowed: can("setup.rooms") },
  ].filter((a) => a.allowed && matches(text, a.label, a.words));
  // the profile (names, language, password) belongs to every user, so it is always in "Go to" (UI gap audit #1)
  const profileItem: NavItem = { href: "/profile", labelKey: "crbs.nav.profile", icon: UserRound };
  const gotos = actionsOnly ? [] : [...visibleNavGroups(can).flatMap((g) => g.items), profileItem].filter((i) => matches(text, t(i.labelKey), i.href));
  const prefs = [
    { value: "pref-theme", icon: Monitor, label: t("palette.toggleTheme"), keys: ["T"], run: () => { cycleTheme(); setOpen(false); }, words: "theme tema dark light koyu açık" },
    { value: "pref-lang", icon: Languages, label: t("palette.toggleLang"), keys: ["L"], run: () => { setLocale(languages[(languages.indexOf(locale) + 1) % languages.length]!); router.refresh(); setOpen(false); }, words: "language dil türkçe english" },
  ].filter((p) => matches(text, p.label, p.words));

  const results = live ? search.data : undefined;
  const sectionsByCourse = useMemo(() => {
    const seen = new Map<string, { code: string; name: string; count: number; programs: Set<string> }>();
    for (const s of results?.sections ?? []) {
      const code = s.course_code ?? "";
      const row = seen.get(code) ?? { code, name: s.course_name ?? "", count: 0, programs: new Set<string>() };
      row.count += 1;
      if (s.program_name) row.programs.add(s.program_name);
      seen.set(code, row);
    }
    for (const c of results?.courses ?? []) {
      const code = c.display_code ?? c.code;
      if (!seen.has(code)) seen.set(code, { code, name: c.name ?? "", count: 0, programs: new Set() });
    }
    return [...seen.values()].slice(0, 6);
  }, [results]);
  const roomItems = live && planner ? (rooms.data ?? []).slice(0, 6) : [];
  const runMatch = /^#?(\d+)$/.exec(text);
  const runItems = actionsOnly || !planner ? [] : (runs.data ?? []).filter((r) => (runMatch ? String(r.id).startsWith(runMatch[1] ?? "") : matches(text, r.term_code, `#${r.id}`, t(`runs.status.${r.status}`)))).slice(0, 5);
  const loading = live !== "" && search.isFetching && !results;

  const item = (value: string, onSelect: () => void, children: ReactNode, hint?: ReactNode) => (
    <CommandItem key={value} value={value} onSelect={onSelect} className="isolate data-selected:bg-transparent">
      <Row selected={selected === value}>
        {children}
        {hint ? <span className="ml-auto flex items-center pl-3">{hint}</span> : null}
      </Row>
    </CommandItem>
  );

  return (
    <CommandDialog open={open} onOpenChange={setOpen} title={t("palette.title")} description={t("glass.palette.placeholder")} className="top-2 max-w-[calc(100vw-1rem)] sm:top-[14%] sm:max-w-[640px]">
      <LayoutGroup id="palette">
        <Command shouldFilter={false} loop value={selected} onValueChange={setSelected} label={t("palette.title")}>
          <CommandInput placeholder={t("glass.palette.placeholder")} value={query} onValueChange={setQuery} className="text-base sm:text-[16px]" />
          <CommandList className="max-h-[min(60vh,520px)]">
            {listReady ? (
              <>
            <CommandEmpty>{loading ? t("glass.palette.searching") : t("glass.palette.empty", { query: text })}</CommandEmpty>
            {sectionsByCourse.length ? (
              <CommandGroup heading={t("glass.palette.courses")}>
                {sectionsByCourse.map((c) =>
                  item(
                    `course-${c.code}`,
                    () => go(`/requests?q=${encodeURIComponent(c.code)}`),
                    <>
                      <BookOpen aria-hidden />
                      <span className="font-medium">{c.code}</span>
                      <span className="min-w-0 truncate text-label-2">{c.name}</span>
                    </>,
                    c.count ? <span className="text-[12px] text-label-3 tabular-nums">{t("glass.palette.sections", { n: c.count })}</span> : undefined,
                  ),
                )}
              </CommandGroup>
            ) : null}
            {results?.instructors.length ? (
              <CommandGroup heading={t("glass.palette.instructors")}>
                {results.instructors.map((p) =>
                  item(
                    `instructor-${p.id}`,
                    () => go(`/timetable?subject=instructor:${p.id}`),
                    <>
                      <UserRound aria-hidden />
                      <span className="truncate">{p.title ? `${p.title} ` : ""}{p.full_name}</span>
                    </>,
                  ),
                )}
              </CommandGroup>
            ) : null}
            {results?.programs.length ? (
              <CommandGroup heading={t("glass.palette.programs")}>
                {results.programs.map((p) =>
                  item(
                    `program-${p.id}`,
                    () => go(`/requests?program_id=${p.id}`),
                    <>
                      <GraduationCap aria-hidden />
                      <span className="truncate">{p.name}</span>
                      {p.is_evening ? <span className="text-[12px] text-label-3">· {t("glass.palette.evening")}</span> : null}
                    </>,
                  ),
                )}
              </CommandGroup>
            ) : null}
            {roomItems.length ? (
              <CommandGroup heading={t("palette.rooms")}>
                {roomItems.map((r) =>
                  item(
                    `room-${r.id}`,
                    () => go(`/rooms/${r.id}`),
                    <>
                      <Warehouse aria-hidden />
                      <span className="font-medium">{r.display_name}</span>
                      <span className="truncate text-label-2">· {t("glass.palette.seats", { n: r.capacity })}{r.tags.length ? ` · ${r.tags.join(" ")}` : ""}</span>
                    </>,
                  ),
                )}
              </CommandGroup>
            ) : null}
            {runItems.length ? (
              <CommandGroup heading={t("palette.runs")}>
                {runItems.map((r) =>
                  item(
                    `run-${r.id}`,
                    () => go(`/runs/${r.id}`),
                    <>
                      <ListChecks aria-hidden />
                      <span className="font-medium">{t("glass.shell.runTitle", { id: r.id, term: r.term_code })}</span>
                    </>,
                    <StatusBadge {...runStatusBadge(r, t)} />,
                  ),
                )}
              </CommandGroup>
            ) : null}
            {actions.length ? (
              <CommandGroup heading={t("palette.actions")}>
                {actions.map((a) =>
                  item(
                    a.value,
                    a.run,
                    <>
                      <a.icon aria-hidden /> {a.label}
                    </>,
                    a.keys ? <KbdHint keys={a.keys} sequence thenLabel={t("glass.shell.then")} /> : undefined,
                  ),
                )}
              </CommandGroup>
            ) : null}
            {gotos.length ? (
              <CommandGroup heading={t("palette.goto")}>
                {gotos.map((i) =>
                  item(
                    `goto-${i.href}`,
                    () => go(i.href),
                    <>
                      <i.icon aria-hidden /> {t(i.labelKey)}
                    </>,
                    i.key ? <KbdHint keys={["G", i.key.toUpperCase()]} sequence thenLabel={t("glass.shell.then")} /> : undefined,
                  ),
                )}
              </CommandGroup>
            ) : null}
            {prefs.length ? (
              <CommandGroup heading={t("palette.prefs")}>
                {prefs.map((p) =>
                  item(
                    p.value,
                    p.run,
                    <>
                      <p.icon aria-hidden /> {p.label}
                    </>,
                    <KbdHint keys={p.keys} />,
                  ),
                )}
              </CommandGroup>
            ) : null}
              </>
            ) : null}
          </CommandList>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 pt-2 pb-1 text-[11px] text-label-3 hairline-t">
            <span className="inline-flex items-center gap-1"><KbdHint keys={["↑"]} /><KbdHint keys={["↓"]} /> {t("palette.navigate")}</span>
            <span className="inline-flex items-center gap-1"><KbdHint keys={["enter"]} /> {t("palette.select")}</span>
            <span className="inline-flex items-center gap-1"><KbdHint keys={["esc"]} /> {t("palette.close")}</span>
            <span className="ml-auto hidden sm:inline">{t("glass.palette.safe")}</span>
          </div>
        </Command>
      </LayoutGroup>
    </CommandDialog>
  );
}
