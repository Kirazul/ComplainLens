import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { Moon } from "@/components/moon";
import { BookingForm } from "@/components/site/booking-form";
import { dict, isLang } from "@/lib/i18n";

export default async function Home({ params }: PageProps<"/[lang]">) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const t = dict(lang);
  const phases = ["received", "understood", "routed", "answered"] as const;

  return (
    <>
      <section className="bg-night text-paper">
        <div className="mx-auto grid max-w-6xl gap-12 px-5 pb-16 pt-12 md:grid-cols-[1.1fr_1fr] md:items-center md:pb-24 md:pt-16">
          <div>
            <h1 className="text-balance font-display text-5xl font-extrabold leading-[1.02] tracking-tight md:text-7xl">
              {t.home.title}
            </h1>
            <p className="mt-6 max-w-[40ch] text-xl text-lilac">{t.home.lead}</p>
          </div>
          <div className="rounded-3xl bg-night-soft/60 p-6 ring-1 ring-lilac/20 sm:p-8">
            <Suspense fallback={<div className="h-80" />}>
              <BookingForm lang={lang} t={t.book} tone="dark" />
            </Suspense>
          </div>
        </div>
      </section>

      <section className="bg-white">
        <div className="mx-auto grid max-w-6xl gap-10 px-5 py-16 md:grid-cols-[1fr_1.2fr] md:items-center">
          <div>
            <h2 className="font-display text-4xl font-extrabold tracking-tight text-night">{t.home.helpTitle}</h2>
            <p className="mt-4 max-w-[45ch] text-lg">{t.home.helpLead}</p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link href={`/${lang}/rides`} className="rounded-full bg-night px-6 py-3 font-semibold text-paper hover:bg-night-soft">
                {t.nav.rides}
              </Link>
              <Link
                href={`/${lang}/?chat=open`}
                scroll={false}
                className="rounded-full px-6 py-3 font-semibold text-night ring-1 ring-lilac hover:ring-night"
              >
                {t.home.helpCta}
              </Link>
            </div>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate/80">{t.home.phasesTitle}</h3>
            <ol className="mt-5 grid grid-cols-2 gap-6 sm:grid-cols-4">
              {phases.map((p, i) => (
                <li key={p} className="wax flex flex-col items-start gap-3" style={{ animationDelay: `${300 + i * 450}ms` }}>
                  <Moon phase={(i + 1) as 1 | 2 | 3 | 4} size={48} surface="day" />
                  <span className="font-display text-lg font-semibold text-night">{t.phases[p]}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>
    </>
  );
}
