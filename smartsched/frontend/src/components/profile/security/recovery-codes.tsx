"use client";
/**
 * Step 3 of the 2FA setup and "Yeni kurtarma kodları oluştur" (docs/design/v3/auth.md §6.3; AUX-06): 10 codes in 2
 * columns, monospace, numbered (an ordered list of 10, each code read group by group); "İndir (.txt)", "Kopyala",
 * "Yazdır"; the tick "Kodları güvenli bir yere kaydettim"; "Bitir" stays disabled until the tick. The codes are shown
 * once: the server never returns them again.
 */
import { Check, Copy, Download, Printer } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { useI18n } from "@/lib/i18n/provider";
import "@/components/auth/auth.css";

export function slugify(value: string): string {
  const map: Record<string, string> = { ç: "c", ğ: "g", ı: "i", İ: "i", ö: "o", ş: "s", ü: "u", Ç: "c", Ğ: "g", Ö: "o", Ş: "s", Ü: "u" };
  return (
    value
      .replace(/[çğıİöşüÇĞÖŞÜ]/g, (c) => map[c] ?? c)
      .toLowerCase()
      .normalize("NFKD")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 40) || "smartsched"
  );
}

/** `smartsched-kurtarma-kodlari-{org-slug}.txt` (TR) / `smartsched-recovery-codes-{org-slug}.txt` (EN). */
export function codesFileName(org: string | null | undefined, locale: string): string {
  return `${locale === "tr" ? "smartsched-kurtarma-kodlari" : "smartsched-recovery-codes"}-${slugify(org ?? "")}.txt`;
}

export function codesFileText(codes: readonly string[], v: { header: string; org: string | null | undefined; accountLabel: string; account: string; dateLabel: string; date: string; note: string }): string {
  return [`${v.header}${v.org ? ` — ${v.org}` : ""}`, `${v.accountLabel}: ${v.account}`, `${v.dateLabel}: ${v.date}`, "", ...codes.map((c, i) => `${String(i + 1).padStart(2, " ")}. ${c}`), "", v.note, ""].join("\n");
}

export function RecoveryCodes({ codes, org, account, onFinish, finishLabel }: { codes: readonly string[]; org?: string | null; account: string; onFinish: () => void; finishLabel?: string }) {
  const { t, locale } = useI18n();
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  const tickId = useId();
  const listId = useId();
  const timer = useRef<number | null>(null);
  useEffect(() => () => (timer.current ? window.clearTimeout(timer.current) : undefined), []);

  const text = () =>
    codesFileText(codes, {
      header: t("auth.setup.fileHeader"),
      org,
      accountLabel: t("auth.setup.fileAccount"),
      account,
      dateLabel: t("auth.setup.fileDate"),
      date: new Intl.DateTimeFormat(locale === "tr" ? "tr-TR" : "en-GB", { dateStyle: "long", timeStyle: "short", timeZone: "Europe/Istanbul" }).format(new Date()),
      note: t("auth.setup.fileNote"),
    });

  const download = () => {
    const blob = new Blob([text()], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = codesFileName(org, locale);
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text());
      setCopied(true);
      if (timer.current) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard refused: the codes are still on screen and in the download */
    }
  };

  const print = () => {
    const w = window.open("", "_blank", "noopener=no,width=480,height=640");
    if (!w) return;
    const pre = w.document.createElement("pre");
    pre.textContent = text();
    pre.style.font = "14px/1.6 ui-monospace, monospace";
    w.document.title = t("auth.setup.fileHeader");
    w.document.body.appendChild(pre);
    w.focus();
    w.print();
  };

  return (
    <div className="flex flex-col gap-4" data-testid="recovery-codes">
      <p className="type-callout text-label-1">{t("auth.setup.step3Text")}</p>
      <Alert tone="warning">{t("auth.setup.step3Warn")}</Alert>
      <ol id={listId} aria-label={t("auth.setup.codesLabel")} className="grid grid-cols-2 gap-x-4 gap-y-2 rounded-xl bg-fill-3 p-4 font-mono type-callout tabular-nums text-label-1 max-[359px]:grid-cols-1" data-testid="recovery-code-list">
        {codes.map((c, i) => (
          <li key={c} className="flex gap-2">
            <span aria-hidden className="w-5 text-right text-label-3">
              {i + 1}.
            </span>
            {/* spelled group by group for screen readers */}
            <span aria-label={c.split("-").join(" , ")}>{c}</span>
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="secondary" shape="rect" onClick={download} data-testid="codes-download">
          <Download aria-hidden />
          {t("auth.setup.download")}
        </Button>
        <Button type="button" variant="secondary" shape="rect" onClick={() => void copy()} data-testid="codes-copy">
          <span key={copied ? "c" : "n"} className="auth-icon-swap">
            {copied ? <Check aria-hidden className="size-4" /> : <Copy aria-hidden className="size-4" />}
          </span>
          <span key={copied ? "tc" : "tn"} className="auth-text-swap">
            {copied ? t("auth.setup.copied") : t("auth.setup.copy")}
          </span>
        </Button>
        <Button type="button" variant="secondary" shape="rect" onClick={print} data-testid="codes-print">
          <Printer aria-hidden />
          {t("auth.setup.print")}
        </Button>
      </div>
      <span role="status" className="sr-only">
        {copied ? t("auth.setup.copied") : ""}
      </span>
      <label htmlFor={tickId} className="flex min-h-11 cursor-pointer items-center gap-3 type-callout text-label-1">
        <Checkbox id={tickId} checked={saved} onCheckedChange={(v) => setSaved(Boolean(v))} data-testid="codes-saved" />
        {t("auth.setup.saved")}
      </label>
      <Button type="button" size="lg" shape="rect" className="w-full" disabled={!saved} onClick={onFinish} data-testid="codes-finish">
        {finishLabel ?? t("auth.setup.finish")}
      </Button>
    </div>
  );
}
