import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ContactForm } from "@/components/site/contact-form";
import { dict, isLang } from "@/lib/i18n";

export const metadata: Metadata = { title: "Contact support" };

export default async function ContactPage({ params }: PageProps<"/[lang]/contact">) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const t = dict(lang);
  return (
    <div className="mx-auto max-w-3xl px-5 py-14">
      <h1 className="font-display text-5xl font-extrabold tracking-tight text-night">{t.contact.title}</h1>
      <p className="mt-4 max-w-[60ch] text-lg">{t.contact.lead}</p>
      <div className="mt-10">
        <ContactForm lang={lang} t={t.contact} />
      </div>
    </div>
  );
}
