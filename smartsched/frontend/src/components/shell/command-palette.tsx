"use client";

import { FileUp, Languages, Monitor, PlayCircle, Warehouse } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Command, CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandShortcut } from "@/components/ui/command";
import { useRooms, useRuns } from "@/lib/api/hooks";
import { useI18n } from "@/lib/i18n/provider";
import { useUiStore } from "@/stores/ui";
import { LOCALES } from "@/lib/i18n";
import { ALL_NAV_ITEMS } from "./nav-config";
import { useCycleTheme } from "./theme-toggle";

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

export function CommandPalette() {
  const open = useUiStore((s) => s.paletteOpen);
  const setOpen = useUiStore((s) => s.setPaletteOpen);
  const router = useRouter();
  const { t, locale, setLocale } = useI18n();
  const cycleTheme = useCycleTheme();
  const [query, setQuery] = useState("");
  const debounced = useDebounced(query, 150);
  const actionsOnly = query.startsWith(">");
  const roomQuery = /^[A-Da-d]\s?[zZ]?\d/.test(debounced) ? debounced : debounced.length >= 2 ? debounced : "";
  const rooms = useRooms(roomQuery ? { q: roomQuery } : { q: "__none__" });
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

  const roomItems = useMemo(() => (roomQuery ? (rooms.data ?? []).slice(0, 8) : []), [roomQuery, rooms.data]);
  const runMatch = /^#?(\d+)$/.exec(debounced.trim());
  const runItems = (runs.data ?? []).filter((r) => !runMatch || String(r.id).startsWith(runMatch[1])).slice(0, 8);

  return (
    <CommandDialog open={open} onOpenChange={setOpen} title={t("palette.title")} description={t("palette.placeholder")} className="sm:max-w-[640px]">
      <Command shouldFilter={!actionsOnly} loop>
        <CommandInput placeholder={t("palette.placeholder")} value={query} onValueChange={setQuery} className="text-base sm:text-sm" />
        <CommandList className="max-h-[60vh]">
          <CommandEmpty>{t("palette.empty", { query })}</CommandEmpty>
          <CommandGroup heading={t("palette.actions")}>
            <CommandItem value="action generate" onSelect={() => go("/generate")}>
              <PlayCircle /> {t("palette.generateWeek")} <CommandShortcut>g g</CommandShortcut>
            </CommandItem>
            <CommandItem value="action import" onSelect={() => go("/import")}>
              <FileUp /> {t("palette.importFile")} <CommandShortcut>g i</CommandShortcut>
            </CommandItem>
            <CommandItem value="action new room" onSelect={() => go("/rooms?new=1")}>
              <Warehouse /> {t("palette.newRoom")}
            </CommandItem>
          </CommandGroup>
          {!actionsOnly ? (
            <>
              <CommandGroup heading={t("palette.goto")}>
                {ALL_NAV_ITEMS.map((item) => (
                  <CommandItem key={item.href} value={`goto ${t(item.labelKey)} ${item.href}`} onSelect={() => go(item.href)}>
                    <item.icon /> {t(item.labelKey)}
                    {item.key ? <CommandShortcut>g {item.key}</CommandShortcut> : null}
                  </CommandItem>
                ))}
              </CommandGroup>
              {roomItems.length > 0 ? (
                <CommandGroup heading={t("palette.rooms")}>
                  {roomItems.map((r) => (
                    <CommandItem key={r.id} value={`room ${r.display_name} ${r.code} ${r.tags.join(" ")}`} onSelect={() => go(`/rooms/${r.id}`)}>
                      <Warehouse /> <span className="font-mono">{r.display_name}</span>
                      <span className="text-muted-foreground">· {r.capacity} {t("common.seats")} {r.tags.join(" ")}</span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              ) : null}
              {runItems.length > 0 ? (
                <CommandGroup heading={t("palette.runs")}>
                  {runItems.map((r) => (
                    <CommandItem key={r.id} value={`run #${r.id} ${r.term_code} ${r.status}`} onSelect={() => go(`/runs/${r.id}`)}>
                      <span className="font-mono">#{r.id}</span> {r.term_code} <span className="text-muted-foreground">· {t(`runs.status.${r.status}`)}</span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              ) : null}
              <CommandGroup heading={t("palette.prefs")}>
                <CommandItem value="theme toggle" onSelect={() => { cycleTheme(); setOpen(false); }}>
                  <Monitor /> {t("palette.toggleTheme")} <CommandShortcut>t</CommandShortcut>
                </CommandItem>
                <CommandItem value="language toggle" onSelect={() => { setLocale(LOCALES[(LOCALES.indexOf(locale) + 1) % LOCALES.length]); router.refresh(); setOpen(false); }}>
                  <Languages /> {t("palette.toggleLang")} <CommandShortcut>l</CommandShortcut>
                </CommandItem>
              </CommandGroup>
            </>
          ) : null}
        </CommandList>
        <div className="flex items-center gap-3 border-t px-3 py-1.5 text-[11px] text-muted-foreground">
          <span><kbd className="rounded border bg-muted px-1 font-mono">↑↓</kbd> {t("palette.navigate")}</span>
          <span><kbd className="rounded border bg-muted px-1 font-mono">↵</kbd> {t("palette.select")}</span>
          <span><kbd className="rounded border bg-muted px-1 font-mono">esc</kbd> {t("palette.close")}</span>
        </div>
      </Command>
    </CommandDialog>
  );
}
