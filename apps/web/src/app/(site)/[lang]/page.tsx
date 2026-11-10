import Link from "next/link";
import { notFound } from "next/navigation";

import { Moon } from "@/components/moon";
import { dict, isLang } from "@/lib/i18n";

const TOPICS = {
  en: [
    ["I was charged twice", "HC-FARES"],
    ["My driver cancelled or was late", "HC-CANCEL"],
    ["I left something in the car", "HC-LOST"],
    ["My food order was late or incomplete", "HC-DELIVERY"],
    ["I felt unsafe during a ride", "HC-SAFETY"],
    ["I can't log in to my account", "HC-APP"],
  ],
  fr: [
    ["J'ai été facturé deux fois", "HC-FARES"],
    ["Mon chauffeur a annulé ou était en retard", "HC-CANCEL"],
    ["J'ai oublié un objet dans la voiture", "HC-LOST"],
    ["Ma commande était en retard ou incomplète", "HC-DELIVERY"],
    ["Je ne me suis pas senti en sécurité", "HC-SAFETY"],
    ["Je n'arrive pas à me connecter", "HC-APP"],
  ],
} as const;

export default async function Home({ params }: PageProps<"/[lang]">) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const t = dict(lang);
  const phases = ["received", "understood", "routed", "answered"] as const;

  return (
    <>
      <section className="bg-night text-paper">
        <div className="mx-auto grid max-w-6xl gap-12 px-5 pb-20 pt-14 md:grid-cols-[1.3fr_1fr] md:items-end">
          <div>
            <h1 className="max-w-[16ch] text-balance font-display text-5xl font-extrabold leading-[1.02] tracking-tight md:text-7xl">
              {t.home.title}
            </h1>
            <p className="mt-6 max-w-[52ch] text-lg text-lilac">{t.home.lead}</p>
          </div>
          <div className="rounded-3xl bg-night-soft/70 p-7 ring-1 ring-lilac/20">
            <h2 className="font-display text-2xl font-bold">{t.home.helpTitle}</h2>
            <p className="mt-3 text-lilac">{t.home.helpLead}</p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link
                href={`/${lang}/?chat=open`}
                scroll={false}
                className="rounded-full bg-amber px-5 py-2.5 font-semibold text-night hover:bg-paper"
              >
                {t.home.cta}
              </Link>
              <Link
                href={`/${lang}/contact`}
                className="rounded-full px-5 py-2.5 font-semibold text-paper ring-1 ring-lilac/40 hover:ring-amber"
              >
                {t.home.write}
              </Link>
            </div>
            <Link
              href={`/${lang}/help`}
              className="mt-5 inline-block text-lilac underline decoration-lilac/40 underline-offset-4 hover:text-paper"
            >
              {t.home.browse}
            </Link>
          </div>
        </div>

        <div className="border-t border-lilac/15">
          <div className="mx-auto max-w-6xl px-5 py-10">
            <h2 className="text-sm text-lilac">{t.home.phasesTitle}</h2>
            <ol className="mt-5 grid grid-cols-2 gap-6 sm:grid-cols-4">
              {phases.map((p, i) => (
                <li key={p} className="wax flex items-center gap-4" style={{ animationDelay: `${300 + i * 450}ms` }}>
                  <Moon phase={(i + 1) as 1 | 2 | 3 | 4} size={52} />
                  <span className="font-display text-lg font-semibold">{t.phases[p]}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-5 py-16">
        <h2 className="font-display text-3xl font-bold text-night">{t.home.topics}</h2>
        <ul className="mt-8 grid gap-x-10 gap-y-1 md:grid-cols-2">
          {TOPICS[lang].map(([label, id]) => (
            <li key={label}>
              <Link
                href={`/${lang}/help#${id}`}
                className="block border-b border-lilac/70 py-4 text-lg text-night hover:text-amber-deep"
              >
                {label}
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
