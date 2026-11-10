import type { Metadata } from "next";
import { IBM_Plex_Sans } from "next/font/google";

import { ConsoleShell } from "@/components/console/shell";
import "../../globals.css";

const plex = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-ibm-plex",
});

export const metadata: Metadata = {
  title: { default: "ComplaintLens console", template: "%s · ComplaintLens" },
  description: "LunaGo's support console: every customer conversation, how the AI understood it, and the team's replies.",
  robots: { index: false },
};

export default function ConsoleLayout({ children }: LayoutProps<"/console">) {
  return (
    <html lang="en" className={plex.variable}>
      <body className="console min-h-screen bg-desk font-plex text-ink [font-variant-numeric:tabular-nums]">
        <ConsoleShell>{children}</ConsoleShell>
      </body>
    </html>
  );
}
