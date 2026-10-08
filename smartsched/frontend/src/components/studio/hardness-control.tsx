"use client";

import { HelpCircle } from "lucide-react";
import { useId, useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useI18n } from "@/lib/i18n/provider";
import { DEFAULT_SCALE, importanceOf, type WeightScale } from "./rule-sentence";
import { Segmented } from "./segmented";

const SEEN_KEY = "smartsched.studio.mustHelpSeen";

/**
 * "Must / Try to" (radiogroup with a plain explanation) + "How important: Low · Normal · High"
 * (Try-to only; 1–10 slider in the advanced layer). Kinds that allow one hardness disable the other
 * option with the reason.
 */
export function HardnessControl({
  hardness,
  weight,
  allowed = ["hard", "soft"],
  onHardness,
  onWeight,
  scale = DEFAULT_SCALE,
  advanced,
  compact,
  idPrefix,
}: {
  hardness: "hard" | "soft";
  weight: number;
  allowed?: readonly ("hard" | "soft")[];
  onHardness: (h: "hard" | "soft") => void;
  onWeight: (w: number) => void;
  scale?: WeightScale;
  advanced: boolean;
  compact?: boolean;
  idPrefix?: string;
}) {
  const { t } = useI18n();
  const auto = useId();
  const id = idPrefix ?? auto;
  const [showNote, setShowNote] = useState(false);
  const [firstUse, setFirstUse] = useState(false);
  const imp = importanceOf(weight, scale);
  const onlyOne = allowed.length === 1;

  const change = (h: "hard" | "soft") => {
    if (h === hardness) return;
    try {
      if (!window.localStorage.getItem(SEEN_KEY)) {
        window.localStorage.setItem(SEEN_KEY, "1");
        setFirstUse(true);
      }
    } catch {
      /* ignore */
    }
    setShowNote(h === "hard");
    onHardness(h);
  };

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <div className="flex items-center gap-1">
        <span id={`${id}-hl`} className="sr-only">
          {t("studio.rule.mustOrTry")}
        </span>
        <Segmented
          size="sm"
          labelledBy={`${id}-hl`}
          describedBy={`${id}-help`}
          value={hardness}
          onChange={change}
          testId="rule-hardness"
          options={[
            { value: "hard", label: t("studio.rule.must"), disabled: !allowed.includes("hard"), title: !allowed.includes("hard") ? t("studio.rule.onlyTry") : undefined, testId: "hardness-hard" },
            { value: "soft", label: t("studio.rule.try"), disabled: !allowed.includes("soft"), title: !allowed.includes("soft") ? t("studio.rule.onlyMust") : undefined, testId: "hardness-soft" },
          ]}
        />
        <Popover>
          <PopoverTrigger
            render={<button type="button" className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground pointer-coarse:size-11" aria-label={t("studio.rule.whatsThis")} />}
          >
            <HelpCircle className="size-3.5" aria-hidden />
          </PopoverTrigger>
          <PopoverContent className="w-72 space-y-2 text-sm">
            <p>
              <strong>{t("studio.rule.must")}:</strong> {t("studio.rule.mustHelp")}
            </p>
            <p>
              <strong>{t("studio.rule.try")}:</strong> {t("studio.rule.tryHelp")}
            </p>
          </PopoverContent>
        </Popover>
      </div>
      <span id={`${id}-help`} className={firstUse || !compact ? "basis-full text-xs text-muted-foreground" : "sr-only"}>
        {hardness === "hard" ? t("studio.rule.mustHelp") : t("studio.rule.tryHelp")}
        {onlyOne ? ` ${allowed[0] === "hard" ? t("studio.rule.onlyMust") : t("studio.rule.onlyTry")}` : ""}
      </span>
      {showNote && hardness === "hard" ? (
        <span role="note" className="basis-full rounded-md bg-status-warning px-2 py-1 text-xs text-status-warning-fg">
          {t("studio.rule.mustNote")}
        </span>
      ) : null}
      {hardness === "soft" ? (
        <div className="flex flex-wrap items-center gap-2">
          <span id={`${id}-il`} className="text-xs text-muted-foreground">
            {t("studio.rule.importance")}
          </span>
          <Segmented
            size="sm"
            labelledBy={`${id}-il`}
            describedBy={`${id}-ih`}
            value={imp === "custom" ? null : imp}
            onChange={(v) => onWeight(scale[v as "low" | "normal" | "high"])}
            testId="rule-importance"
            options={[
              { value: "low", label: t("studio.rule.low") },
              { value: "normal", label: t("studio.rule.normal") },
              { value: "high", label: t("studio.rule.high") },
            ]}
          />
          {imp === "custom" ? <span className="text-xs text-muted-foreground">{t("studio.rule.custom", { n: weight })}</span> : null}
          <span id={`${id}-ih`} className="sr-only">
            {t("studio.rule.importanceHelp")}
          </span>
          {advanced ? (
            <div className="flex w-36 items-center gap-2">
              <input
                type="range"
                min={1}
                max={10}
                step={1}
                value={weight}
                onChange={(e) => onWeight(Number(e.target.value))}
                aria-label={t("studio.rule.weightSlider")}
                aria-valuetext={t("studio.rule.weightValue", { n: weight })}
                className="h-1.5 w-full cursor-pointer accent-[var(--primary)]"
                data-testid="weight-slider"
              />
              <span className="w-5 text-right font-mono text-xs tabular-nums">{weight}</span>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
