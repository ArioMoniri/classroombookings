"use client";
/**
 * Yönetim › KVKK › Aydınlatma metni (`setup.settings`): the privacy notice, versioned per language. Drafts are edited
 * and deleted; publishing freezes a text for good (a change is a new version) and every user is asked to read the new
 * version at their next visit. SmartSched ships no notice text: the institution writes it with its KVKK officer.
 * The body is plain Markdown (headings, lists, bold), previewed exactly as users will read it.
 */
import { Eye, Pencil, Plus, Send, Trash2 } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import { Alert, ConfirmDialog, Field, Loading } from "@/components/admin/kit";
import { useIsPhone } from "@/components/bookings/use-is-phone";
import { Button, IconButton } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { noticeVersions, useDeleteNotice, useNotices, usePublishNotice, useSaveNotice, type Notice, type NoticeIn } from "@/lib/api/kvkk";
import { errorText, wave1Error } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";
import { Markdown } from "@/components/privacy/markdown";
import { useDateTime } from "@/components/privacy/privacy-section";

type Editing = { id: number | null; body: NoticeIn };

export function NoticeEditor() {
  const { t, locale } = useI18n();
  const q = useNotices();
  const publish = usePublishNotice();
  const del = useDeleteNotice();
  const when = useDateTime();
  const [editing, setEditing] = useState<Editing | null>(null);
  const [viewing, setViewing] = useState<Notice | null>(null);
  const [publishing, setPublishing] = useState<Notice | null>(null);
  const [deleting, setDeleting] = useState<Notice | null>(null);
  const list = q.data ?? [];
  const versions = noticeVersions(list);
  const next = (versions[0]?.version ?? 0) + 1;
  const fail = (e: unknown) => toast.error(errorText(wave1Error(e), locale));

  const lang = (n: Notice | null, code: "tr" | "en", version: number) => (
    <div className="flex min-w-0 flex-col gap-1.5 rounded-lg bg-fill-3 p-3" data-testid={`notice-v${version}-${code}`}>
      <p className="type-footnote font-medium text-label-2">{t(code === "tr" ? "kvkk.notice.tr" : "kvkk.notice.en")}</p>
      {n ? (
        <>
          <p className="type-callout font-medium text-label-1">{n.title}</p>
          <p className="type-footnote text-label-3">{n.published_at ? t("kvkk.notice.publishedOn", { date: when(n.published_at, true) }) : t("kvkk.notice.draft")}</p>
          <div className="flex flex-wrap gap-1">
            <Button size="sm" variant="ghost" onClick={() => setViewing(n)}>
              <Eye aria-hidden />
              {t("kvkk.notice.view")}
            </Button>
            {!n.published_at ? (
              <>
                <Button size="sm" variant="ghost" onClick={() => setEditing({ id: n.id, body: { language: n.language as "tr" | "en", title: n.title, body_md: n.body_md, version: n.version } })} data-testid={`notice-edit-${n.id}`}>
                  <Pencil aria-hidden />
                  {t("kvkk.notice.edit")}
                </Button>
                <Button size="sm" onClick={() => setPublishing(n)} data-testid={`notice-publish-${n.id}`}>
                  <Send aria-hidden />
                  {t("kvkk.notice.publish")}
                </Button>
                <IconButton size="sm" label={t("kvkk.notice.deleteLabel", { v: n.version, lang: n.language.toUpperCase() })} onClick={() => setDeleting(n)}>
                  <Trash2 aria-hidden />
                </IconButton>
              </>
            ) : null}
          </div>
        </>
      ) : (
        <Button size="sm" variant="outline" className="self-start" onClick={() => setEditing({ id: null, body: { language: code, title: "", body_md: "", version } })} data-testid={`notice-add-${version}-${code}`}>
          <Plus aria-hidden />
          {t("kvkk.notice.addLanguage")}
        </Button>
      )}
    </div>
  );

  return (
    <div className="flex flex-col gap-4" data-testid="notice-editor">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-2xl type-callout text-label-2">{t("kvkk.notice.lead")}</p>
        {/* the next version number needs the list: until it loads the button waits (it said "1" and the save got a 409) */}
        <Button size="sm" className="pointer-coarse:min-h-11" disabled={!q.isSuccess} onClick={() => setEditing({ id: null, body: { language: "tr", title: "", body_md: "", version: next } })} data-testid="notice-new">
          <Plus aria-hidden />
          {t("kvkk.notice.newVersion", { v: next })}
        </Button>
      </div>
      {q.isLoading ? <Loading /> : null}
      {q.isError ? <Alert tone="error">{errorText(wave1Error(q.error), locale)}</Alert> : null}
      {q.isSuccess && !list.length ? <p className="rounded-xl bg-fill-3 p-3 type-callout text-label-2" data-testid="notice-empty">{t("kvkk.notice.empty")}</p> : null}
      <ul className="flex flex-col gap-3">
        {versions.map((v, i) => (
          <li key={v.version}>
            <Card className="gap-3 px-4 py-4">
              <p className="flex flex-wrap items-center gap-2 type-headline text-label-1">
                {t("kvkk.notice.version", { v: v.version })}
                {v.published ? <span className="rounded-full bg-status-feasible px-2 type-caption text-status-feasible-fg">{i === versions.findIndex((x) => x.published) ? t("kvkk.notice.current") : t("kvkk.notice.published")}</span> : <span className="rounded-full bg-fill-2 px-2 type-caption text-label-2">{t("kvkk.notice.draft")}</span>}
              </p>
              <div className="grid gap-2 sm:grid-cols-2">
                {lang(v.tr, "tr", v.version)}
                {lang(v.en, "en", v.version)}
              </div>
              {v.published && (!v.tr?.published_at || !v.en?.published_at) ? <p className="type-footnote text-label-3">{t("kvkk.notice.fallback")}</p> : null}
            </Card>
          </li>
        ))}
      </ul>

      <NoticeSheet editing={editing} onClose={() => setEditing(null)} />

      <Sheet open={!!viewing} onOpenChange={(o) => !o && setViewing(null)}>
        <SheetContent side="right" className="sm:max-w-xl" data-testid="notice-view">
          {viewing ? (
            <>
              <SheetHeader className="px-5 pt-5">
                <SheetTitle className="type-title-3">{viewing.title}</SheetTitle>
                <SheetDescription>{t("kvkk.notice.versionLang", { v: viewing.version, lang: viewing.language.toUpperCase() })}</SheetDescription>
              </SheetHeader>
              <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-5">
                <Markdown source={viewing.body_md} className="type-callout text-label-1" />
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>

      <ConfirmDialog
        open={!!publishing}
        onOpenChange={(o) => !o && setPublishing(null)}
        title={t("kvkk.notice.publishTitle", { v: publishing?.version ?? 0, lang: publishing?.language.toUpperCase() ?? "" })}
        description={t("kvkk.notice.publishBody")}
        confirmLabel={t("kvkk.notice.publish")}
        busy={publish.isPending}
        onConfirm={() =>
          publishing &&
          publish.mutate(publishing.id, {
            onSuccess: () => {
              setPublishing(null);
              toast.success(t("kvkk.notice.publishedToast"));
            },
            onError: fail,
          })
        }
      />
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t("kvkk.notice.deleteTitle")}
        confirmLabel={t("kvkk.notice.delete")}
        destructive
        busy={del.isPending}
        onConfirm={() => deleting && del.mutate(deleting.id, { onSuccess: () => setDeleting(null), onError: fail })}
      />
    </div>
  );
}

function NoticeSheet({ editing, onClose }: { editing: Editing | null; onClose: () => void }) {
  const { t } = useI18n();
  const phone = useIsPhone();
  return (
    <Sheet open={!!editing} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side={phone ? "bottom" : "right"} className="gap-0 data-[side=bottom]:max-h-[94dvh] data-[side=right]:sm:max-w-2xl" data-testid="notice-sheet">
        <SheetHeader className="px-5 pt-5 pb-2">
          <SheetTitle className="type-title-3">{editing?.id ? t("kvkk.notice.editTitle") : t("kvkk.notice.newTitle")}</SheetTitle>
          <SheetDescription>{t("kvkk.notice.formLead")}</SheetDescription>
        </SheetHeader>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-5">{editing ? <NoticeForm key={editing.id ?? `new-${editing.body.version}-${editing.body.language}`} editing={editing} onDone={onClose} /> : null}</div>
      </SheetContent>
    </Sheet>
  );
}

function NoticeForm({ editing, onDone }: { editing: Editing; onDone: () => void }) {
  const { t, locale } = useI18n();
  const save = useSaveNotice();
  const [b, setB] = useState<NoticeIn>(editing.body);
  const [mode, setMode] = useState<"write" | "preview">("write");
  const [error, setError] = useState<string | null>(null);
  const ids = { lang: useId(), title: useId(), body: useId(), version: useId() };
  const ok = b.title.trim() && b.body_md.trim();
  const submit = () => {
    setError(null);
    if (!ok) return setError(t("kvkk.notice.required"));
    save.mutate(
      { id: editing.id, body: { ...b, title: b.title.trim() } },
      {
        onSuccess: () => {
          toast.success(t("kvkk.notice.saved"));
          onDone();
        },
        onError: (e) => setError(errorText(wave1Error(e), locale)),
      },
    );
  };
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      data-testid="notice-form"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("kvkk.notice.language")} htmlFor={ids.lang}>
          <NativeSelect id={ids.lang} value={b.language} disabled={!!editing.id} onChange={(e) => setB({ ...b, language: e.target.value as "tr" | "en" })} data-testid="notice-language">
            <option value="tr">Türkçe</option>
            <option value="en">English</option>
          </NativeSelect>
        </Field>
        <Field label={t("kvkk.notice.versionField")} htmlFor={ids.version} hint={t("kvkk.notice.versionHint")}>
          <Input id={ids.version} type="number" min={1} inputMode="numeric" value={b.version ?? ""} disabled={!!editing.id} onChange={(e) => setB({ ...b, version: e.target.value ? Number(e.target.value) : null })} />
        </Field>
      </div>
      <Field label={t("kvkk.notice.titleField")} htmlFor={ids.title}>
        <Input id={ids.title} value={b.title} maxLength={255} onChange={(e) => setB({ ...b, title: e.target.value })} data-testid="notice-title" />
      </Field>
      <div className="flex flex-col gap-1.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label htmlFor={ids.body} className="type-footnote font-medium text-label-2">
            {t("kvkk.notice.body")}
          </label>
          <SegmentedControl size="sm" aria-label={t("kvkk.notice.body")} value={mode} onValueChange={(v) => setMode(v as "write" | "preview")} options={[{ value: "write", label: t("kvkk.notice.write") }, { value: "preview", label: t("kvkk.notice.preview"), testId: "notice-preview" }]} />
        </div>
        {mode === "write" ? (
          <Textarea id={ids.body} rows={14} value={b.body_md} onChange={(e) => setB({ ...b, body_md: e.target.value })} className="font-mono" data-testid="notice-body" />
        ) : b.body_md.trim() ? (
          <Markdown source={b.body_md} className="min-h-40 rounded-lg bg-fill-3 p-3 type-callout text-label-1" />
        ) : (
          <p className="rounded-lg bg-fill-3 p-3 type-callout text-label-3">{t("kvkk.notice.previewEmpty")}</p>
        )}
        <p className="type-footnote text-label-3">{t("kvkk.notice.markdownHint")}</p>
      </div>
      {error ? <Alert tone="error" testId="notice-error">{error}</Alert> : null}
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button type="button" variant="ghost" onClick={onDone} disabled={save.isPending}>
          {t("crbs.common.cancel")}
        </Button>
        <Button type="submit" {...busyProps(save.isPending)} data-testid="notice-save">
          <BusyLabel busy={save.isPending} label={t("busy.saving")}>
            {t("kvkk.notice.saveDraft")}
          </BusyLabel>
        </Button>
      </div>
    </form>
  );
}
