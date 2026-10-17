"use client";
/**
 * CopyField (docs/design/v3/integrations.md §5.2, IN-06): a label, the whole value (read-only input or a focusable
 * `<pre>`; wraps, never truncated, `user-select: all`) and "Kopyala". Success swaps the label to "✓ Kopyalandı" for
 * 1.5 s in place (no toast) and announces "{label} kopyalandı"; when the Clipboard API fails, the value is selected
 * and the message says to press Ctrl+C.
 */
import { Check, Copy } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

export const COPIED_MS = 1500;

export function CopyField({ label, value, mono = true, multiline = false, testId }: { label: string; value: string; mono?: boolean; multiline?: boolean; testId?: string }) {
  const { t } = useI18n();
  const id = useId();
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const valueRef = useRef<HTMLInputElement | HTMLPreElement | null>(null);
  useEffect(() => {
    if (state !== "copied") return;
    const timer = window.setTimeout(() => setState("idle"), COPIED_MS);
    return () => window.clearTimeout(timer);
  }, [state]);
  const selectValue = () => {
    const el = valueRef.current;
    if (!el) return;
    if (el instanceof HTMLInputElement) {
      el.focus();
      el.select();
    } else {
      const range = document.createRange();
      range.selectNodeContents(el);
      const sel = window.getSelection();
      sel?.removeAllRanges();
      sel?.addRange(range);
      el.focus();
    }
  };
  const copy = async () => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error("no clipboard");
      await navigator.clipboard.writeText(value);
      setState("copied");
    } catch {
      setState("failed");
      selectValue();
    }
  };
  return (
    <div className="grid gap-1.5" data-testid={testId}>
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={id}>{label}</Label>
        <Button size="sm" variant="outline" onClick={copy} aria-label={t("integrations.guided.copyWhat", { what: label })} className="min-w-28 pointer-coarse:min-h-11" data-testid={testId ? `${testId}-copy` : undefined} data-state={state}>
          {state === "copied" ? <Check aria-hidden /> : <Copy aria-hidden />}
          {t(state === "copied" ? "integrations.guided.copied" : "integrations.guided.copy")}
        </Button>
      </div>
      {multiline ? (
        <pre
          id={id}
          ref={(el) => {
            valueRef.current = el;
          }}
          tabIndex={0}
          aria-label={label}
          className={cn("max-h-56 overflow-auto rounded-xl bg-fill-2 p-3 type-caption whitespace-pre-wrap break-all text-label-1 select-all", mono && "font-mono")}
        >
          {value}
        </pre>
      ) : (
        <Input
          id={id}
          ref={(el) => {
            valueRef.current = el;
          }}
          readOnly
          value={value}
          className={cn("select-all pointer-coarse:text-base", mono && "font-mono")}
          onFocus={(e) => e.currentTarget.select()}
        />
      )}
      <p role="status" aria-live="polite" className={cn("type-caption", state === "failed" ? "text-status-infeasible-fg" : "sr-only")}>
        {state === "copied" ? t("integrations.guided.copiedLive", { label }) : state === "failed" ? t("integrations.guided.copyFailed") : ""}
      </p>
    </div>
  );
}
