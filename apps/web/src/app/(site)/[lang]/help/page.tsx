import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { api, type Lang } from "@/lib/api";
import { dict, isLang } from "@/lib/i18n";

export const metadata: Metadata = { title: "Help Center" };

async function Articles({ lang }: { lang: Lang }) {
  let articles;
  try {
    articles = await api.help(lang);
  } catch {
    return (
      <p className="text-slate">
        {lang === "fr"
          ? "Le centre d'aide est momentanément indisponible. Réessayez dans un instant."
          : "The Help Center is temporarily unavailable. Try again in a moment."}
      </p>
    );
  }
  return (
    <div className="grid gap-12 md:grid-cols-[16rem_1fr]">
      <nav aria-label="Articles" className="md:sticky md:top-6 md:self-start">
        <ul className="space-y-2">
          {articles.map((a) => (
            <li key={a.id}>
              <a href={`#${a.id}`} className="text-night hover:text-amber-deep">
                {a.title}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <div className="space-y-16">
        {articles.map((a) => (
          <article key={a.id} id={a.id} className="scroll-mt-6">
            <h2 className="font-display text-3xl font-bold text-night">{a.title}</h2>
            <div className="mt-6 space-y-6">
              {a.sections.map((s) => (
                <section key={s.id} id={s.id.replace("#", "-")}>
                  <h3 className="font-display text-xl font-semibold text-night">{s.heading}</h3>
                  <p className="mt-2 max-w-[68ch] leading-relaxed">{s.text}</p>
                  <p className="mt-1 text-xs text-slate/60">{s.id}</p>
                </section>
              ))}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

export default async function HelpPage({ params }: PageProps<"/[lang]/help">) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const t = dict(lang);
  return (
    <div className="mx-auto max-w-6xl px-5 py-14">
      <h1 className="font-display text-5xl font-extrabold tracking-tight text-night">{t.help.title}</h1>
      <p className="mt-4 max-w-[60ch] text-lg">{t.help.lead}</p>
      <div className="mt-12">
        <Suspense fallback={<p className="text-slate/70">…</p>}>
          <Articles lang={lang} />
        </Suspense>
      </div>
    </div>
  );
}
