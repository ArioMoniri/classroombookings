"use client";
/** HX-04: `answer` — plain paragraphs in the log, no bubble, never links or markup; "Dizinden" for index answers. */
import { useI18n } from "@/lib/i18n/provider";
import type { AnswerCard } from "../schema.gen";
import { useCardHost } from "./context";

export function AnswerView({ card }: { card: AnswerCard }) {
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
    </div>
  );
}
