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
          {/* Phones: brand and sign-in on the first row, links on a second row that never wraps
              (a fixed height, whatever the font). Desktop: one row. */}
          <nav
            aria-label="Console"
            className="mx-auto grid max-w-7xl grid-cols-[1fr_auto] items-center gap-x-6 gap-y-2 px-5 py-3 md:flex"
          >
            <Link href="/console" className="text-lg font-semibold tracking-tight md:mr-auto">
              ComplaintLens <span className="font-normal text-muted">for LunaGo</span>
            </Link>
            <div className="col-span-2 row-start-2 flex gap-6 overflow-x-auto whitespace-nowrap text-sm md:order-none">
              <Link href="/console" className="hover:text-sent">
                Inbox
              </Link>
              <Link href="/console/insights" className="hover:text-sent">
                Insights
              </Link>
              <Link href="/console/annotate" className="hover:text-sent">
                Annotate
              </Link>
              <Link href="/en" className="hover:text-sent">
                Customer site
              </Link>
            </div>
            <div className="col-start-2 row-start-1">
              <OperatorControl />
            </div>
          </nav>
        </header>
        {children}
      </body>
    </html>
  );
}
