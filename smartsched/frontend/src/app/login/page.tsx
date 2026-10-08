import type { Metadata } from "next";
import { Suspense } from "react";
import { LoginForm } from "@/components/auth/login-form";

export const metadata: Metadata = { title: "Sign in" };

/* The login canvas paints the scene mesh itself (liquid-glass.md §3, §16.3): the glass card needs
   something to refract, so no flat page background here. */
export default function LoginPage() {
  return (
    <main className="scene flex min-h-dvh flex-col justify-center bg-fixed px-4 py-10 sm:items-center">
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </main>
  );
}
