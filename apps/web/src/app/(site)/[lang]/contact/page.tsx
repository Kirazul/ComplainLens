import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { ContactForm } from "@/components/site/contact-form";
import { FORUM_URL, SUPPORT_EMAIL } from "@/lib/api";
import { dict, isLang } from "@/lib/i18n";

export const metadata: Metadata = { title: "Contact" };

export default async function ContactPage({ params }: PageProps<"/[lang]/contact">) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const t = dict(lang);
  const c = t.contact;
  const link = "font-semibold text-night underline decoration-lilac decoration-2 underline-offset-4 hover:decoration-amber";
  const ways = [
    [c.chat, c.chatHint, <Link key="chat" href={`/${lang}/contact/?chat=open`} scroll={false} className={link}>{t.chat.open}</Link>],
    [c.emailUs, c.emailHint, <a key="mail" href={`mailto:${SUPPORT_EMAIL}`} className={`${link} break-all`}>{SUPPORT_EMAIL}</a>],
    [c.forum, c.forumHint, <a key="forum" href={FORUM_URL} className={link}>GitHub Discussions</a>],
    [c.rate, c.rateHint, <Link key="rate" href={`/${lang}/rate`} className={link}>{c.rate}</Link>],
  ] as const;
  return (
    <div className="mx-auto grid max-w-6xl gap-14 px-5 py-14 lg:grid-cols-[minmax(0,1fr)_19rem]">
      <div>
        <h1 className="font-display text-5xl font-extrabold tracking-tight text-night">{c.title}</h1>
        <p className="mt-4 max-w-[55ch] text-lg">{c.lead}</p>
        <div className="mt-10">
          <Suspense fallback={<div className="h-96" />}>
            <ContactForm lang={lang} t={c} />
          </Suspense>
        </div>
      </div>
      <aside aria-labelledby="other-ways" className="lg:pt-24">
        <h2 id="other-ways" className="font-display text-2xl font-bold text-night">
          {c.other}
        </h2>
        <dl className="mt-6 space-y-6">
          {ways.map(([title, hint, action]) => (
            <div key={title}>
              <dt className="font-semibold text-night">{title}</dt>
              <dd className="mt-1">{hint}</dd>
              <dd className="mt-2">{action}</dd>
            </div>
          ))}
        </dl>
      </aside>
    </div>
  );
}
