import type { Metadata } from "next";
import { Suspense } from "react";
import { ChangePasswordForm } from "@/components/auth/change-password-form";

export const metadata: Metadata = { title: "Change password" };

export default function ChangePasswordPage() {
  return (
    <main className="scene flex min-h-dvh flex-col justify-center bg-fixed px-4 py-10 sm:items-center">
      <Suspense fallback={null}>
        <ChangePasswordForm />
      </Suspense>
    </main>
  );
}
