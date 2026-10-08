"use client";

import { ChevronDown, Copy, FileUp, LayoutTemplate, Lock, Search } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { NativeSelect } from "@/components/common/native-select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import type { PrecheckItem } from "@/lib/api/studio-schemas";
import type { MessageKey } from "@/lib/i18n";
import { useSettingsPeek } from "@/lib/api/studio-hooks";
import { useI18n } from "@/lib/i18n/provider";
import { PERIODS } from "@/lib/time";
import { cn } from "@/lib/utils";
import { fold } from "./class-filters";
import { CopyDialog } from "./copy-dialog";
import { BuiltinRules, PolicySwitches } from "./policy-switches";
import { PresetMenu } from "./presets";
import { ReviewTray } from "./review-tray";
import { RuleCard } from "./rule-card";
import { plainRuleText } from "./rule-helpers";
import { templateFor } from "./rule-sentence";
import { useStudio, useStudioStore } from "./studio-context";
import { effectiveRules, isPlacementPin, pinOverrides, type EffectiveRule } from "./studio-reducer";
import { TemplateGallery, type BuilderPrefill } from "./template-gallery";
import { TermRuleCard } from "./term-rule-card";
import { UploadPanel } from "./upload-panel";
import { UploadReview } from "./upload-review";
import { useRuleActions } from "./use-rule-actions";
import { WriteIt } from "./write-it";
import type { ProposedConstraint } from "@/lib/api/schemas";
import type { TrayItem } from "./studio-store";

type GroupBy = "status" | "topic" | "source";
const SOURCES = ["FILE", "ADMIN", "AI", "UPLOAD"] as const;

export function RulesStep({ builderPrefill, onBuilderConsumed }: { builderPrefill?: BuilderPrefill | null; onBuilderConsumed?: () => void }) {
  const { t, n } = useI18n();
  const { rules, local, meta, sentence, precheck, store, dispatch } = useStudio();
  const settings = useSettingsPeek();
  const actions = useRuleActions();
  const tray = useStudioStore((s) => s.tray);
  const [gallery, setGallery] = useState(false);
  const [upload, setUpload] = useState(false);
  const [copy, setCopy] = useState(false);
  const [q, setQ] = useState("");
  const [source, setSource] = useState("");
  const [hard, setHard] = useState("");
  const [problemsOnly, setProblemsOnly] = useState(false);
  const [groupBy, setGroupBy] = useState<GroupBy>("status");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set(["builtin", "off"]));

  const galleryOpen = gallery || Boolean(builderPrefill);
  // real pins (room / day and time) vs the draft-only changes a pre-check fix made (unlock, tags, seats)
  const placed = useMemo(() => local.pins.filter(isPlacementPin), [local.pins]);
  const changed = useMemo(() => local.pins.filter((p) => Object.keys(pinOverrides(p)).length > 0), [local.pins]);
  const classLabel = sentence.classLabel;
  const eff = useMemo(() => effectiveRules(rules?.rules ?? [], local), [rules, local]);
  const clashes = useMemo(() => (precheck?.items ?? []).filter((i) => i.category === "clash"), [precheck]);
  const clashFor = (id: number): PrecheckItem | null => clashes.find((c) => c.constraint_ids.includes(id)) ?? null;
  const problem = (e: EffectiveRule) => e.rule.affected_count === 0 || clashFor(e.rule.id) !== null;

  const filtered = eff.filter((e) => {
    if (source && e.rule.source !== source) return false;
    if (hard && e.hardness !== hard) return false;
    if (problemsOnly && !problem(e)) return false;
    const qq = fold(q).trim();
    if (qq && !fold(`${plainRuleText(meta, e.rule.kind, e.rule.params, e.rule.nl_text, sentence)} ${e.rule.nl_text ?? ""}`).includes(qq)) return false;
    return true;
  });
  const compact = eff.length > 40;
  const must = eff.filter((e) => e.inPlay && e.hardness === "hard").length;
  const tryTo = eff.filter((e) => e.inPlay && e.hardness === "soft").length;
  const problems = eff.filter((e) => e.inPlay && problem(e)).length;

  const groups: { key: string; label: string; items: EffectiveRule[] }[] = useMemo(() => {
    if (groupBy === "status")
      return [
        { key: "must", label: t("studio.rules.groupMust"), items: filtered.filter((e) => e.inPlay && e.hardness === "hard") },
        { key: "try", label: t("studio.rules.groupTry"), items: filtered.filter((e) => e.inPlay && e.hardness === "soft") },
        { key: "off", label: t("studio.rules.groupOff"), items: filtered.filter((e) => !e.inPlay) },
      ];
    if (groupBy === "source") return SOURCES.map((s) => ({ key: s, label: t(`studio.source.${s}`), items: filtered.filter((e) => e.rule.source === s) }));
    const topics: MessageKey[] = ["studio.topic.rooms", "studio.topic.times", "studio.topic.buildings", "studio.topic.programmes", "studio.topic.exams"];
    const topicOf = (e: EffectiveRule) => templateFor(e.rule.kind, e.rule.params, meta?.templates ?? [])?.topic ?? "rooms";
    return topics.map((k) => ({ key: k, label: t(k), items: filtered.filter((e) => `studio.topic.${topicOf(e)}` === k) }));
  }, [groupBy, filtered, t, meta]);

  const nlTray = tray.filter((i) => i.origin === "nl");
  const upTray = tray.filter((i) => i.origin === "upload");
  const noKey = settings.data ? !settings.data.anthropic_api_key_masked : false;
  const onReject = (keys: string[]) => store.getState().setTrayState(keys, "rejected");
  const onUpdate = (key: string, proposal: ProposedConstraint) => store.getState().updateTray(key, { proposal } as Partial<TrayItem>);
  const firstVisit = rules !== undefined && rules.rules.length === 0 && tray.length === 0;

  const toggleGroup = (k: string) =>
    setCollapsed((s) => {
      const next = new Set(s);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });

  return (
    <div className="space-y-5" data-testid="rules-step">
      <div className="sticky top-0 z-10 -mx-1 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md bg-background/95 px-1 py-1.5 text-sm backdrop-blur-sm" aria-live="polite" data-testid="rules-counter">
        <span>
          <strong className="tabular-nums">{n(must)}</strong> {t("studio.rules.mustWord")}
        </span>
        <span aria-hidden>·</span>
        <span>
          <strong className="tabular-nums">{n(tryTo)}</strong> {t("studio.rules.tryWord")}
        </span>
        {problems ? (
          <>
            <span aria-hidden>·</span>
            <span className="text-status-warning-fg">{t("studio.rules.problems", { n: problems })}</span>
          </>
        ) : null}
      </div>

      {firstVisit ? (
        <div className="rounded-lg border bg-tint-soft/40 p-3 text-sm" data-testid="rules-explainer">
          {t("studio.rules.explainer")}
        </div>
      ) : null}

      <section aria-labelledby="add-rule-title" className="space-y-3 rounded-xl border bg-card p-3 sm:p-4">
        <h3 id="add-rule-title" className="sr-only">
          {t("studio.add.title")}
        </h3>
        <WriteIt noKey={noKey} />
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => setGallery(true)} data-testid="add-template">
            <LayoutTemplate aria-hidden /> {t("studio.add.template")}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setUpload((v) => !v)} aria-expanded={upload} data-testid="add-upload">
            <FileUp aria-hidden /> {t("studio.add.upload")}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setCopy(true)} data-testid="add-copy">
            <Copy aria-hidden /> {t("studio.add.copy")}
          </Button>
          <PresetMenu />
        </div>
      </section>

      {upload ? <UploadPanel onClose={() => setUpload(false)} /> : null}
      {upTray.length ? (
        <UploadReview
          items={upTray}
          meta={meta}
          onAccept={(items) => actions.accept(items)}
          onReject={onReject}
          onUpdate={onUpdate}
          onUndo={() => void store.getState().undo()}
          onRephrase={(text, key) => {
            store.getState().setNlText(text);
            onReject([key]);
            window.requestAnimationFrame(() => document.getElementById("studio-write")?.focus());
          }}
        />
      ) : null}
      <ReviewTray items={nlTray} meta={meta} onAccept={(items) => actions.accept(items)} onReject={onReject} onUpdate={onUpdate} />

      <PolicySwitches />

      <section aria-labelledby="rule-list-title" className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h3 id="rule-list-title" className="mr-auto text-base font-semibold">
            {t("studio.rules.listTitle")}
          </h3>
          <div className="relative w-full sm:w-56">
            <Search className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-label-2" aria-hidden />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("studio.rules.search")} aria-label={t("studio.rules.search")} className="pl-7" />
          </div>
          <NativeSelect className="w-auto min-w-36" aria-label={t("studio.rules.source")} value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">{t("studio.rules.anySource")}</option>
            {SOURCES.map((s) => (
              <option key={s} value={s}>
                {t(`studio.source.${s}`)}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect className="w-auto min-w-40" aria-label={t("studio.rule.mustOrTry")} value={hard} onChange={(e) => setHard(e.target.value)}>
            <option value="">{t("studio.rules.mustAndTry")}</option>
            <option value="hard">{t("studio.rule.must")}</option>
            <option value="soft">{t("studio.rule.try")}</option>
          </NativeSelect>
          <label className="flex items-center gap-1.5 text-sm">
            <input type="checkbox" checked={problemsOnly} onChange={(e) => setProblemsOnly(e.target.checked)} /> {t("studio.rules.problemsOnly")}
          </label>
          <NativeSelect className="w-auto min-w-48" aria-label={t("studio.rules.groupBy")} value={groupBy} onChange={(e) => setGroupBy(e.target.value as GroupBy)}>
            <option value="status">{t("studio.rules.groupByStatus")}</option>
            <option value="topic">{t("studio.rules.groupByTopic")}</option>
            <option value="source">{t("studio.rules.groupBySource")}</option>
          </NativeSelect>
        </div>

        {!rules ? (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-[var(--rule-card-min-h)] w-full" />
            ))}
          </div>
        ) : (
          groups.map((g) => (
            <RuleGroup key={g.key} id={g.key} label={g.label} count={g.items.length} collapsed={collapsed.has(g.key)} onToggle={() => toggleGroup(g.key)}>
              {g.items.length === 0 ? <p className="text-sm text-label-2">{t("studio.rules.groupEmpty")}</p> : null}
              <ul className="space-y-2">
                {g.items.map((e) => (
                  <li key={e.rule.id}>
                    <TermRuleCard eff={e} clash={clashFor(e.rule.id)} compact={compact} />
                  </li>
                ))}
              </ul>
            </RuleGroup>
          ))
        )}

        {placed.length ? (
          <RuleGroup id="pins" label={t("studio.rules.groupPins")} count={placed.length} collapsed={collapsed.has("pins")} onToggle={() => toggleGroup("pins")}>
            <ul className="space-y-2">
              {placed.map((p) => {
                const where = p.room_ids.length ? t("studio.pin.inRoom", { room: p.room_ids.map(sentence.roomCode).join(", ") }) : p.day ? t("studio.pin.atTime", { day: sentence.dayName(p.day), time: p.start_period ? PERIODS[p.start_period - 1]?.start ?? "" : "" }) : "";
                return (
                  <li key={p.event_id}>
                    <RuleCard
                      domId={`pin-${p.event_id}`}
                      tokens={null}
                      fallback={t("studio.pin.sentence", { cls: classLabel(p.event_id), where })}
                      source="ADMIN"
                      subLabel={t("studio.pin.fromClassList")}
                      hardness="hard"
                      weight={5}
                      readOnly
                      actions={
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            dispatch({ type: "unpin", eventId: p.event_id });
                            store.getState().record({ label: t("studio.pin.removed"), undo: () => dispatch({ type: "setPin", pin: p }), redo: () => dispatch({ type: "unpin", eventId: p.event_id }) });
                          }}
                        >
                          <Lock aria-hidden /> {t("studio.pin.remove")}
                        </Button>
                      }
                    />
                  </li>
                );
              })}
            </ul>
          </RuleGroup>
        ) : null}

        {changed.length ? (
          <RuleGroup id="overrides" label={t("studio.rules.groupOverrides")} count={changed.length} collapsed={collapsed.has("overrides")} onToggle={() => toggleGroup("overrides")}>
            <ul className="space-y-2">
              {changed.map((p) => {
                const ov = pinOverrides(p);
                const cls = classLabel(p.event_id);
                const lines = [
                  ov.unlock ? t("studio.pin.unlockedSentence", { cls }) : null,
                  ov.required_tags ? (ov.required_tags.length ? t("studio.pin.tagsSentence", { cls, tags: ov.required_tags.map(sentence.tagLabel).join(", ") }) : t("studio.pin.noTagsSentence", { cls })) : null,
                  ov.size != null ? t("studio.pin.seatsSentence", { cls, n: n(ov.size) }) : null,
                  ov.max_rooms != null ? t("studio.pin.roomsSentence", { cls, n: ov.max_rooms }) : null,
                ].filter((x): x is string => x !== null);
                return (
                  <li key={p.event_id}>
                    <RuleCard
                      domId={`override-${p.event_id}`}
                      testId="override-card"
                      tokens={null}
                      fallback={lines.join(" · ")}
                      source="ADMIN"
                      subLabel={t("studio.pin.fromFix")}
                      hardness="hard"
                      weight={5}
                      readOnly
                      hideHardness
                      actions={
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            dispatch({ type: "dropOverrides", eventId: p.event_id });
                            store.getState().record({ label: ov.unlock ? t("studio.pin.relocked") : t("studio.pin.overrideRemoved"), undo: () => dispatch({ type: "setPin", pin: p }), redo: () => dispatch({ type: "dropOverrides", eventId: p.event_id }) });
                          }}
                        >
                          {ov.unlock ? <Lock aria-hidden /> : null} {ov.unlock ? t("studio.pin.lockAgain") : t("studio.pin.undoOverride")}
                        </Button>
                      }
                    />
                  </li>
                );
              })}
            </ul>
          </RuleGroup>
        ) : null}

        <RuleGroup id="builtin" label={t("studio.rules.groupBuiltin")} count={rules?.builtins.length ?? 0} collapsed={collapsed.has("builtin")} onToggle={() => toggleGroup("builtin")}>
          <BuiltinRules />
        </RuleGroup>
      </section>

      <TemplateGallery
        open={galleryOpen}
        prefill={builderPrefill}
        onOpenChange={(v) => {
          setGallery(v);
          if (!v) onBuilderConsumed?.();
        }}
      />
      <CopyDialog open={copy} onOpenChange={setCopy} />
    </div>
  );
}

function RuleGroup({ id, label, count, collapsed, onToggle, children }: { id: string; label: string; count: number; collapsed: boolean; onToggle: () => void; children: ReactNode }) {
  return (
    <section aria-labelledby={`grp-${id}`} className="space-y-2" data-testid={`rule-group-${id}`}>
      <h4 id={`grp-${id}`}>
        <button type="button" onClick={onToggle} aria-expanded={!collapsed} className="flex w-full items-center gap-2 rounded-md py-1 text-sm font-semibold hover:text-primary pointer-coarse:min-h-11">
          <ChevronDown className={cn("size-4 transition-transform duration-[var(--dur-fast)]", collapsed && "-rotate-90")} aria-hidden />
          {label} <span className="font-normal text-label-2">({count})</span>
        </button>
      </h4>
      {collapsed ? null : children}
    </section>
  );
}
