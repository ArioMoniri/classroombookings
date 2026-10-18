"use client";
/**
 * HB-23c (helper-file-router.md §4–§7): the client side of the router. One function set for the sheet's 📎 / paste /
 * drop and the page's edge target:
 *
 * - `attach(files)`: several files with `planning.edit` → one "{n} dosya" card that opens the setup wizard with all of
 *   them (owner decision; no classify, the wizard reads them together). Otherwise the first file: the 15 MB pre-check
 *   (no request over it), then `POST /helper/files/classify`. A newer file collapses the older live card.
 * - `pick(kind)`: the chooser / "Başka bir tür seç" → `POST /helper/files/route` (the token stays valid).
 * - `primary(route)`: a route that carries the file → `POST /helper/files/handoff` (the audit row), then the hand-over
 *   slot (file-handoff.ts) and the page's address; a route without the file deletes the stage and opens the page.
 * - `cancel()` ("Vazgeç"), `dropLive()` (the sheet's close / Esc / "Yeni konuşma"): the stage is deleted at once.
 *
 * The browser's File objects stay in this module (memory only): "Tekrar dene" and "Dosyayı yeniden oku" re-send the
 * same File without a new pick.
 */
import { useMemo } from "react";
import { HttpError } from "@/lib/api/client";
import { helperRefusal } from "@/lib/api/helper";
import { CLASSIFY_MAX_BYTES, dropStage, helperFilesApi, isStageGone, sidOf, type FileAnswerCard, type FileRoute } from "@/lib/api/helper-files";
import { usePermissions } from "@/lib/api/shell-extra";
import { translate, type MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { fileHandoffHref, useFileHandoffStore, type HandoffParams } from "./file-handoff";
import { useHelperStore, type FileEntry } from "./helper-store";

const both = (key: MessageKey, vars?: Record<string, string | number>) => ({ tr: translate("tr", key, vars), en: translate("en", key, vars) });

const files = new Map<string, File[]>();
const inflight = new Map<string, AbortController>();

/** the kinds a person may pick under "Başka bir tür seç" (client side, from the same permission keys as §4.2) */
export const PICKABLE_KINDS: readonly { kind: string; perms: readonly string[] }[] = [
  { kind: "planning_list", perms: ["planning.edit"] },
  { kind: "exam_list", perms: ["planning.edit"] },
  { kind: "weekly_grid", perms: ["planning.edit"] },
  { kind: "room_master", perms: ["planning.edit", "setup.rooms"] },
  { kind: "users_csv", perms: ["setup.users"] },
  { kind: "crbs_dump", perms: ["planning.edit"] },
];

const entryOf = (key: string): FileEntry | undefined => {
  const e = useHelperStore.getState().entries.find((x) => x.key === key);
  return e && e.kind === "file" ? e : undefined;
};

/** the file entry's in-memory File objects (null after a reload or "Yeni konuşma") */
export const entryFiles = (key: string): File[] | null => files.get(key) ?? null;

const update = (key: string, patch: Partial<FileEntry> | ((e: FileEntry) => Partial<FileEntry>)) => useHelperStore.getState().updateFile(key, patch);

const shown = (key: string, card: FileAnswerCard, stage: FileEntry["stage"]) =>
  update(key, (e) => ({ phase: "shown", view: { kind: "card", card }, stage: stage ?? null, expired: false, notice: null, seq: e.seq + 1 }));

async function classifyInto(key: string, file: File, lang: string, context: string | null) {
  update(key, { phase: "reading", view: null, notice: null, expired: false });
  if (file.size > CLASSIFY_MAX_BYTES) {
    update(key, (e) => ({ phase: "shown", view: { kind: "local", code: "file_too_large", size: file.size }, seq: e.seq + 1 }));
    return;
  }
  const ctl = new AbortController();
  inflight.set(key, ctl);
  try {
    const out = await helperFilesApi.classify(file, { context, lang, signal: ctl.signal });
    if (ctl.signal.aborted || entryOf(key)?.phase !== "reading") {
      // "Vazgeç" came first: the stage is not wanted
      dropStage(out.stage);
      return;
    }
    shown(key, out.card, out.stage ?? null);
  } catch (err) {
    if (ctl.signal.aborted || entryOf(key)?.phase !== "reading") return;
    const status = err instanceof HttpError ? err.status : 0;
    const card = helperRefusal(err).card;
    if (card && (card.type === "refusal" || card.type === "error" || card.type === "limit")) shown(key, card, null);
    else if (status === 413) update(key, (e) => ({ phase: "shown", view: { kind: "local", code: "file_too_large", size: file.size }, seq: e.seq + 1 }));
    else update(key, (e) => ({ phase: "shown", view: { kind: "local", code: "file_read_failed" }, seq: e.seq + 1 }));
  } finally {
    inflight.delete(key);
  }
}

/** Delete every live stage of the thread (the sheet's close, Esc, "Yeni konuşma"); their cards say "yeniden oku". */
export function dropLiveStages() {
  for (const e of useHelperStore.getState().entries) {
    if (e.kind !== "file") continue;
    inflight.get(e.key)?.abort();
    if (e.stage) {
      dropStage(e.stage);
      update(e.key, { stage: null, expired: e.view?.kind === "card" || e.view?.kind === "pick" ? true : e.expired });
    }
    if (e.phase === "reading") update(e.key, { phase: "cancelled" });
  }
}

export function forgetEntryFiles() {
  files.clear();
}

type Can = (perm: string | readonly string[] | undefined) => boolean;

/**
 * Attach files to the helper's thread (📎, paste, the sheet's drop, the page's edge target). Several files with
 * `planning.edit` → one "{n} dosya" card; otherwise the first file is classified. Returns the entry key.
 */
export function attachFiles(list: readonly File[], opts: { can: Can; lang: string; context?: string | null }): string | null {
  const picked = list.filter((f) => f instanceof File);
  if (!picked.length) return null;
  const st = useHelperStore.getState();
  // one live card per thread: the older stage goes (the server also keeps one stage per person)
  for (const e of st.entries) if (e.kind === "file" && e.stage && (e.phase === "shown" || e.phase === "reading")) dropStage(e.stage);
  if (picked.length > 1 && opts.can("planning.edit")) {
    const key = st.pushFile(picked.map((f) => ({ name: f.name, size: f.size })));
    files.set(key, [...picked]);
    update(key, (e) => ({ phase: "shown", view: { kind: "many", n: picked.length }, seq: e.seq + 1 }));
    return key;
  }
  // §15.4: people without planning.edit get the first file classified
  const file = picked[0];
  const key = st.pushFile([{ name: file.name, size: file.size }]);
  files.set(key, [file]);
  void classifyInto(key, file, opts.lang, opts.context ?? null);
  return key;
}

export type Go = (href: string) => void;

export function useFileRouter() {
  const { locale } = useI18n();
  const { can } = usePermissions();
  return useMemo(() => {
    const attach = (list: readonly File[], opts: { context?: string | null } = {}) => attachFiles(list, { can, lang: locale, context: opts.context });

    /** "Tekrar dene" / "Dosyayı yeniden oku": the same File again; false when the browser no longer holds it */
    const retry = (key: string): boolean => {
      const f = files.get(key)?.[0];
      if (!f) return false;
      void classifyInto(key, f, locale, null);
      return true;
    };

    const cancel = (key: string) => {
      inflight.get(key)?.abort();
      const e = entryOf(key);
      if (e?.stage) dropStage(e.stage);
      update(key, { phase: "cancelled", stage: null });
    };

    /** the chooser pick or a kind from "Başka bir tür seç" */
    const pick = async (key: string, kind: string) => {
      const e = entryOf(key);
      const token = e?.stage?.upload_token;
      if (!e || !token) return;
      update(key, { notice: null });
      try {
        const out = await helperFilesApi.route(token, kind);
        shown(key, out.card, e.stage);
      } catch (err) {
        if (isStageGone(err)) update(key, { expired: true, stage: null });
        else {
          const card = helperRefusal(err).card;
          if (card && (card.type === "refusal" || card.type === "error")) shown(key, card, e.stage);
          else update(key, { notice: both("helper.file.error") });
        }
      }
    };

    const showKinds = (key: string) => update(key, (e) => (e.view?.kind === "card" ? { view: { kind: "pick", card: e.view.card } } : {}));
    const hideKinds = (key: string) => update(key, (e) => (e.view?.kind === "pick" ? { view: { kind: "card", card: e.view.card } } : {}));

    /** the card's one primary (or a secondary route): the hand-over, then the page */
    const primary = async (key: string, route: Pick<FileRoute, "feature_id" | "params" | "carries_file">, go: Go, kind: string | null) => {
      const e = entryOf(key);
      if (!e) return;
      const params = (route.params ?? {}) as HandoffParams;
      const href = fileHandoffHref(route.feature_id, params);
      if (!href) return;
      if (e.view?.kind === "many") {
        const all = files.get(key) ?? [];
        useFileHandoffStore.getState().set(
          { featureId: "onboarding", kind: null, params: {}, items: all.map((f) => ({ token: null, sid: null, name: f.name, size: f.size, format: null, expiresAt: null })), at: Date.now() },
          all,
        );
        update(key, { phase: "handed" });
        go(href);
        return;
      }
      if (route.carries_file && e.stage) {
        const stage = e.stage;
        update(key, { notice: null });
        try {
          await helperFilesApi.handoff({ upload_token: stage.upload_token, kind, feature_id: route.feature_id, params });
        } catch (err) {
          if (isStageGone(err)) update(key, { expired: true, stage: null });
          else update(key, { notice: both(err instanceof HttpError && err.status === 403 ? "helper.file.notAllowed" : "helper.file.error") });
          return;
        }
        const f = files.get(key)?.[0];
        const expiresAt = Date.parse(stage.expires_at);
        useFileHandoffStore.getState().set(
          {
            featureId: route.feature_id,
            kind,
            params,
            items: [{ token: stage.upload_token, sid: sidOf(stage), name: f?.name ?? e.files[0]?.name ?? "", size: f?.size ?? e.files[0]?.size ?? stage.size ?? 0, format: stage.format ?? null, expiresAt: Number.isFinite(expiresAt) ? expiresAt : null }],
            at: Date.now(),
          },
          f ? [f] : [],
        );
        // the stage now belongs to the page (closing the sheet must not delete it)
        update(key, { phase: "handed", stage: null });
        go(href);
        return;
      }
      // no file on this route (Derslerim, Takvimime ekle…): the stage is not needed any more
      if (e.stage) dropStage(e.stage);
      update(key, { phase: "handed", stage: null });
      go(href);
    };

    return { attach, retry, cancel, pick, showKinds, hideKinds, primary };
  }, [can, locale]);
}

export type FileRouter = ReturnType<typeof useFileRouter>;
