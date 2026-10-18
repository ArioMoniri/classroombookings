import { TermWeeksEditor } from "@/components/admin/term-weeks-editor";
import { WeeksAdmin } from "@/components/admin/weeks-admin";
import { SeasonProfiles } from "@/components/seasons/season-profiles";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.adminWeeks");

export default function Page() {
  return (
    <div className="flex flex-col gap-8">
      <WeeksAdmin />
      {/* RF-09: the term's week calendar (Ders / Sınav / Tatil / Bütünleme per week) */}
      <TermWeeksEditor />
      {/* AS-15: season profiles and the term's period calendar (ADMIN; hidden on 403) */}
      <SeasonProfiles />
    </div>
  );
}
