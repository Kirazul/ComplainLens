import type { Metadata } from "next";
import { Atkinson_Hyperlegible_Next, Bricolage_Grotesque } from "next/font/google";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { ChatWidget } from "@/components/site/chat-widget";
import { LangSwitch } from "@/components/site/lang-switch";
import { FORUM_URL } from "@/lib/api";
import { dict, isLang, LANGS } from "@/lib/i18n";
import "../../globals.css";

const bricolage = Bricolage_Grotesque({ subsets: ["latin"], variable: "--font-bricolage" });
const atkinson = Atkinson_Hyperlegible_Next({ subsets: ["latin"], variable: "--font-atkinson" });

export const metadata: Metadata = {
  title: { default: "LunaGo", template: "%s · LunaGo" },
  description: "Rides and late-night food delivery in Montréal (fictional company, NLP project).",
};

export function generateStaticParams() {
  return LANGS.map((lang) => ({ lang }));
}

export default async function SiteLayout({ children, params }: LayoutProps<"/[lang]">) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const t = dict(lang);
  return (
    <html lang={lang} className={`${bricolage.variable} ${atkinson.variable}`}>
      <body className="flex min-h-screen flex-col bg-paper font-body text-slate">
        <header className="bg-night text-paper">
          {/* Mobile: logo and language on the first row, links below. Desktop: one row. */}
          <nav
            aria-label="Main"
            className="mx-auto grid max-w-6xl grid-cols-[1fr_auto] items-center gap-x-8 gap-y-3 px-5 py-4 md:flex"
          >
            <Link
              href={`/${lang}`}
              className="font-display text-2xl font-extrabold tracking-tight md:mr-auto"
            >
              Luna<span className="text-amber">Go</span>
            </Link>
            <div className="col-span-2 row-start-2 flex flex-wrap gap-x-6 gap-y-2 md:order-none md:gap-x-8">
              <Link href={`/${lang}/help`} className="hover:text-amber">
                {t.nav.help}
              </Link>
              <Link href={`/${lang}/rate`} className="hover:text-amber">
                {t.nav.rate}
              </Link>
              <a href={FORUM_URL} className="hover:text-amber">
                {t.nav.community}
              </a>
              <Link href={`/${lang}/contact`} className="hover:text-amber">
                {t.nav.contact}
              </Link>
            </div>
            <div className="col-start-2 row-start-1">
              <Suspense fallback={null}>
                <LangSwitch current={lang} label={t.nav.switch} />
              </Suspense>
            </div>
          </nav>
        </header>
        <main className="flex-1">{children}</main>
        <footer className="border-t border-lilac/60 bg-paper">
          <div className="mx-auto flex max-w-6xl flex-wrap items-baseline gap-x-8 gap-y-2 px-5 py-6 pb-24 text-sm text-slate/80">
            <p className="max-w-[80ch]">{t.footer}</p>
            <Link href="/console" className="underline underline-offset-4 hover:text-night">
              {lang === "fr" ? "Console du personnel (ComplaintLens)" : "Staff console (ComplaintLens)"}
            </Link>
          </div>
        </footer>
        <Suspense fallback={null}>
          <ChatWidget lang={lang} t={t} />
        </Suspense>
      </body>
    </html>
  );
}
