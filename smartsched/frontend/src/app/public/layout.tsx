import type { Metadata } from "next";

/** V2 public day view: no sign-in, no app shell; never indexed (a wall screen, not a website). */
export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return <div className="flex min-h-dvh flex-col">{children}</div>;
}
