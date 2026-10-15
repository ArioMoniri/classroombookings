import { Suspense } from "react";
import { ChangePasswordForm } from "@/components/auth/change-password-form";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.changePassword");

export default function ChangePasswordPage() {
  return (
    <main className="scene flex min-h-dvh flex-col justify-center bg-fixed px-4 py-10 sm:items-center">
      <Suspense fallback={null}>
        <ChangePasswordForm />
      </Suspense>
    </main>
  );
}
