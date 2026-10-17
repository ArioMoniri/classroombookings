"use client";
/**
 * Icons for rooms, departments and timetable weeks (CRBS shows a small icon next to each). The backend
 * stores a free `icon` string; SmartSched stores a lucide icon name from this curated set (no emoji, A3).
 */
import {
  Armchair,
  Beaker,
  BookOpen,
  Building2,
  Dumbbell,
  FlaskConical,
  GraduationCap,
  HeartPulse,
  Laptop,
  Library,
  Mic,
  Monitor,
  Music,
  Palette,
  Presentation,
  Projector,
  Stethoscope,
  Users,
  Video,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useT } from "@/lib/i18n/provider";
import { BareButton } from "@/components/shell/bare-button";

export const ICONS: Record<string, LucideIcon> = {
  presentation: Presentation,
  projector: Projector,
  monitor: Monitor,
  laptop: Laptop,
  flask: FlaskConical,
  beaker: Beaker,
  stethoscope: Stethoscope,
  "heart-pulse": HeartPulse,
  library: Library,
  book: BookOpen,
  "graduation-cap": GraduationCap,
  users: Users,
  armchair: Armchair,
  mic: Mic,
  video: Video,
  music: Music,
  palette: Palette,
  dumbbell: Dumbbell,
  wrench: Wrench,
  building: Building2,
};

export function EntityIcon({ name, className, label }: { name: string | null | undefined; className?: string; label?: string }) {
  const Icon = name ? ICONS[name] : undefined;
  if (!Icon) return null;
  return <Icon className={cn("size-3.5 shrink-0 stroke-[1.75] text-label-2", className)} aria-hidden={label ? undefined : true} aria-label={label} />;
}

/** Radio grid of the curated icons (plus "none"). */
export function IconPicker({ value, onChange, id }: { value: string | null | undefined; onChange: (v: string | null) => void; id?: string }) {
  const t = useT();
  return (
    <div id={id} role="radiogroup" aria-label={t("crbs.icons.label")} className="flex flex-wrap gap-1">
      <BareButton
        role="radio"
        aria-checked={!value}
        onClick={() => onChange(null)}
        className={cn("h-(--control-h-md) rounded-md px-2 type-footnote", !value ? "bg-tint-soft text-tint-text" : "bg-fill-2 text-label-2 hover:bg-fill-1")}
      >
        {t("crbs.common.none")}
      </BareButton>
      {Object.entries(ICONS).map(([name, Icon]) => (
        <BareButton
          key={name}
          role="radio"
          aria-checked={value === name}
          aria-label={name}
          title={name}
          onClick={() => onChange(name)}
          className={cn("flex size-(--control-h-md) items-center justify-center rounded-md", value === name ? "bg-tint-soft text-tint-text" : "bg-fill-2 text-label-2 hover:bg-fill-1")}
        >
          <Icon className="size-4 stroke-[1.75]" aria-hidden />
        </BareButton>
      ))}
    </div>
  );
}
