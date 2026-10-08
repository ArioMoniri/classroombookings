import type { Metadata } from "next";
import { Suspense } from "react";
import { ResetPassword } from "@/components/admin/reset-password";

export const metadata: Metadata = { title: "Reset password" };

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPassword />
    </Suspense>
  );
}
