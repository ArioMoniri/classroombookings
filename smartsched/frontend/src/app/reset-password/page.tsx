import { Suspense } from "react";
import { ResetPassword } from "@/components/admin/reset-password";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.resetPassword");

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPassword />
    </Suspense>
  );
}
