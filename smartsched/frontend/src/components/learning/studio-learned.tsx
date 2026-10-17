"use client";
/**
 * "Öğrenilen öneriler" at the top of the Generator Studio review tray (phase19-suggestions.md §5.3): the learned
 * suggestions of the working term, next to the AI and upload proposals, never preselected, hidden when empty.
 * Accepting writes one soft LEARNED rule to the term; the Studio rule list picks it up on its next refresh.
 * Renders nothing outside a QueryClient (unit tests of the tray) or without planning.view.
 */
import { QueryClientContext } from "@tanstack/react-query";
import { useContext } from "react";
import { useTermContext } from "@/components/timetable/use-calendar-data";
import { usePermissions } from "@/lib/permissions";
import { SuggestionList } from "./suggestion-list";

function Inner() {
  const { termId } = useTermContext();
  const { can } = usePermissions();
  if (termId === null || !can("planning.view")) return null;
  return <SuggestionList termId={termId} canAct={can("planning.edit")} surface="studio" compact className="rounded-xl border border-dashed border-hairline-strong p-3 sm:p-4" />;
}

export function StudioLearnedSuggestions() {
  const client = useContext(QueryClientContext);
  return client ? <Inner /> : null;
}
