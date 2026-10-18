"use client";
/**
 * HB-23c, KVKK review condition 10: the end of a session for the helper's file router. Sign-out (user menu) and the
 * 401 redirect (app shell) call {@link clearHelperFileSession} **before** the session is revoked, so the stages are
 * deleted while the cookie still works and `sessionStorage["smartsched.helper.fileHandoff"]` (token + file name)
 * never reaches the next person's session. The router modules are fetched on demand (the shell stays light).
 */
import { useHelperStore } from "./helper-store";

/** the hand-over's sessionStorage key (file-handoff.ts `HANDOFF_STORAGE_KEY`; a test keeps them equal) */
export const HANDOFF_KEY = "smartsched.helper.fileHandoff";

export async function clearHelperFileSession(): Promise<void> {
  try {
    window.sessionStorage.removeItem(HANDOFF_KEY);
  } catch {
    /* private mode */
  }
  try {
    const [{ useFileHandoffStore }, { dropLiveStages, forgetEntryFiles }, { dropStage }] = await Promise.all([
      import("./file-handoff"),
      import("./file-router"),
      import("@/lib/api/helper-files"),
    ]);
    // the stage a page was handed, then the thread's live ones (fire-and-forget DELETEs, sent before the logout)
    for (const i of useFileHandoffStore.getState().handoff?.items ?? []) if (i.token) dropStage({ upload_token: i.token, sid: i.sid ?? undefined });
    dropLiveStages();
    forgetEntryFiles();
    useFileHandoffStore.getState().clear();
  } finally {
    // the conversation (file names, cards) belongs to the person who is leaving
    const st = useHelperStore.getState();
    st.closeSheet();
    st.newThread();
  }
}
