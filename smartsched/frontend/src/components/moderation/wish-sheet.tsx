"use client";
/**
 * "Tercih ekle" (P19-T2, F-05 S03; owner: academicians add their own wishes, coordinators moderate them, nothing
 * is ever applied by itself): a side sheet on desktop and a bottom sheet on phones. Pick the classes you teach,
 * the kind (oda / bina / zaman aralığı) and its fields, an optional note; the summary the coordinator will read
 * is shown before sending, every server refusal reads as TR/EN text, and `fixed_by_department` explains that the
 * department form fixes the time. `POST /moderation/me/preferences` stores it switched off until a coordinator
 * accepts it (ranked below the department's request).
 */
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Search } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Chip } from "@/components/ui/chip";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { crbs } from "@/lib/api/crbs";
import type { Matching } from "@/lib/api/moderation";
import { useSubmitWish, wishError, WISH_KINDS, type SubmitOut, type WishKind } from "@/lib/api/teacher-preferences";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { PERIODS, dayName } from "@/lib/time";
import { cn } from "@/lib/utils";
import { pairText, requestedText } from "./moderation-model";
import { usePhone } from "./use-media";
import { MAX_ROOMS, NOTE_MAX, buildingCode, buildingOf, buildingsOf, roomCode, emptyWish, fixedClasses, formIssues, isKnownError, wishBody, wishSentence, type FormIssue, type WishForm } from "./wish-model";

/** 44 px rows and controls on touch (MOBILE.md M-02) */
const ROW = "flex min-h-11 items-start gap-3 rounded-md px-2 py-2 md:min-h-9 md:py-1.5 hover:bg-fill-3";
const WEEKDAYS = [1, 2, 3, 4, 5, 6] as const;

export function WishSheet({ open, onOpenChange, classes, initial }: { open: boolean; onOpenChange: (v: boolean) => void; classes: readonly Matching[]; initial: readonly number[] }) {
  const phone = usePhone();
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side={phone ? "bottom" : "right"} className="gap-4 overflow-y-auto p-5 sm:max-w-lg md:p-6" data-testid="wish-sheet" data-variant={phone ? "sheet" : "side"}>
        {/* a fresh form each time the sheet opens on a row (the row's class preselected) */}
        {open ? <WishFormBody key={initial.join(",")} classes={classes} initial={initial} onClose={() => onOpenChange(false)} /> : null}
      </SheetContent>
    </Sheet>
  );
}

function WishFormBody({ classes, initial, onClose }: { classes: readonly Matching[]; initial: readonly number[]; onClose: () => void }) {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const [form, setForm] = useState<WishForm>(() => emptyWish(initial));
  const [roomQ, setRoomQ] = useState("");
  const [tried, setTried] = useState(false);
  const [serverError, setServerError] = useState<{ code: string; text: string; detail: string | null } | null>(null);
  const [sent, setSent] = useState<SubmitOut | null>(null);
  const submit = useSubmitWish();
  const ids = useId();
  // the rooms this user may see (bookings visibility; the planning room list needs planning.view)
  const rooms = useQuery({ queryKey: ["crbs", "booking-rooms"], queryFn: () => crbs.bookings.rooms(), retry: false, staleTime: 60_000 });
  const roomList = useMemo(() => [...(rooms.data ?? [])].sort((a, b) => a.code.localeCompare(b.code, "tr", { numeric: true })), [rooms.data]);
  const byId = useMemo(() => new Map(roomList.map((r) => [r.id, r])), [roomList]);
  // the buildings of the visible rooms plus those of the classes' own rooms (asked, definitive, assigned)
  const buildings = useMemo(() => {
    const own = classes.flatMap((m) => [...m.requested.rooms, ...m.definitive.rooms, ...(m.assigned?.rooms ?? [])]).map((code) => ({ code }));
    return buildingsOf([...roomList, ...own]);
  }, [roomList, classes]);
  const [buildingQ, setBuildingQ] = useState("");

  const set = (patch: Partial<WishForm>) => {
    setServerError(null);
    setForm((f) => ({ ...f, ...patch }));
  };
  const selected = classes.filter((m) => form.requestIds.includes(m.request_id));
  const labels = [...selected].sort((a, b) => a.request_id - b.request_id).map((m) => m.label);
  const fixed = fixedClasses(classes, form.requestIds);
  const allFixed = selected.length > 0 && fixed.length === selected.length;
  const issues = formIssues(form);
  const roomNames = [...form.roomIds.map((id) => byId.get(id)?.name || byId.get(id)?.code || `#${id}`), ...form.roomCodes];
  const roomCount = form.roomIds.length + form.roomCodes.length;
  const needle = roomQ.trim().toLocaleLowerCase("tr").replace(/\s+/g, "");
  const roomHits = roomList.filter((r) => !needle || `${r.code}${r.name}`.toLocaleLowerCase("tr").replace(/\s+/g, "").includes(needle)).slice(0, 40);
  // a code typed as the lists write it, for rooms this account cannot list (the server checks it: unknown_room)
  const typed = roomCode(roomQ);
  const typedListed = typed ? roomList.find((r) => r.code.toLocaleUpperCase("tr").replace(/\s+/g, " ") === typed) : undefined;
  const canAddTyped = !!typed && !typedListed && !form.roomCodes.includes(typed) && roomCount < MAX_ROOMS;
  const typedBuilding = buildingCode(buildingQ);

  const issueText = (i: FormIssue) => t(`moderation.wish.issue.${i}` as MessageKey, { n: i === "tooManyRooms" ? MAX_ROOMS : NOTE_MAX });

  const send = async () => {
    setTried(true);
    setServerError(null);
    if (issues.length) return;
    try {
      const out = await submit.mutateAsync(wishBody(form));
      setSent(out);
      toast.success(t("moderation.wish.sentToast"));
    } catch (e) {
      const err = wishError(e);
      if (err) {
        const own = isKnownError(err.code) ? t(`moderation.wish.err.${err.code}` as MessageKey) : t("moderation.wish.err.generic");
        const server = (lang === "tr" ? err.message_tr : err.message) || null;
        setServerError({ code: err.code, text: own, detail: server && server !== own ? server : null });
      } else {
        setServerError({ code: "generic", text: t("moderation.wish.err.generic"), detail: e instanceof Error ? e.message : null });
      }
    }
  };

  if (sent) {
    return (
      <>
        <SheetHeader className="p-0">
          <SheetTitle>{t("moderation.wish.sentTitle")}</SheetTitle>
          <SheetDescription>{pairText(sent.effective, lang)}</SheetDescription>
        </SheetHeader>
        <div className="flex flex-col gap-2" role="status" data-testid="wish-sent">
          {sent.items.map((it) => (
            <p key={it.id} className="flex items-start gap-2 rounded-lg bg-fill-3 px-3 py-2 type-callout">
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-status-feasible-fg" aria-hidden />
              <span>
                {pairText(it.text, lang)}
                <span className="block type-footnote text-label-2">{t("moderation.wish.status.pending")} · {t("moderation.wish.rank")}</span>
              </span>
            </p>
          ))}
        </div>
        <SheetFooter className="flex-col-reverse gap-2 p-0 sm:flex-row sm:justify-end max-md:[&_button]:w-full">
          <Button variant="ghost" className="max-md:h-11" onClick={() => (setSent(null), setForm(emptyWish(form.requestIds)), setTried(false))} data-testid="wish-another">{t("moderation.wish.anotherOne")}</Button>
          <Button className="max-md:h-11" onClick={onClose} data-testid="wish-done">{t("moderation.wish.done")}</Button>
        </SheetFooter>
      </>
    );
  }

  return (
    <form
      className="flex flex-col gap-4"
      aria-labelledby={`${ids}-title`}
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        void send();
      }}
    >
      <SheetHeader className="p-0">
        <SheetTitle id={`${ids}-title`}>{t("moderation.wish.title")}</SheetTitle>
        <SheetDescription>{t("moderation.wish.lead")}</SheetDescription>
      </SheetHeader>

      {/* 1 · classes */}
      <fieldset className="flex flex-col gap-1" aria-describedby={`${ids}-classes-hint`}>
        <legend className="flex w-full items-center gap-2 type-headline">
          <span className="min-w-0 flex-1">{t("moderation.wish.classes")}</span>
          <span className="type-footnote font-normal text-label-2">{t("moderation.wish.classesCount", { n: n(selected.length) })}</span>
        </legend>
        <p id={`${ids}-classes-hint`} className="type-footnote text-label-2">{t("moderation.wish.classesHint")}</p>
        <div className="flex flex-wrap gap-2 py-1">
          <Button type="button" size="sm" variant="outline" className="max-md:h-11" onClick={() => set({ requestIds: classes.map((m) => m.request_id) })}>{t("moderation.wish.selectAll")}</Button>
          {form.requestIds.length ? <Button type="button" size="sm" variant="ghost" className="max-md:h-11" onClick={() => set({ requestIds: [] })}>{t("moderation.wish.clear")}</Button> : null}
        </div>
        <ul className="flex max-h-64 flex-col overflow-y-auto rounded-lg bg-fill-3 p-1" data-testid="wish-classes">
          {classes.map((m) => {
            const id = `${ids}-c${m.request_id}`;
            const on = form.requestIds.includes(m.request_id);
            return (
              <li key={m.request_id}>
                <label htmlFor={id} className={ROW} data-testid="wish-class">
                  <Checkbox id={id} className="mt-0.5" checked={on} onCheckedChange={(v) => set({ requestIds: v === true ? [...form.requestIds, m.request_id] : form.requestIds.filter((x) => x !== m.request_id) })} />
                  <span className="min-w-0 flex-1 type-callout">
                    <span className="font-semibold">{m.label}</span>
                    <span className="block type-footnote text-label-2">
                      {requestedText(m, lang)}
                      {m.requested.start_period !== null ? ` · ${t("moderation.wish.fixedTag")}` : ""}
                    </span>
                  </span>
                </label>
              </li>
            );
          })}
        </ul>
      </fieldset>

      {/* 2 · kind */}
      <div className="flex flex-col gap-1.5">
        <span id={`${ids}-kind`} className="type-headline">{t("moderation.wish.kind")}</span>
        <SegmentedControl<WishKind>
          aria-labelledby={`${ids}-kind`}
          semantics="radiogroup"
          fill
          collapse={false}
          // 44 px segments on touch (MOBILE.md M-02): the track grows instead of insetting the segments
          className="pointer-coarse:[&_[role=radiogroup]]:h-auto pointer-coarse:[&_[role=radio]]:min-h-12"
          value={form.kind}
          onValueChange={(k) => set({ kind: k })}
          options={WISH_KINDS.map((k) => ({ value: k, label: t(`moderation.wish.kinds.${k}`), testId: `wish-kind-${k}` }))}
          data-testid="wish-kind"
        />
      </div>

      {/* 3 · the fields of the kind */}
      {form.kind === "room_preference" ? (
        <div className="flex flex-col gap-1.5" data-testid="wish-rooms">
          <label htmlFor={`${ids}-room-q`} className="type-headline">{t("moderation.wish.rooms", { n: MAX_ROOMS })}</label>
          {roomCount ? (
            <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("moderation.wish.roomsPicked", { n: n(roomCount) })} data-testid="wish-rooms-picked">
              {form.roomIds.map((id, i) => (
                <Chip key={id} size="sm" className="pointer-coarse:h-9" removeLabel={t("moderation.wish.removeRoom", { room: roomNames[i] ?? "" })} onRemove={() => set({ roomIds: form.roomIds.filter((x) => x !== id) })}>
                  {roomNames[i]}
                </Chip>
              ))}
              {form.roomCodes.map((code) => (
                <Chip key={code} size="sm" className="pointer-coarse:h-9" removeLabel={t("moderation.wish.removeRoom", { room: code })} onRemove={() => set({ roomCodes: form.roomCodes.filter((x) => x !== code) })}>
                  {code}
                </Chip>
              ))}
            </div>
          ) : null}
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-label-3" aria-hidden />
            <Input id={`${ids}-room-q`} type="search" value={roomQ} onChange={(e) => setRoomQ(e.target.value)} onKeyDown={(e) => {
              // Enter adds a typed code; it never sends the form from the search box
              if (e.key !== "Enter") return;
              e.preventDefault();
              if (canAddTyped) {
                set({ roomCodes: [...form.roomCodes, typed!] });
                setRoomQ("");
              }
            }} placeholder={t("moderation.wish.roomsPh")} className="pl-8" data-testid="wish-room-search" />
          </div>
          {canAddTyped ? (
            <Button type="button" size="sm" variant="secondary" className="self-start max-md:h-11" onClick={() => (set({ roomCodes: [...form.roomCodes, typed!] }), setRoomQ(""))} data-testid="wish-room-add-code">
              {t("moderation.wish.addCode", { code: typed! })}
            </Button>
          ) : null}
          {rooms.isLoading ? (
            <p className="type-footnote text-label-2">{t("moderation.wish.roomsLoading")}</p>
          ) : roomList.length === 0 ? (
            <p className="type-footnote text-label-2" data-testid="wish-rooms-typed-hint">{t("moderation.wish.typeCodeHint")}</p>
          ) : roomHits.length === 0 ? (
            <p className="type-footnote text-label-2">{t("moderation.wish.roomsNone")}</p>
          ) : (
            <ul className="flex max-h-56 flex-col overflow-y-auto rounded-lg bg-fill-3 p-1" aria-label={t("moderation.wish.rooms", { n: MAX_ROOMS })}>
              {roomHits.map((r) => {
                const id = `${ids}-r${r.id}`;
                const on = form.roomIds.includes(r.id);
                const full = !on && roomCount >= MAX_ROOMS;
                return (
                  <li key={r.id}>
                    <label htmlFor={id} className={cn(ROW, "items-center", full && "opacity-60")} data-testid="wish-room">
                      <Checkbox id={id} checked={on} disabled={full} onCheckedChange={(v) => set({ roomIds: v === true ? [...form.roomIds, r.id] : form.roomIds.filter((x) => x !== r.id) })} />
                      <span className="min-w-0 flex-1 type-callout">{r.name || r.code}</span>
                      {r.capacity ? <span className="shrink-0 type-footnote text-label-2">{t("moderation.wish.seats", { n: n(r.capacity) })}</span> : null}
                    </label>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ) : form.kind === "building_preference" ? (
        <fieldset className="flex flex-col gap-1.5" data-testid="wish-buildings">
          <legend className="type-headline">{t("moderation.wish.buildings")}</legend>
          <div className="flex flex-wrap gap-2 pt-1">
            {buildings.map((b) => (
              <Chip key={b} className="pointer-coarse:h-11 pointer-coarse:px-4" selected={form.buildings.includes(b)} onSelectedChange={(on) => set({ buildings: on ? [...form.buildings, b] : form.buildings.filter((x) => x !== b) })} data-testid={`wish-building-${b}`}>
                {t("moderation.wish.building", { b })}
                <span className="sr-only"> ({n(roomList.filter((r) => buildingOf(r.code) === b).length)})</span>
              </Chip>
            ))}
            {form.buildings.filter((b) => !buildings.includes(b)).map((b) => (
              <Chip key={b} className="pointer-coarse:h-11 pointer-coarse:px-4" selected onSelectedChange={() => set({ buildings: form.buildings.filter((x) => x !== b) })}>
                {t("moderation.wish.building", { b })}
              </Chip>
            ))}
          </div>
          <div className="flex items-end gap-2 pt-1">
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <label htmlFor={`${ids}-bq`} className="type-footnote text-label-2">{t("moderation.wish.otherBuilding")}</label>
              <Input
                id={`${ids}-bq`}
                value={buildingQ}
                onChange={(e) => setBuildingQ(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    if (typedBuilding && !form.buildings.includes(typedBuilding)) set({ buildings: [...form.buildings, typedBuilding] });
                    setBuildingQ("");
                  }
                }}
                placeholder={t("moderation.wish.otherBuildingPh")}
                className="max-w-40"
                data-testid="wish-building-input"
              />
            </div>
            <Button type="button" variant="secondary" className="max-md:h-11" disabled={!typedBuilding || form.buildings.includes(typedBuilding)} onClick={() => (typedBuilding && set({ buildings: [...form.buildings, typedBuilding] }), setBuildingQ(""))} data-testid="wish-building-add">
              {t("moderation.wish.addBuilding")}
            </Button>
          </div>
          {buildingQ.trim() && !typedBuilding ? <p className="type-footnote text-status-warning-fg">{t("moderation.wish.badBuilding")}</p> : null}
        </fieldset>
      ) : (
        <div className="flex flex-col gap-3" data-testid="wish-window">
          {fixed.length ? (
            <Alert tone="warning" data-testid="wish-fixed">
              {allFixed ? t("moderation.wish.fixedAll") : t("moderation.wish.fixedSome", { labels: fixed.map((m) => m.label).slice(0, 3).join(", ") + (fixed.length > 3 ? " …" : "") })}
            </Alert>
          ) : null}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {(["earliest", "latest"] as const).map((k) => (
              <div key={k} className="flex flex-col gap-1">
                <label htmlFor={`${ids}-${k}`} className="type-footnote font-semibold text-label-2">{t(`moderation.wish.${k}`)}</label>
                <NativeSelect id={`${ids}-${k}`} value={form[k] === null ? "" : String(form[k])} onChange={(e) => set({ [k]: e.target.value ? Number(e.target.value) : null })} selectClassName="max-md:pointer-coarse:text-base" data-testid={`wish-${k}`}>
                  <option value="">{t("moderation.wish.any")}</option>
                  {PERIODS.map((p) => (
                    <option key={p.index} value={p.index}>{`P${p.index} · ${k === "earliest" ? p.start : p.end}`}</option>
                  ))}
                </NativeSelect>
              </div>
            ))}
          </div>
          <fieldset className="flex flex-col gap-1">
            <legend className="type-footnote font-semibold text-label-2">{t("moderation.wish.days")}</legend>
            <div className="flex flex-wrap gap-2 pt-1">
              {WEEKDAYS.map((d) => (
                <Chip key={d} className="pointer-coarse:h-11 pointer-coarse:px-4" selected={form.days.includes(d)} onSelectedChange={(on) => set({ days: on ? [...form.days, d] : form.days.filter((x) => x !== d) })}>
                  {dayName(d, locale, "short")}
                </Chip>
              ))}
            </div>
            <p className="type-footnote text-label-2">{t("moderation.wish.daysHint")}</p>
          </fieldset>
        </div>
      )}

      {/* 4 · note */}
      <div className="flex flex-col gap-1">
        <label htmlFor={`${ids}-note`} className="type-headline">{t("moderation.wish.note")}</label>
        <Textarea id={`${ids}-note`} rows={2} value={form.note} maxLength={NOTE_MAX + 50} onChange={(e) => set({ note: e.target.value })} placeholder={t("moderation.wish.notePh")} aria-describedby={`${ids}-note-count`} data-testid="wish-note" />
        <span id={`${ids}-note-count`} className={cn("self-end type-caption", form.note.trim().length > NOTE_MAX ? "text-status-infeasible-fg" : "text-label-3")}>{t("moderation.wish.noteCount", { n: n(form.note.trim().length), max: n(NOTE_MAX) })}</span>
      </div>

      {/* 5 · what the coordinator will read, before sending */}
      <section className="flex flex-col gap-1 rounded-lg bg-tint-soft px-3 py-2" aria-labelledby={`${ids}-sum`} data-testid="wish-summary">
        <h3 id={`${ids}-sum`} className="type-footnote font-semibold text-label-2">{t("moderation.wish.summary")}</h3>
        <p className="type-callout">{labels.length ? wishSentence(form, labels, roomNames, lang) : "—"}</p>
        <p className="type-footnote text-label-2">{t("moderation.wish.rank")}</p>
        <p className="type-footnote text-label-2">{t("moderation.wish.effective")}</p>
      </section>

      {tried && issues.length ? (
        <Alert tone="error" data-testid="wish-issues">
          <ul className="flex flex-col">
            {issues.map((i) => <li key={i}>{issueText(i)}</li>)}
          </ul>
        </Alert>
      ) : null}
      {serverError ? (
        <Alert tone={serverError.code === "fixed_by_department" || serverError.code === "already_requested" ? "warning" : "error"} live="assertive" data-testid="wish-error" >
          <span data-code={serverError.code}>{serverError.text}</span>
          {serverError.detail ? <span className="block type-footnote opacity-90">{serverError.detail}</span> : null}
        </Alert>
      ) : null}

      <SheetFooter className="sticky bottom-0 flex-col-reverse gap-2 bg-(--mat-thick-solid) p-0 py-2 sm:flex-row sm:justify-end max-md:[&_button]:h-11 max-md:[&_button]:w-full">
        <Button type="button" variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
        <Button type="submit" disabled={submit.isPending} aria-busy={submit.isPending || undefined} data-testid="wish-submit">
          {submit.isPending ? t("busy.sending") : t("moderation.wish.submit")}
        </Button>
      </SheetFooter>
    </form>
  );
}
