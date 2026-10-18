"use client";
/**
 * Genel: the part switches (spec §4.6, §7). Up front: Karşılama rehberi, Rehberli tur, Başlarken listesi, Yeni özellik
 * ipuçları. Under "Gelişmiş": Herkese ipucu göster (off by default) and "Önce kendinizde deneyin" (opens the sheet for
 * a chosen audience without writing progress). Each switch saves at once (PUT /welcome/settings, audited).
 */
import { ChevronDown } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import { Loading, SelectField } from "@/components/admin/kit";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { AUDIENCES, type Audience, type WelcomeSettings, useSaveWelcomeSettings, useWelcomeSettings } from "@/lib/api/welcome";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { audienceKey } from "../content";
import { useWelcomeStore } from "../welcome-store";

type SwitchPart = "sheet" | "tour" | "checklist" | "hints" | "hints_for_all";
/** the settings field each switch writes, and its copy (`welcome.admin.part.<copy>`) */
const MAIN: { part: SwitchPart; copy: string }[] = [
  { part: "sheet", copy: "enabled" },
  { part: "tour", copy: "tour" },
  { part: "checklist", copy: "checklist" },
  { part: "hints", copy: "hints" },
];

function SwitchRow({ part, copy, settings, onChange, busy }: { part: SwitchPart; copy: string; settings: WelcomeSettings; onChange: (part: SwitchPart, v: boolean) => void; busy: boolean }) {
  const { t } = useI18n();
  const id = useId();
  return (
    <li className="flex items-center gap-4 px-4 py-3 not-last:edge-hairline-b">
      <label htmlFor={id} className="min-w-0 flex-1 cursor-pointer">
        <span className="block type-headline text-label-1">{t(`welcome.admin.part.${copy}.title` as MessageKey)}</span>
        <span className="block type-footnote text-label-2">{t(`welcome.admin.part.${copy}.body` as MessageKey)}</span>
      </label>
      <Switch id={id} checked={!!settings[part]} disabled={busy} onCheckedChange={(v) => onChange(part, v)} data-testid={`welcome-switch-${part}`} />
    </li>
  );
}

export function WelcomeGeneral() {
  const { t } = useI18n();
  const q = useWelcomeSettings();
  const save = useSaveWelcomeSettings();
  const [advanced, setAdvanced] = useState(false);
  const [audience, setAudience] = useState<Audience>("academician");
  const openSheet = useWelcomeStore((s) => s.openSheet);
  const advId = useId();
  const selectId = useId();
  if (q.isLoading) return <Loading />;
  const settings = q.data ?? { enabled: true, sheet: true, tour: true, checklist: true, hints: true, hints_for_all: false, min_cohort: 5 };
  const onChange = (part: SwitchPart, v: boolean) =>
    save.mutate({ [part]: v }, { onSuccess: () => toast.success(t("welcome.admin.saved")), onError: () => toast.error(t("welcome.admin.saveFailed")) });
  return (
    <div className="flex flex-col gap-4">
      <Card variant="plain" className="py-0">
        <ul>
          {MAIN.map((m) => (
            <SwitchRow key={m.part} {...m} settings={settings} onChange={onChange} busy={save.isPending} />
          ))}
        </ul>
      </Card>
      <div>
        <Button variant="ghost" className="pointer-coarse:min-h-11" aria-expanded={advanced} aria-controls={advId} onClick={() => setAdvanced((v) => !v)} data-testid="welcome-advanced">
          <ChevronDown aria-hidden className={advanced ? "rotate-180" : ""} />
          {t("welcome.admin.advanced")}
        </Button>
      </div>
      {advanced ? (
        <div id={advId} className="flex flex-col gap-4">
          <Card variant="plain" className="py-0">
            <ul>
              <SwitchRow part="hints_for_all" copy="hints_for_all" settings={settings} onChange={onChange} busy={save.isPending} />
            </ul>
          </Card>
          <Card variant="plain" className="gap-3 px-4 py-4" data-testid="welcome-preview">
            <div>
              <p className="type-headline text-label-1">{t("welcome.admin.preview.title")}</p>
              <p className="type-footnote text-label-2">{t("welcome.admin.preview.body")}</p>
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <label htmlFor={selectId} className="flex flex-col gap-1 type-footnote text-label-2">
                {t("welcome.admin.preview.audience")}
                <SelectField id={selectId} value={audience} onChange={(e) => setAudience(e.target.value as Audience)} className="min-w-48" data-testid="welcome-preview-audience">
                  {AUDIENCES.map((a) => (
                    <option key={a} value={a}>
                      {t(audienceKey(a))}
                    </option>
                  ))}
                </SelectField>
              </label>
              <Button variant="outline" className="pointer-coarse:min-h-11" onClick={() => openSheet({ mode: "preview", kind: "sheet", audience })} data-testid="welcome-preview-open">
                {t("welcome.admin.preview.open")}
              </Button>
            </div>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
