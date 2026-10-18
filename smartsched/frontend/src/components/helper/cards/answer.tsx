"use client";
/**
 * HX-04: `answer` — plain paragraphs in the log, no bubble, never links or markup; "Dizinden" for index answers.
 * An AI answer carries thumbs up / down (`POST /helper/feedback` with the turn id; one per turn, a second one replaces it).
 */
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { IconButton } from "@/components/ui/button";
import { helperApi } from "@/lib/api/helper";
import { useI18n } from "@/lib/i18n/provider";
import type { CardEntry } from "../helper-store";
import type { AnswerCard } from "../schema.gen";
import { useCardHost } from "./context";

function Feedback({ turnId }: { turnId: string }) {
  const { t } = useI18n();
  const [sent, setSent] = useState<"up" | "down" | null>(null);
  const send = (thumb: "up" | "down") => {
    setSent(thumb);
    void helperApi.feedback({ turn_id: turnId, thumb }).catch(() => undefined);
  };
  return (
    <div className="flex items-center gap-1" role="group" aria-label={t("helper.feedback.label")} data-testid="helper-feedback">
      <IconButton label={t("helper.feedback.up")} size="sm" aria-pressed={sent === "up"} onClick={() => send("up")} className="text-label-2 aria-pressed:text-tint-text">
        <ThumbsUp aria-hidden />
      </IconButton>
      <IconButton label={t("helper.feedback.down")} size="sm" aria-pressed={sent === "down"} onClick={() => send("down")} className="text-label-2 aria-pressed:text-tint-text">
        <ThumbsDown aria-hidden />
      </IconButton>
      {sent ? <span role="status" className="type-footnote text-label-3">{t("helper.feedback.thanks")}</span> : null}
    </div>
  );
}

export function AnswerView({ card, entry }: { card: AnswerCard; entry?: CardEntry }) {
  const { t } = useI18n();
  const { locale } = useCardHost();
  const paragraphs = card.text.split(/\n{2,}/).filter((p) => p.trim());
  return (
    <div data-testid={`helper-card-answer${card.action ? `-${card.action}` : ""}`} lang={card.lang !== locale ? card.lang : undefined} className="flex flex-col gap-2 type-body text-label-1">
      {paragraphs.map((p, i) => (
        <p key={i} className="whitespace-pre-line">
          {p}
        </p>
      ))}
      {card.source === "index" ? <p className="type-footnote text-label-3">{t("helper.card.fromIndex")}</p> : null}
      {card.source === "ai" && entry?.turnId ? <Feedback turnId={entry.turnId} /> : null}
    </div>
  );
}
