import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ContactForm } from "@/components/site/contact-form";
import { FORUM_URL, SUPPORT_EMAIL } from "@/lib/api";
import { dict, isLang } from "@/lib/i18n";

export const metadata: Metadata = { title: "Contact support" };

export default async function ContactPage({ params }: PageProps<"/[lang]/contact">) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const t = dict(lang);
  const c = t.contact.channels;
  const link = "font-semibold text-night underline decoration-lilac decoration-2 underline-offset-4 hover:decoration-amber";
  return (
    <div className="mx-auto grid max-w-6xl gap-14 px-5 py-14 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <div>
        <h1 className="font-display text-5xl font-extrabold tracking-tight text-night">{t.contact.title}</h1>
        <p className="mt-4 max-w-[60ch] text-lg">{t.contact.lead}</p>
        <div className="mt-10">
          <ContactForm lang={lang} t={t.contact} />
        </div>
      </div>
      <aside aria-labelledby="other-ways" className="lg:pt-24">
        <h2 id="other-ways" className="font-display text-2xl font-bold text-night">
          {t.contact.otherWays}
        </h2>
        <dl className="mt-6 space-y-6">
          <div>
            <dt className="font-semibold text-night">{c.chat[0]}</dt>
            <dd className="mt-1">{c.chat[1]}</dd>
            <dd className="mt-2">
              <Link href={`/${lang}/contact/?chat=open`} className={link}>
                {c.chat[2]}
              </Link>
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-night">{c.rate[0]}</dt>
            <dd className="mt-1">{c.rate[1]}</dd>
            <dd className="mt-2">
              <Link href={`/${lang}/rate`} className={link}>
                {c.rate[2]}
              </Link>
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-night">{c.email[0]}</dt>
            <dd className="mt-1">{c.email[1]}</dd>
            <dd className="mt-2">
              <a href={`mailto:${SUPPORT_EMAIL}`} className={`${link} break-all`}>
                {SUPPORT_EMAIL}
              </a>
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-night">{c.forum[0]}</dt>
            <dd className="mt-1">{c.forum[1]}</dd>
            <dd className="mt-2">
              <a href={FORUM_URL} className={link}>
                {c.forum[2]}
              </a>
            </dd>
          </div>
        </dl>
      </aside>
    </div>
  );
}
