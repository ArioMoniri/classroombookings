"use client";
/** Shared frame for the public pages (/setup, /reset-password): scene canvas + one regular glass card. */
import type { ReactNode } from "react";
import { GlassPanel } from "@/components/ui/glass-panel";
import { useOrgPublic } from "@/lib/api/crbs";

export function PublicCard({ title, lead, children, wide }: { title: string; lead?: ReactNode; children: ReactNode; wide?: boolean }) {
  const org = useOrgPublic();
  return (
    <main className="scene flex min-h-dvh flex-col justify-center bg-fixed px-4 py-10 sm:items-center">
      <GlassPanel material="regular" radius="2xl" padding="lg" className={wide ? "w-full sm:max-w-xl" : "w-full sm:max-w-md"}>
        <div className="mb-5 flex items-center gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element -- uploaded by an administrator, served by the backend */}
          {org.data?.logo_url ? <img src={org.data.logo_url} alt="" className="h-9 max-w-32 object-contain" /> : null}
          {org.data?.name ? <p className="type-headline text-label-2">{org.data.name}</p> : null}
        </div>
        <h1 className="type-title-2 text-label-1">{title}</h1>
        {lead ? <p className="mt-1 mb-5 type-callout text-label-2">{lead}</p> : <div className="mb-5" />}
        {children}
      </GlassPanel>
    </main>
  );
}
