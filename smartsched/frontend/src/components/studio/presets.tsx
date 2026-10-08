"use client";

import { useQueryClient } from "@tanstack/react-query";
import { BookmarkPlus, ChevronDown, Layers, Loader2, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api/endpoints";
import { sk, usePresets } from "@/lib/api/studio-hooks";
import type { Preset, PresetApply } from "@/lib/api/studio-schemas";
import { useI18n } from "@/lib/i18n/provider";
import { formatDate } from "@/lib/time";
import { fallbackSentence, plainRuleText } from "./rule-helpers";
import { localFromDraft } from "./studio-reducer";
import { useStudio } from "./studio-context";

/** (e) Presets: university-wide snapshots of rules, scope and filters. Apply shows a diff first. */
export function PresetMenu({ className, compact }: { className?: string; compact?: boolean }) {
  const { t, locale } = useI18n();
  const { kind, local } = useStudio();
  const presets = usePresets(kind);
  const [apply, setApply] = useState<Preset | null>(null);
  const [saveOpen, setSaveOpen] = useState(false);
  const [manageOpen, setManageOpen] = useState(false);
  const current = presets.data?.find((p) => p.id === local.preset_id);
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger render={<Button variant="outline" size="sm" className={className} data-testid="preset-menu" />}>
          <Layers aria-hidden />
          <span className="truncate">{compact ? t("studio.preset.button") : current ? current.name : t("studio.add.preset")}</span>
          <ChevronDown aria-hidden />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-64">
          <DropdownMenuLabel>{t("studio.preset.shared")}</DropdownMenuLabel>
          {(presets.data ?? []).map((p) => (
            <DropdownMenuItem key={p.id} onClick={() => setApply(p)} data-testid="preset-item">
              <span className="min-w-0 flex-1">
                <span className="block truncate">{p.name}</span>
                <span className="block truncate text-xs text-label-2">
                  {p.author ?? "—"} · {formatDate(p.updated_at ?? p.created_at, locale)}
                </span>
              </span>
            </DropdownMenuItem>
          ))}
          {presets.data?.length === 0 ? <DropdownMenuItem disabled>{t("studio.preset.none")}</DropdownMenuItem> : null}
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => setSaveOpen(true)} data-testid="preset-save">
            <BookmarkPlus aria-hidden /> {t("studio.preset.saveCurrent")}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setManageOpen(true)}>{t("studio.preset.manage")}</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <ApplyPresetDialog preset={apply} onClose={() => setApply(null)} />
      <SavePresetDialog open={saveOpen} onOpenChange={setSaveOpen} />
      <ManagePresetsDialog open={manageOpen} onOpenChange={setManageOpen} presets={presets.data ?? []} />
    </>
  );
}

function ApplyPresetDialog({ preset, onClose }: { preset: Preset | null; onClose: () => void }) {
  const { t, locale } = useI18n();
  const { termId, kind, meta, sentence, dispatch, store, refresh, flush } = useStudio();
  const qc = useQueryClient();
  const [diff, setDiff] = useState<PresetApply | null>(null);
  const [loadedFor, setLoadedFor] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  if (preset && loadedFor !== preset.id) {
    setLoadedFor(preset.id);
    setDiff(null);
    void api.presets.apply(preset.id, termId, true).then(setDiff).catch(() => setDiff(null));
  }
  if (!preset && loadedFor !== null) setLoadedFor(null);

  const text = (r: Record<string, unknown>) => {
    const k = String(r.kind ?? "?");
    const params = (r.params ?? {}) as Record<string, unknown>;
    const nl = typeof r.nl_text === "string" ? r.nl_text : null;
    return nl || Object.keys(params).length ? plainRuleText(meta, k, params, nl, sentence) : fallbackSentence(meta, k, null, locale);
  };

  const run = async () => {
    if (!preset) return;
    setBusy(true);
    try {
      await flush();
      const before = store.getState().studio.local;
      const res = await api.presets.apply(preset.id, termId, false);
      if (res.draft) {
        dispatch({ type: "saved", draft: res.draft, sent: [] });
        qc.setQueryData(sk.draft(termId, kind), res.draft);
      }
      await refresh();
      const after = res.draft ? localFromDraft(res.draft) : null;
      store.getState().record({
        label: t("studio.preset.applied", { name: preset.name }),
        undo: async () => {
          await Promise.all(res.created.map((id) => api.constraints.remove(id)));
          dispatch({ type: "setExcluded", ids: before.excluded });
          for (const id of Object.keys(store.getState().studio.local.rule_overrides)) dispatch({ type: "setOverride", ruleId: Number(id), override: before.rule_overrides[id] ?? null });
          const off = new Set(before.disabled_rule_ids);
          for (const id of store.getState().studio.local.disabled_rule_ids) if (!off.has(id)) dispatch({ type: "setRuleInPlay", ruleId: id, inPlay: true });
          await refresh();
        },
        redo: async () => {
          if (after) dispatch({ type: "setExcluded", ids: after.excluded });
          await api.presets.apply(preset.id, termId, false);
          await refresh();
        },
      });
      toast.success(t("studio.preset.applied", { name: preset.name }), { action: { label: t("common.undo"), onClick: () => void store.getState().undo() } });
      onClose();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={preset !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg" data-testid="preset-apply">
        <DialogHeader>
          <DialogTitle>{t("studio.preset.applyTitle", { name: preset?.name ?? "" })}</DialogTitle>
          <DialogDescription>{preset?.description ?? t("studio.preset.applyHelp")}</DialogDescription>
        </DialogHeader>
        {!diff ? (
          <p className="flex items-center gap-2 text-sm text-label-2" role="status">
            <Loader2 className="size-4 animate-spin" aria-hidden /> {t("common.loading")}
          </p>
        ) : (
          <div className="space-y-3 text-sm">
            <p className="font-medium">{t("studio.preset.diff", { add: diff.add.length, change: diff.change.length, off: diff.turn_off.length })}</p>
            <table className="w-full text-left text-sm">
              <tbody>
                {diff.add.map((r, i) => (
                  <tr key={`a${i}`} className="border-t">
                    <td className="w-8 py-1 font-mono text-status-feasible-fg" aria-label={t("studio.preset.add")}>
                      +
                    </td>
                    <td className="py-1">{text(r)}</td>
                  </tr>
                ))}
                {diff.change.map((r, i) => (
                  <tr key={`c${i}`} className="border-t">
                    <td className="w-8 py-1 font-mono text-status-warning-fg" aria-label={t("studio.preset.change")}>
                      ~
                    </td>
                    <td className="py-1">{text(r)}</td>
                  </tr>
                ))}
                {diff.turn_off.map((r, i) => (
                  <tr key={`o${i}`} className="border-t">
                    <td className="w-8 py-1 font-mono text-status-infeasible-fg" aria-label={t("studio.preset.off")}>
                      −
                    </td>
                    <td className="py-1 line-through decoration-muted-foreground">{text(r)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {diff.unresolved.length ? <p className="text-xs text-status-warning-fg">{t("studio.preset.unresolved", { n: diff.unresolved.length })}</p> : null}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={() => void run()} disabled={!diff || busy} data-testid="preset-apply-confirm">
            {busy ? <Loader2 className="animate-spin" aria-hidden /> : null} {t("common.apply")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SavePresetDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const { t } = useI18n();
  const { termId, kind, flush } = useStudio();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      await flush();
      await api.presets.create({ name: name.trim(), description: description.trim() || null, kind, from_term_id: termId });
      await qc.invalidateQueries({ queryKey: sk.presets(kind) });
      toast.success(t("studio.preset.saved", { name: name.trim() }));
      setName("");
      setDescription("");
      onOpenChange(false);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("studio.preset.saveCurrent")}</DialogTitle>
          <DialogDescription>{t("studio.preset.saveHelp")}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="preset-name">{t("studio.preset.name")}</Label>
            <Input id="preset-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={128} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="preset-desc">{t("studio.preset.description")}</Label>
            <Input id="preset-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button onClick={() => void save()} disabled={!name.trim() || busy}>
            {t("common.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ManagePresetsDialog({ open, onOpenChange, presets }: { open: boolean; onOpenChange: (v: boolean) => void; presets: Preset[] }) {
  const { t, locale } = useI18n();
  const { kind, isAdmin } = useStudio();
  const qc = useQueryClient();
  const remove = async (p: Preset) => {
    await api.presets.remove(p.id);
    await qc.invalidateQueries({ queryKey: sk.presets(kind) });
    toast.success(t("studio.preset.deleted", { name: p.name }));
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("studio.preset.manage")}</DialogTitle>
          <DialogDescription>{t("studio.preset.manageHelp")}</DialogDescription>
        </DialogHeader>
        <ul className="divide-y text-sm">
          {presets.map((p) => (
            <li key={p.id} className="flex items-center gap-2 py-2">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{p.name}</p>
                <p className="truncate text-xs text-label-2">
                  {t("studio.preset.meta", { n: p.rules.length, author: p.author ?? "—", date: formatDate(p.updated_at ?? p.created_at, locale) })}
                </p>
              </div>
              <Button size="icon-sm" variant="ghost" disabled={!isAdmin} title={isAdmin ? undefined : t("studio.preset.adminDelete")} aria-label={t("studio.preset.delete", { name: p.name })} onClick={() => void remove(p)}>
                <Trash2 aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
