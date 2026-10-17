import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import { Inter, JetBrains_Mono } from "next/font/google";
import { requestLocale } from "@/lib/i18n/server";
import { Providers } from "@/components/providers";
import { appearanceHeadScript } from "@/components/shell/appearance-init";
import "./globals.css";

/* Variable Inter with the optical-size axis (liquid-glass.md §6): non-Apple platforms get the Display cut
   at title sizes through `font-optical-sizing: auto` (globals.css); Apple platforms use SF Pro first. */
const inter = Inter({ variable: "--font-inter", subsets: ["latin", "latin-ext"], display: "swap", axes: ["opsz"] });
const mono = JetBrains_Mono({ variable: "--font-jetbrains", subsets: ["latin", "latin-ext"], display: "swap" });

export const metadata: Metadata = {
  title: { default: "SmartSched", template: "%s · SmartSched" },
  description: "AI classroom planner — import, optimise, converse, publish.",
  icons: {
    icon: [
      { url: "/favicon.svg", type: "image/svg+xml" },
      { url: "/icons/icon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/icons/icon-16.png", sizes: "16x16", type: "image/png" },
    ],
    apple: "/apple-touch-icon.png",
  },
  manifest: "/site.webmanifest",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // MOBILE.md M-06: without cover the env(safe-area-inset-*) paddings are 0 on iOS (notch, home indicator)
  viewportFit: "cover",
  // T-R1-02 (R1-A-03): Chromium Android keeps the layout viewport when the keyboard opens unless told to resize
  // it; with it, 100dvh shrinks with the keyboard, so a bottom sheet's sticky footer stays above the keys and a
  // focused field scrolls clear of it (sign-in.md §5.4 asked for it on /login only; every app sheet needs it)
  interactiveWidget: "resizes-content",
  themeColor: [
    /* --scene (liquid-glass.md §3, §16.6): the browser chrome continues the scene behind the glass */
    { media: "(prefers-color-scheme: light)", color: "#eef0f4" },
    { media: "(prefers-color-scheme: dark)", color: "#0d0e12" },
  ],
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await requestLocale();
  // the per-request CSP nonce from src/proxy.ts (docs/SECURITY.md F9): inline scripts without it do not run
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html lang={locale} suppressHydrationWarning className={`${inter.variable} ${mono.variable} h-full antialiased`}>
      <head>
        {/* before first paint: in-app Reduce motion / Reduce transparency and the accent preset (no flash) */}
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: appearanceHeadScript }} />
      </head>
      <body className="flex min-h-full flex-col">
        <Providers locale={locale} nonce={nonce}>{children}</Providers>
      </body>
    </html>
  );
}
