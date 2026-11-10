import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { loadHelpCenter } from "@/lib/help-center";
import { dict, isLang } from "@/lib/i18n";

export const metadata: Metadata = { title: "Help Center" };

// Built from company/help_center/ at build time: the exact policies the AI replies quote.
export default async function HelpPage({ params }: PageProps<"/[lang]/help">) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const t = dict(lang);
  const articles = loadHelpCenter(lang);
  return (
    <div className="mx-auto max-w-6xl px-5 py-14">
      <h1 className="font-display text-5xl font-extrabold tracking-tight text-night">{t.help.title}</h1>
      <p className="mt-4 max-w-[60ch] text-lg">{t.help.lead}</p>
      <div className="mt-12 grid gap-12 md:grid-cols-[16rem_1fr]">
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
    </div>
  );
}
