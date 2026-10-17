"use client";
/** The checklist as a card on the audience's home page (`/dashboard`, `/reserve`, `/admin`) until it is complete or hidden. */
import { Card } from "@/components/ui/card";
import { ChecklistPanel, useChecklistModel } from "./checklist-list";

export function ChecklistHomeCard() {
  const model = useChecklistModel();
  if (!model || model.hidden || model.allDone) return null;
  return (
    <Card className="mb-4 max-w-2xl gap-0 px-4 py-4" data-testid="checklist-home-card">
      <ChecklistPanel model={model} />
    </Card>
  );
}
