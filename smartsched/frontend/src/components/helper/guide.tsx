"use client";
/**
 * HX-03 (helper.md §5.3): **Rehber modu** — the helper with no model. Shown when `GET /helper/status` says
 * `mode: index` (the default until an administrator routes the helper), and at a hard limit under the disabled
 * composer: a "Ne arıyorsunuz?" field over `GET /helper/search` (pages, "Nerede?" answers, data hits) and the
 * deterministic shortcut of the typed text. Nothing here calls a model or writes `ai_usage`.
 */
import { CornerDownLeft, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useHelperSearch } from "@/lib/api/helper";
import { useI18n } from "@/lib/i18n/provider";
import { useCardHost } from "./cards/context";
import { NavView } from "./cards/nav";
import { dataHitHref } from "./feature-links";
import { parseIntent } from "./intents";
import { useShortcutLabel } from "./shortcut-label";

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

export function GuideMode({ inputRef, seed, showLead = true }: { inputRef?: React.Ref<HTMLInputElement>; seed?: string | null; showLead?: boolean }) {
  const { t } = useI18n();
  const host = useCardHost();
  const [q, setQ] = useState(seed ?? "");
  const [seen, setSeen] = useState(seed);
  if (seed !== seen) {
    setSeen(seed);
    if (seed) setQ(seed);
  }
  const text = useDebounced(q, 150).trim();
  const search = useHelperSearch(text);
  const intent = text ? parseIntent(text) : null;
  const shortcut = intent && (!host.actions || host.actions.has(intent.action)) ? intent : null;
  const label = useShortcutLabel(shortcut);
  const data = Object.values(search.data?.data ?? {}).flat().slice(0, 6);
  const hits = [...(search.data?.pages ?? []), ...(search.data?.where ?? [])];
  const none = text.length >= 2 && search.isSuccess && !hits.length && !data.length && !shortcut;
  return (
    <div className="flex flex-col gap-3" data-testid="helper-guide">
      {showLead ? <p className="type-footnote text-label-2">{t("helper.guide.mode")}</p> : null}
      <label className="relative block">
        <span className="sr-only">{t("helper.guide.field")}</span>
        <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-label-3" />
        <Input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("helper.guide.field")} className="h-11 pl-9 text-base" data-testid="helper-guide-input" enterKeyHint="search" />
      </label>
      <div className="flex flex-col gap-2" aria-live="polite">
        {shortcut && label ? (
          <Button variant="secondary" size="md" className="h-auto min-h-11 justify-between gap-2 py-2 text-left whitespace-normal" shape="rect" onClick={() => void host.runner.runAction(shortcut.action, shortcut.args, { hints: shortcut.hints })} data-testid={`palette-shortcut-${shortcut.action}`}>
            <span>
              <span className="block type-footnote text-label-2">{t("helper.palette.groups.shortcuts")}</span>
              {label}
            </span>
            <CornerDownLeft aria-hidden />
          </Button>
        ) : null}
        {hits.map((n) => (
          <NavView key={n.id} card={n} compact />
        ))}
        {data.length ? (
          <ul className="flex flex-col">
            {data.map((d) => {
              const href = dataHitHref(d);
              if (!href) return null;
              return (
                <li key={`${d.kind}-${d.id}`}>
                  <Button variant="ghost" size="md" className="h-auto min-h-11 w-full justify-start gap-2 text-left whitespace-normal" shape="rect" onClick={() => host.go(href)}>
                    <span className="font-medium">{d.label}</span>
                    {d.sub ? <span className="text-label-2">· {host.locale === "en" ? d.sub.en : d.sub.tr}</span> : null}
                  </Button>
                </li>
              );
            })}
          </ul>
        ) : null}
        {search.isFetching && !search.data ? <p className="type-footnote text-label-3">{t("glass.palette.searching")}</p> : null}
        {none ? <p className="type-callout text-label-2" data-testid="helper-guide-empty">{t("helper.palette.none", { q: text })}</p> : null}
      </div>
    </div>
  );
}
