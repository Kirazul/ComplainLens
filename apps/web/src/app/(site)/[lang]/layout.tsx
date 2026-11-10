import type { Metadata } from "next";
import { Atkinson_Hyperlegible_Next, Bricolage_Grotesque } from "next/font/google";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { LunaGoLogo } from "@/components/brand";
import { AccountButton } from "@/components/site/account";
import { ChatWidget } from "@/components/site/chat-widget";
import { LangSwitch } from "@/components/site/lang-switch";
import { FORUM_URL } from "@/lib/api";
import { dict, isLang, LANGS } from "@/lib/i18n";
import "../../globals.css";

const bricolage = Bricolage_Grotesque({ subsets: ["latin"], variable: "--font-bricolage" });
const atkinson = Atkinson_Hyperlegible_Next({ subsets: ["latin"], variable: "--font-atkinson" });

export const metadata: Metadata = {
  title: { default: "LunaGo", template: "%s · LunaGo" },
  description: "Fictional ride company for a university NLP project (ComplaintLens).",
};

export function generateStaticParams() {
  return LANGS.map((lang) => ({ lang }));
}

export default async function SiteLayout({ children, params }: LayoutProps<"/[lang]">) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const t = dict(lang);
  const link = "hover:text-amber";
  return (
    <html lang={lang} className={`${bricolage.variable} ${atkinson.variable}`}>
      <body className="flex min-h-screen flex-col bg-paper font-body text-slate">
        <header className="bg-night text-paper">
          {/* Phones: logo and account on the first row, links below. Desktop: one row. */}
          <nav aria-label="Main" className="mx-auto grid max-w-6xl grid-cols-[1fr_auto] items-center gap-x-8 gap-y-3 px-5 py-4 md:flex">
            <Link href={`/${lang}`} aria-label="LunaGo" className="md:mr-auto">
              <LunaGoLogo />
            </Link>
            <div className="col-span-2 row-start-2 flex flex-wrap items-center gap-x-6 gap-y-2 md:order-none md:gap-x-8">
              <Link href={`/${lang}/book`} className={link}>
                {t.nav.book}
              </Link>
              <Link href={`/${lang}/rides`} className={link}>
                {t.nav.rides}
              </Link>
              <Link href={`/${lang}/contact`} className={link}>
                {t.nav.contact}
              </Link>
              <Suspense fallback={null}>
                <LangSwitch current={lang} label={t.nav.switch} />
              </Suspense>
            </div>
            <div className="col-start-2 row-start-1">
              <AccountButton lang={lang} t={t.nav} />
            </div>
          </nav>
        </header>
        <main className="flex-1">{children}</main>
        <footer className="border-t border-lilac/60 bg-paper">
          <div className="mx-auto flex max-w-6xl flex-wrap items-baseline gap-x-6 gap-y-2 px-5 py-6 pb-24 text-sm text-slate/80">
            <p className="max-w-[70ch]">{t.footer}</p>
            <Link href={`/${lang}/rate`} className="underline underline-offset-4 hover:text-night">
              {t.contact.rate}
            </Link>
            <a href={FORUM_URL} className="underline underline-offset-4 hover:text-night">
              {t.contact.forum}
            </a>
            <Link href="/console" className="underline underline-offset-4 hover:text-night">
              {t.staff}
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
