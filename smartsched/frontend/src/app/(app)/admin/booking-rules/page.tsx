import { PoliciesAdmin } from "@/components/policies/policies-admin";
import { localizedTitle } from "@/lib/i18n/server";
import { BookingRulesTitle } from "./title";

export const generateMetadata = localizedTitle("titles.adminBookingRules");

/**
 * PER-F07 (fix-h-2026-10-18): Kurulum › Rezervasyon kuralları, next to Onay kuralları. It used to be a tab under
 * Ayarlar; /settings?tab=booking-rules redirects here.
 */
export default function Page() {
  return (
    <div className="flex flex-col gap-6" data-testid="booking-rules">
      <BookingRulesTitle />
      <PoliciesAdmin />
    </div>
  );
}
