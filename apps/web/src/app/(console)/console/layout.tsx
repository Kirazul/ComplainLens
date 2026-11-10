import type { Metadata } from "next";
import { IBM_Plex_Sans } from "next/font/google";
import Link from "next/link";

import { OperatorControl } from "@/components/console/operator";
import "../../globals.css";

const plex = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-ibm-plex",
});

export const metadata: Metadata = {
  title: { default: "ComplaintLens console", template: "%s · ComplaintLens" },
  description: "Live support console of LunaGo: every customer message, how it was understood, routed and answered.",
  robots: { index: false },
};

export default function ConsoleLayout({ children }: LayoutProps<"/console">) {
  return (
    <html lang="en" className={plex.variable}>
      <body className="console min-h-screen bg-desk font-plex text-ink [font-variant-numeric:tabular-nums]">
        <header className="border-b border-line bg-white">
          <nav
            aria-label="Console"
            className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-5 py-3"
          >
            <Link href="/console" className="mr-auto text-lg font-semibold tracking-tight">
              ComplaintLens <span className="font-normal text-muted">for LunaGo</span>
            </Link>
            <Link href="/console" className="text-sm hover:text-sent">
              Inbox
            </Link>
            <Link href="/console/insights" className="text-sm hover:text-sent">
              Insights
            </Link>
            <Link href="/console/annotate" className="text-sm hover:text-sent">
              Annotate
            </Link>
            <Link href="/en" className="text-sm hover:text-sent">
              Customer site
            </Link>
            <OperatorControl />
          </nav>
        </header>
        {children}
      </body>
    </html>
  );
}
