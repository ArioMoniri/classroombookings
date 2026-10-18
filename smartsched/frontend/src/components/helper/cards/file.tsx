"use client";
/**
 * HB-23c (helper-file-router.md §5, §7, §8, §9, §10, §12): the router's answer in the helper's log.
 *
 * One file entry renders the person's bubble (the file chip, name and size from the browser's File) and then:
 * - **reading**: "Dosya okunuyor…" (`role=status`, shimmer only after 400 ms) + "Vazgeç";
 * - **detected / needs_planner / unknown**: the `file` card: icon + title (`tabIndex=-1`, focused when it arrives) +
 *   certainty word; evidence; term line; warnings (icon **and** text, `bad` → `role=alert`); **one primary** (the
 *   server's label, a short one under 640 px, the full one as the accessible name); ≤ 2 text buttons; "Bu dosya nedir?"
 *   folded (unknown: "Hangi dosyaları tanıyorum?" open, the primary opens the example files);
 * - **ambiguous**: the server's `choice` card as a `radiogroup` (↑ ↓ move, Enter / Space pick), no primary;
 * - **refused / error**: the message, then "Başka dosya seç" (error: "Tekrar dene" first);
 * - **several files**: one client card (no classify, no stage), "Kurulum sihirbazında aç" hands all the File objects over;
 * - **expired**: an inline line and "Dosyayı yeniden oku" (the same File again, else the picker).
 * A polite live line says "{dosya}: {tür}, {kesinlik}. {birincil düğme}" once per card. Motion (§9): the card's opacity +
 * y 6 → 0 on `springs.smooth` (reduced: 100 ms opacity), no stagger, no shake; the disclosure's content fades in after 60 ms.
 */
import { AlertTriangle, CalendarDays, ChevronDown, CircleAlert, Database, FileQuestion, FileSpreadsheet, Grid3x3, Info, ListChecks, Paperclip, Users, Warehouse, type LucideIcon } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { CLASSIFY_MAX_MB, EXAMPLE_EXT, exampleHref, type FileCard, type FileRoute, type FileWarning } from "@/lib/api/helper-files";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { springs, tween, useReduce } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { useFilePicker } from "../file-drop";
import { PICKABLE_KINDS, useFileRouter } from "../file-router";
import { useHelperStore, type FileEntry } from "../helper-store";
import type { ChoiceCard, ErrorCard, LimitCard, RefusalCard } from "../schema.gen";
import { activation } from "../use-helper-runner";
import { KIND_KEYS } from "../kind-labels";
import { pickText, useCardHost } from "./context";
import { formatSize } from "./file-size";

export { formatSize };

/* ------------------------------------------------------------------------------------------------ helpers */

const HINT_KEYS: Readonly<Record<string, MessageKey>> = {
  planning_list: "helper.file.chooser.hint.planning_list",
  exam_list: "helper.file.chooser.hint.exam_list",
  weekly_grid: "helper.file.chooser.hint.weekly_grid",
  room_master: "helper.file.chooser.hint.room_master",
  users_csv: "helper.file.chooser.hint.users_csv",
  crbs_dump: "helper.file.chooser.hint.crbs_dump",
  onboarding: "helper.file.chooser.hint.onboarding",
};

const KIND_ICON: Readonly<Record<string, LucideIcon>> = {
  planning_list: FileSpreadsheet,
  exam_list: ListChecks,
  weekly_grid: Grid3x3,
  timetable_other: Grid3x3,
  room_master: Warehouse,
  room_list: Warehouse,
  crbs_dump: Database,
  users_csv: Users,
  staff_list: Users,
  calendar_ics: CalendarDays,
  holidays: CalendarDays,
};

function useKindLabel() {
  const { t } = useI18n();
  return (kind: string | null | undefined): string | null => (kind && KIND_KEYS[kind] ? t(KIND_KEYS[kind]) : null);
}

const CERTAINTY_KEY = { sure: "helper.file.sure", likely: "helper.file.likely", unsure: "helper.file.unsure" } as const satisfies Record<string, MessageKey>;
const CERTAINTY_DOT = { sure: "bg-status-feasible-fg", likely: "bg-tint", unsure: "bg-status-warning-fg" } as const;

function CertaintyBadge({ certainty }: { certainty: NonNullable<FileCard["certainty"]> }) {
  const { t } = useI18n();
  return (
    <span className="inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full bg-fill-2 px-2 type-caption text-label-1" data-testid="helper-file-certainty">
      <span aria-hidden className={cn("size-2 rounded-full forced-colors:bg-[CanvasText]", CERTAINTY_DOT[certainty])} />
      {t(CERTAINTY_KEY[certainty])}
    </span>
  );
}

function WarningRow({ w }: { w: FileWarning }) {
  const { locale } = useI18n();
  const Icon = w.status === "info" ? Info : w.status === "bad" ? CircleAlert : AlertTriangle;
  return (
    <li
      className="flex items-start gap-2 type-footnote text-label-1"
      data-testid={`helper-file-warning-${w.code}`}
      data-status={w.status}
      // a `bad` warning is said once (it is in the card, never colour alone)
      role={w.status === "bad" ? "alert" : undefined}
    >
      <Icon aria-hidden className={cn("mt-0.5 size-4 shrink-0", w.status === "info" && "text-label-2", w.status === "warn" && "text-status-warning-fg", w.status === "bad" && "text-status-infeasible-fg")} />
      <span className="min-w-0">{pickText(w.message, locale)}</span>
    </li>
  );
}

/**
 * §8.2: on phones a column line shows ≤ 3 labels, then "+n" ("Sütunlar: Ders Kodu, Şube, Dersin Günü +3 → Planlama
 * listesi"); a server "+n" is added in. Null when the line is not a label list or is short already.
 */
export function splitEvidence(line: string): string | null {
  const m = /^([^:→]+:\s)(.+?)(\s→\s.+)$/.exec(line);
  if (!m) return null;
  const labels = m[2]!.split(", ").map((x) => x.trim()).filter(Boolean);
  let extra = 0;
  const last = labels[labels.length - 1];
  if (last && /^\+\d+$/.test(last)) {
    extra = Number(last.slice(1));
    labels.pop();
  }
  if (labels.length <= 3) return null;
  return `${m[1]}${labels.slice(0, 3).join(", ")} +${labels.length - 3 + extra}${m[3]}`;
}

function EvidenceLine({ line }: { line: string }) {
  const short = splitEvidence(line);
  if (!short) {
    return (
      <p className="type-callout text-label-2" data-testid="helper-file-evidence">
        {line}
      </p>
    );
  }
  // the full line stays for wider screens and for screen readers; the short one is visual, phones only
  return (
    <p className="type-callout text-label-2" data-testid="helper-file-evidence">
      <span aria-hidden="true" className="sm:hidden">
        {short}
      </span>
      <span className="max-sm:sr-only">{line}</span>
    </p>
  );
}

/**
 * The card's enter (§9): y 6 → 0 once on `springs.smooth`, opacity on `tween.fadeIn` (a spring on opacity becomes a
 * 400 ms WAAPI animation, over the 300 ms ceiling of the motion audit); reduced motion 100 ms opacity.
 */
const ENTER = { ...springs.smooth, opacity: tween.fadeIn };
function Enter({ children, k }: { children: ReactNode; k: string | number }) {
  const reduce = useReduce();
  return (
    <motion.div key={k} initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }} animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0 }} transition={reduce ? tween.reduced : ENTER} className="min-w-0">
      {children}
    </motion.div>
  );
}

/** the card well (helper.md §12: `--fill-3`, hairline, radius-md, 16 px pad, 12 px gap), title focusable */
function Frame({ testId, titleId, title, icon: Icon, badge, children, tintId }: { testId: string; titleId: string; title: ReactNode; icon?: LucideIcon; badge?: ReactNode; children: ReactNode; tintId?: string | null }) {
  const reduce = useReduce();
  return (
    <div role="group" aria-labelledby={titleId} data-testid={testId} className="helper-card flex min-w-0 flex-col gap-3 rounded-(--radius-md) bg-fill-3 p-4 edge-hairline forced-colors:border forced-colors:border-[CanvasText]">
      <div className="relative flex min-w-0 flex-wrap items-start gap-x-3 gap-y-1">
        {/* §9 "Chooser pick → new card": the picked row's tint lands here (shared layoutId; instant when reduced) */}
        {tintId ? <motion.span layoutId={tintId} data-pick-tint="" aria-hidden className="pointer-events-none absolute -inset-1.5 rounded-lg bg-tint-soft" transition={reduce ? { duration: 0 } : springs.glassMorph} /> : null}
        {Icon ? <Icon aria-hidden className="relative mt-0.5 size-5 shrink-0 stroke-[1.75] text-label-2" /> : null}
        <p id={titleId} tabIndex={-1} data-focus-target="" className="relative min-w-0 flex-1 rounded-sm type-headline text-label-1 outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)">
          {title}
        </p>
        {badge}
      </div>
      {children}
    </div>
  );
}

/** The one primary: 40 px desktop / 48 px full width on phones; the short label under 640 px, the full one as its name. */
function PrimaryButton({ label, short, onClick, testId = "helper-file-primary", busy }: { label: string; short?: string | null; onClick: (e: React.MouseEvent<HTMLButtonElement>) => void; testId?: string; busy?: boolean }) {
  return (
    <Button size="md" aria-label={short && short !== label ? label : undefined} onClick={onClick} disabled={busy} className="h-auto min-h-10 w-full py-2 text-center whitespace-normal max-sm:min-h-12" data-testid={testId}>
      {short && short !== label ? (
        <>
          <span className="sm:hidden" data-testid="helper-file-primary-short">{short}</span>
          <span className="max-sm:hidden">{label}</span>
        </>
      ) : (
        label
      )}
    </Button>
  );
}

function TextButton({ children, onClick, testId, ...rest }: { children: ReactNode; onClick: () => void; testId: string } & Record<`aria-${string}`, string | boolean | undefined>) {
  return (
    <Button variant="ghost" size="md" onClick={onClick} data-testid={testId} className="h-auto min-h-11 max-w-full min-w-0 shrink px-3 py-2 text-left whitespace-normal max-sm:w-full" {...rest}>
      {children}
    </Button>
  );
}

/** "Bu dosya nedir?" (folded) / "Hangi dosyaları tanıyorum?" (open): height in place, the text fades in after 60 ms. */
function Disclosure({ label, lines, defaultOpen = false }: { label: string; lines: string[]; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  const reduce = useReduce();
  if (!lines.length) return null;
  return (
    <div className="flex flex-col">
      <Button variant="ghost" size="md" aria-expanded={open} aria-controls={id} onClick={() => setOpen((v) => !v)} data-testid="helper-file-what" className="min-h-11 justify-start gap-1.5 self-start px-2">
        <ChevronDown aria-hidden className={cn("transition-transform duration-(--dur-fast) motion-reduce:transition-none", !open && "-rotate-90")} />
        {label}
      </Button>
      {open ? (
        <motion.div id={id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={reduce ? { duration: 0 } : { ...tween.fadeIn, delay: 0.06 }} className="flex flex-col gap-1 px-2 pt-1" data-testid="helper-file-explain">
          {lines.map((l, i) => (
            <p key={i} className="type-callout text-label-2">
              {l}
            </p>
          ))}
        </motion.div>
      ) : null}
    </div>
  );
}

/** "Örnek dosyaları gör": one line per kind with an "İndir" text button (44 px), header-only templates (§6.6). */
function Examples({ kinds }: { kinds: string[] }) {
  const { t } = useI18n();
  const label = useKindLabel();
  const rows = kinds.filter((k) => label(k) && EXAMPLE_EXT[k]);
  return (
    <ul className="flex flex-col" data-testid="helper-file-examples" aria-label={t("helper.file.examplesTitle")}>
      {rows.map((k) => (
        <li key={k} className="flex min-h-11 items-center justify-between gap-3 [&:not(:last-child)]:hairline-b">
          <span className="min-w-0 type-callout text-label-1">{label(k)}</span>
          <Button
            variant="ghost"
            size="md"
            className="min-h-11"
            nativeButton={false}
            render={<a href={exampleHref(k, EXAMPLE_EXT[k])} download aria-label={t("helper.file.downloadName", { kind: label(k) ?? "" })} data-testid={`helper-file-example-${k}`} />}
          >
            {t("helper.file.download")}
          </Button>
        </li>
      ))}
    </ul>
  );
}

/** A radiogroup of rows (the chooser and "Başka bir tür seç"): ↑ ↓ move, Enter / Space / click pick. */
function KindRadios({ label, options, onPick, testPrefix = "helper-file-choice-", picked, tintId }: { label: string; options: { value: string; label: string; hint?: string | null }[]; onPick: (v: string) => void; testPrefix?: string; picked?: string | null; tintId?: string }) {
  const reduce = useReduce();
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLElement | null)[]>([]);
  const move = (i: number) => {
    const n = (i + options.length) % options.length;
    setActive(n);
    refs.current[n]?.focus();
  };
  const onKey = (e: KeyboardEvent<HTMLElement>, i: number, v: string) => {
    if (e.key === "ArrowDown" || e.key === "ArrowRight") {
      e.preventDefault();
      move(i + 1);
    } else if (e.key === "ArrowUp" || e.key === "ArrowLeft") {
      e.preventDefault();
      move(i - 1);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onPick(v);
    }
  };
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-col gap-1" data-testid="helper-file-radios">
      {options.map((o, i) => (
        <Button
          key={o.value}
          ref={(el: HTMLElement | null) => {
            refs.current[i] = el;
          }}
          role="radio"
          aria-checked={picked === o.value}
          tabIndex={i === active ? 0 : -1}
          variant="secondary"
          shape="rect"
          onClick={() => onPick(o.value)}
          onKeyDown={(e: KeyboardEvent<HTMLElement>) => onKey(e, i, o.value)}
          onFocus={() => setActive(i)}
          className="h-auto min-h-11 w-full justify-start px-3 py-2 text-left whitespace-normal"
          data-testid={`${testPrefix}${o.value}`}
        >
          {picked === o.value && tintId ? <motion.span layoutId={tintId} data-pick-tint="" aria-hidden className="pointer-events-none absolute inset-0 rounded-lg bg-tint-soft" transition={reduce ? { duration: 0 } : springs.glassMorph} /> : null}
          <span className="relative flex min-w-0 flex-col">
            <span className="font-medium text-label-1">{o.label}</span>
            {o.hint ? <span className="type-footnote text-label-2">{o.hint}</span> : null}
          </span>
        </Button>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------------------------------------- states */

interface StateProps {
  entry: FileEntry;
  titleId: string;
  reread: () => void;
  anotherFile: () => void;
}

/** KVKK N3: what happens to the file: kept encrypted ≤ 10 min while a stage lives, otherwise read only and not kept. */
function PrivacyLine({ staged }: { staged: boolean }) {
  const { t } = useI18n();
  return (
    <p className="type-caption text-label-2" data-testid="helper-file-privacy">
      {t(staged ? "helper.file.privacyRead" : "helper.file.privacyNotKept")}
    </p>
  );
}

function ExpiredLine({ reread }: { reread: () => void }) {
  const { t } = useI18n();
  return (
    <div className="flex flex-col gap-2" data-testid="helper-file-expired">
      <p className="type-footnote text-label-2">{t("helper.file.expired")}</p>
      <PrimaryButton label={t("helper.file.reread")} onClick={reread} testId="helper-file-reread" />
    </div>
  );
}

function FileCardView({ entry, card, titleId, reread }: StateProps & { card: FileCard }) {
  const { t, locale } = useI18n();
  const host = useCardHost();
  const router = useFileRouter();
  const label = useKindLabel();
  const [examples, setExamples] = useState(false);
  const kind = label(card.kind) ?? (card.kind_label ? pickText(card.kind_label, locale) : null);
  const title = card.title
    ? pickText(card.title, locale)
    : card.state === "unknown"
      ? t("helper.file.unknown.text", { format: card.format.toUpperCase() })
      : card.state === "needs_planner"
        ? t(card.primary ? "helper.file.needsPlanner.text" : "helper.file.needsPlanner.none", { kind: kind ?? "" })
        : t(card.certainty === "sure" ? "helper.file.title" : "helper.file.titleLikely", { kind: kind ?? "" });
  const evidence = card.evidence[locale] ?? card.evidence.tr ?? [];
  const explain = card.explain[locale] ?? card.explain.tr ?? [];
  const token = entry.stage?.upload_token ?? null;
  const go = (route: FileRoute) => (e?: React.MouseEvent<HTMLButtonElement>) => {
    // a script's synthetic click is not the person's consent (helper.md §4.1 rule 4)
    if (e && !activation.trusted(e)) return;
    void router.primary(entry.key, route, host.go, card.kind ?? null);
  };
  const canPickOther = card.state === "detected" && card.format !== "mixed" && !!token;
  const secondary = card.secondary.slice(0, canPickOther ? 1 : 2);
  const Icon = card.state === "unknown" ? FileQuestion : card.format === "mixed" ? Paperclip : (card.kind && KIND_ICON[card.kind]) || FileSpreadsheet;

  return (
    <Frame testId={`helper-card-file-${card.state}`} titleId={titleId} title={title} icon={Icon} tintId={entry.picked ? `file-tint-${entry.key}` : null} badge={card.state === "detected" && card.certainty ? <CertaintyBadge certainty={card.certainty} /> : null}>
      {evidence.length ? (
        <div className="flex flex-col gap-1">
          {evidence.slice(0, 4).map((l, i) => (
            <EvidenceLine key={i} line={l} />
          ))}
          {card.term ? (
            <p className="type-footnote text-label-2" data-testid="helper-file-term">
              {t(card.term.source === "sheet_title" ? "helper.file.termLine.sheet_title" : "helper.file.termLine.file_name", { term: pickText(card.term.name, locale) })}
            </p>
          ) : null}
        </div>
      ) : card.term ? (
        <p className="type-footnote text-label-2" data-testid="helper-file-term">
          {t(card.term.source === "sheet_title" ? "helper.file.termLine.sheet_title" : "helper.file.termLine.file_name", { term: pickText(card.term.name, locale) })}
        </p>
      ) : null}
      {card.warnings.length ? (
        <ul className="mt-1 flex flex-col gap-1.5" data-testid="helper-file-warnings">
          {card.warnings.slice(0, 4).map((w) => (
            <WarningRow key={w.code} w={w} />
          ))}
        </ul>
      ) : null}

      {entry.expired ? (
        <ExpiredLine reread={reread} />
      ) : (
        <div className="mt-1 flex flex-col gap-2">
          {card.state === "unknown" ? (
            <>
              {card.examples.length ? (
                <PrimaryButton label={t("helper.file.examples")} onClick={() => setExamples((v) => !v)} testId="helper-file-primary" />
              ) : null}
              {examples ? <Examples kinds={card.examples} /> : null}
            </>
          ) : card.primary ? (
            <PrimaryButton label={pickText(card.primary.label, locale)} short={card.primary.label_short ? pickText(card.primary.label_short, locale) : null} onClick={go(card.primary)} />
          ) : null}
          {canPickOther || secondary.length ? (
            <div className="flex flex-wrap gap-x-1 gap-y-1 max-sm:flex-col">
              {canPickOther ? (
                <TextButton onClick={() => router.showKinds(entry.key)} testId="helper-file-other">
                  {t("helper.file.other")}
                </TextButton>
              ) : null}
              {secondary.map((r) => (
                <TextButton key={`${r.feature_id}:${JSON.stringify(r.params)}`} onClick={() => go(r)()} testId={r.feature_id === "onboarding" ? "helper-file-onboarding" : `helper-file-secondary-${r.feature_id}`}>
                  {pickText(r.label, locale)}
                </TextButton>
              ))}
            </div>
          ) : null}
        </div>
      )}
      {entry.notice ? <p className="type-footnote text-status-infeasible-fg" role="alert">{pickText(entry.notice, locale)}</p> : null}
      <Disclosure
        label={t(card.state === "unknown" ? "helper.file.whatKnown" : "helper.file.what")}
        lines={card.state === "unknown" ? (explain.length ? explain : [t("helper.file.unknown.list")]) : explain}
        defaultOpen={card.state === "unknown"}
      />
      {card.ai_sorted ? <p className="type-caption text-label-2">{t("helper.file.aiSorted")}</p> : null}
      <PrivacyLine staged={!!entry.stage} />
    </Frame>
  );
}

function ChooserView({ entry, card, titleId, reread }: StateProps & { card: ChoiceCard }) {
  const { t, locale } = useI18n();
  const router = useFileRouter();
  const rows = card.options.filter((o) => String(o.value) !== "onboarding").map((o) => ({ value: String(o.value), label: pickText(o.label, locale), hint: o.hint ? pickText(o.hint, locale) : null }));
  const wizard = card.options.find((o) => String(o.value) === "onboarding");
  return (
    <Frame testId="helper-card-file-ambiguous" titleId={titleId} title={pickText(card.question, locale)} icon={FileQuestion}>
      {entry.expired ? (
        <ExpiredLine reread={reread} />
      ) : (
        <>
          <KindRadios label={pickText(card.question, locale)} options={rows} onPick={(v) => void router.pick(entry.key, v)} picked={entry.picked} tintId={`file-tint-${entry.key}`} />
          {wizard ? (
            <TextButton onClick={() => void router.pick(entry.key, "onboarding")} testId="helper-file-onboarding">
              {t("helper.file.openWizard")}
            </TextButton>
          ) : null}
        </>
      )}
      {entry.notice ? <p className="type-footnote text-status-infeasible-fg" role="alert">{pickText(entry.notice, locale)}</p> : null}
      <PrivacyLine staged={!!entry.stage} />
    </Frame>
  );
}

function OtherKindView({ entry, card, titleId }: StateProps & { card: FileCard | ChoiceCard | RefusalCard | ErrorCard | LimitCard }) {
  const { t } = useI18n();
  const host = useCardHost();
  const router = useFileRouter();
  const label = useKindLabel();
  const current = card.type === "file" ? card.kind : null;
  const rows = PICKABLE_KINDS.filter((k) => k.kind !== current && host.can(k.perms)).map((k) => ({ value: k.kind, label: label(k.kind) ?? "", hint: HINT_KEYS[k.kind] ? t(HINT_KEYS[k.kind]) : null }));
  return (
    <Frame testId="helper-card-file-pick" titleId={titleId} title={t("helper.file.chooser.otherQ")} icon={FileQuestion}>
      <KindRadios label={t("helper.file.chooser.otherQ")} options={rows} onPick={(v) => void router.pick(entry.key, v)} picked={entry.picked} tintId={`file-tint-${entry.key}`} />
      <TextButton onClick={() => router.hideKinds(entry.key)} testId="helper-file-other-back">
        {t("helper.file.otherBack")}
      </TextButton>
    </Frame>
  );
}

function StatusCardView({ entry, card, titleId, anotherFile }: StateProps & { card: RefusalCard | ErrorCard | LimitCard }) {
  const { t, locale } = useI18n();
  const router = useFileRouter();
  const retryable = card.type === "error";
  const retry = () => {
    if (!router.retry(entry.key)) anotherFile();
  };
  return (
    <div role="group" aria-labelledby={titleId} className="flex flex-col gap-2" data-testid={`helper-card-file-${card.type === "refusal" || card.type === "limit" ? "refused" : "error"}`} data-code={card.code}>
      <Alert tone={card.type === "error" ? "error" : "info"} live="off">
        <span id={titleId} tabIndex={-1} data-focus-target="" className="rounded-sm outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)">
          {pickText(card.message, locale)}
        </span>
      </Alert>
      <div className="flex flex-wrap gap-2 max-sm:flex-col">
        {retryable ? <PrimaryButton label={t("helper.file.retry")} onClick={retry} testId="helper-file-retry" /> : null}
        {retryable ? (
          <TextButton onClick={anotherFile} testId="helper-file-another">
            {t("helper.file.another")}
          </TextButton>
        ) : (
          <PrimaryButton label={t("helper.file.another")} onClick={anotherFile} testId="helper-file-another" />
        )}
      </div>
    </div>
  );
}

function LocalView({ entry, titleId, anotherFile, view }: StateProps & { view: Extract<NonNullable<FileEntry["view"]>, { kind: "local" }> }) {
  const { t, locale } = useI18n();
  const router = useFileRouter();
  const message =
    view.code === "file_too_large"
      ? t("helper.file.refused.size", { size: formatSize(view.size ?? 0, locale), mb: CLASSIFY_MAX_MB })
      : view.code === "file_empty"
        ? t("helper.file.refused.empty")
        : t("helper.file.error");
  const failed = view.code === "file_read_failed";
  return (
    <div role="group" aria-labelledby={titleId} className="flex flex-col gap-2" data-testid={`helper-card-file-${failed ? "error" : "refused"}`} data-code={view.code}>
      <Alert tone={failed ? "error" : "info"} live="off">
        <span id={titleId} tabIndex={-1} data-focus-target="" className="rounded-sm outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)">
          {message}
        </span>
      </Alert>
      <div className="flex flex-wrap gap-2 max-sm:flex-col">
        {failed ? <PrimaryButton label={t("helper.file.retry")} onClick={() => (router.retry(entry.key) ? undefined : anotherFile())} testId="helper-file-retry" /> : null}
        {failed ? (
          <TextButton onClick={anotherFile} testId="helper-file-another">
            {t("helper.file.another")}
          </TextButton>
        ) : (
          <PrimaryButton label={t("helper.file.another")} onClick={anotherFile} testId="helper-file-another" />
        )}
      </div>
    </div>
  );
}

function ManyView({ entry, n, titleId }: StateProps & { n: number }) {
  const { t } = useI18n();
  const host = useCardHost();
  const router = useFileRouter();
  return (
    <Frame testId="helper-card-file-many" titleId={titleId} title={t("helper.file.many", { n })} icon={Paperclip}>
      <PrimaryButton
        label={t("helper.file.openWizard")}
        onClick={(e) => {
          if (!activation.trusted(e)) return;
          void router.primary(entry.key, { feature_id: "onboarding", params: {}, carries_file: true }, host.go, null);
        }}
      />
      <p className="type-caption text-label-2">{t("helper.file.privacyMany")}</p>
    </Frame>
  );
}

/* -------------------------------------------------------------------------------------------- entry view */

function FileChip({ name, size }: { name: string; size: number }) {
  const { t, locale } = useI18n();
  return (
    <span className="inline-flex h-8 max-w-full min-w-0 items-center gap-2 rounded-full bg-fill-2 px-3 text-label-1 max-sm:h-11" data-testid="helper-file-chip" title={name}>
      <FileSpreadsheet aria-hidden className="size-4 shrink-0" />
      <span className="min-w-0 truncate type-callout" style={{ maxWidth: "28ch" }}>
        {name}
      </span>
      <span className="shrink-0 type-caption text-label-2" aria-label={t("helper.file.fileChip", { name, size: formatSize(size, locale) })}>
        {formatSize(size, locale)}
      </span>
    </span>
  );
}

/** "Dosya okunuyor…": a real wait; the shimmer label only after 400 ms (§9), with "Vazgeç". */
function Reading({ onCancel }: { onCancel: () => void }) {
  const { t } = useI18n();
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const id = window.setTimeout(() => setSlow(true), 400);
    return () => window.clearTimeout(id);
  }, []);
  return (
    <div className="flex items-center gap-2" data-testid="helper-file-reading">
      <p role="status" className={cn("type-callout text-label-2", slow && "helper-shimmer")}>
        {t("helper.file.reading")}
      </p>
      <Button variant="ghost" size="md" className="min-h-11" onClick={onCancel} data-testid="helper-file-cancel">
        {t("helper.file.cancel")}
      </Button>
    </div>
  );
}

/** the live line said once per card (§10): "{dosya}: {tür}, {kesinlik}. {birincil düğme}" */
function useLiveLine(entry: FileEntry): string {
  const { t, locale } = useI18n();
  const label = useKindLabel();
  const name = entry.files.length > 1 ? t("helper.file.many", { n: entry.files.length }) : (entry.files[0]?.name ?? "");
  const v = entry.view;
  if (!v || entry.phase !== "shown") return "";
  if (v.kind === "card" && v.card.type === "file") {
    const c = v.card;
    if (c.state === "detected" && c.certainty) {
      const kind = label(c.kind) ?? (c.kind_label ? pickText(c.kind_label, locale) : "");
      return t("helper.file.live", { file: name, kind, certainty: t(CERTAINTY_KEY[c.certainty]), button: c.primary ? pickText(c.primary.label, locale) : "" });
    }
    return t("helper.file.liveOther", { file: name, text: c.title ? pickText(c.title, locale) : t("helper.file.unknown.text", { format: c.format.toUpperCase() }) });
  }
  if (v.kind === "card" && v.card.type === "choice") return t("helper.file.liveOther", { file: name, text: pickText(v.card.question, locale) });
  if (v.kind === "card" && (v.card.type === "refusal" || v.card.type === "error" || v.card.type === "limit")) return t("helper.file.liveOther", { file: name, text: pickText(v.card.message, locale) });
  if (v.kind === "many") return t("helper.file.many", { n: v.n });
  if (v.kind === "local") return t("helper.file.liveOther", { file: name, text: v.code === "file_too_large" ? t("helper.file.refused.size", { size: formatSize(v.size ?? 0, locale), mb: CLASSIFY_MAX_MB }) : t("helper.file.error") });
  return "";
}

export function FileEntryView({ entry }: { entry: FileEntry }) {
  const { t } = useI18n();
  const router = useFileRouter();
  const titleId = useId();
  const label = useKindLabel();
  const picker = useFilePicker((list) => router.attach(list), { testId: "helper-file-reinput" });
  const live = useLiveLine(entry);
  const [said, setSaid] = useState<{ seq: number; text: string }>({ seq: 0, text: "" });
  const initialKey = useRef(`${entry.phase}:${entry.view?.kind ?? ""}:${entry.expired ? 1 : 0}`);
  if (entry.seq !== said.seq && entry.phase === "shown") setSaid({ seq: entry.seq, text: live });

  // focus the card title when a new card arrives (the reader hears what the file is before the button)
  useEffect(() => {
    if (!entry.seq || entry.phase !== "shown") return;
    const id = requestAnimationFrame(() => document.getElementById(titleId)?.focus({ preventScroll: false }));
    return () => cancelAnimationFrame(id);
  }, [entry.seq, entry.phase, titleId]);

  // HB-23d DS-01…DS-03: a view change that removes the focused control ("Başka bir tür seç", "Vazgeç", an expired
  // hand-over) moves the focus to what replaced it, never leaving it on <body>
  const focusKey = `${entry.phase}:${entry.view?.kind ?? ""}:${entry.expired ? 1 : 0}`;
  const [seenKey, setSeenKey] = useState(focusKey);
  if (seenKey !== focusKey) setSeenKey(focusKey);
  useEffect(() => {
    if (seenKey === initialKey.current) return;
    const id = requestAnimationFrame(() => {
      const a = document.activeElement;
      if (a && a !== document.body) return;
      const root = document.querySelector(`[data-file-entry="${entry.key}"]`);
      const target = entry.expired
        ? root?.querySelector<HTMLElement>('[data-testid="helper-file-reread"]')
        : entry.phase === "cancelled"
          ? root?.querySelector<HTMLElement>('[data-testid="helper-file-cancelled"]')
          : entry.view?.kind === "pick"
            ? root?.querySelector<HTMLElement>('[role="radio"][tabindex="0"]')
            : document.getElementById(titleId);
      target?.focus();
    });
    return () => cancelAnimationFrame(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs when the view changes
  }, [seenKey]);

  // the token's 10 minutes: the button turns into "Dosyayı yeniden oku"
  const expiresAt = entry.stage ? Date.parse(entry.stage.expires_at) : NaN;
  useEffect(() => {
    if (!Number.isFinite(expiresAt) || entry.expired) return;
    const id = window.setTimeout(() => markExpired(entry.key), Math.max(0, expiresAt - Date.now()));
    return () => window.clearTimeout(id);
  }, [expiresAt, entry.expired, entry.key]);

  const reread = () => {
    if (!router.retry(entry.key)) picker.open();
  };
  const props: StateProps = { entry, titleId, reread, anotherFile: picker.open };
  const v = entry.view;
  const kindOf = v?.kind === "card" && v.card.type === "file" ? label(v.card.kind) : null;

  return (
    <div className="flex min-w-0 flex-col gap-3" data-testid="helper-file-entry" data-phase={entry.phase} data-file-entry={entry.key}>
      <div className="ml-auto flex max-w-[85%] flex-wrap justify-end gap-1.5" data-testid="helper-user-file">
        {entry.files.slice(0, 3).map((f) => (
          <FileChip key={`${f.name}:${f.size}`} name={f.name} size={f.size} />
        ))}
        {entry.files.length > 3 ? <span className="self-center type-caption text-label-2">+{entry.files.length - 3}</span> : null}
      </div>
      {picker.input}
      {entry.phase === "reading" ? <Reading onCancel={() => router.cancel(entry.key)} /> : null}
      {entry.phase === "cancelled" ? <p tabIndex={-1} className="rounded-sm type-footnote text-label-2 outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)" data-testid="helper-file-cancelled">{t("helper.file.cancelled")}</p> : null}
      {entry.phase === "collapsed" || entry.phase === "handed" ? (
        <p className="type-footnote text-label-2" data-testid={`helper-file-${entry.phase}`}>
          {kindOf ? t(entry.phase === "handed" ? "helper.file.opened" : "helper.file.collapsed", { kind: kindOf }) : t("helper.file.collapsedPlain")}
        </p>
      ) : null}
      {entry.phase === "shown" && v ? (
        <Enter k={entry.seq}>
          {v.kind === "many" ? (
            <ManyView {...props} n={v.n} />
          ) : v.kind === "local" ? (
            <LocalView {...props} view={v} />
          ) : v.kind === "pick" ? (
            <OtherKindView {...props} card={v.card} />
          ) : v.card.type === "file" ? (
            <FileCardView {...props} card={v.card} />
          ) : v.card.type === "choice" ? (
            <ChooserView {...props} card={v.card} />
          ) : (
            <StatusCardView {...props} card={v.card} />
          )}
        </Enter>
      ) : null}
      <p className="sr-only" role="status" data-testid="helper-file-live">
        {said.text}
      </p>
    </div>
  );
}

/** the stage's 10 minutes are over: the server already deleted it (sweeper), the card offers a re-read */
function markExpired(key: string) {
  useHelperStore.getState().updateFile(key, { expired: true, stage: null });
}
