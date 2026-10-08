import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { cookies } from "next/headers";
import { DEFAULT_LOCALE, LOCALE_COOKIE, isLocale } from "@/lib/i18n";
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
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    /* --scene (liquid-glass.md §3, §16.6): the browser chrome continues the scene behind the glass */
    { media: "(prefers-color-scheme: light)", color: "#eef0f4" },
    { media: "(prefers-color-scheme: dark)", color: "#0d0e12" },
  ],
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const jar = await cookies();
  const cookieLocale = jar.get(LOCALE_COOKIE)?.value;
  const locale = isLocale(cookieLocale) ? cookieLocale : DEFAULT_LOCALE;
  return (
    <html lang={locale} suppressHydrationWarning className={`${inter.variable} ${mono.variable} h-full antialiased`}>
      <head>
        {/* before first paint: in-app Reduce motion / Reduce transparency and the accent preset (no flash) */}
        <script dangerouslySetInnerHTML={{ __html: appearanceHeadScript }} />
      </head>
      <body className="flex min-h-full flex-col">
        <Providers locale={locale}>{children}</Providers>
      </body>
    </html>
  );
}
