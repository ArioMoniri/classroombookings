import type { Metadata } from "next";
import { Suspense } from "react";
import { LoginForm } from "@/components/auth/login-form";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <main className="flex min-h-dvh items-center justify-center bg-background px-4 py-10">
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </main>
  );
}
