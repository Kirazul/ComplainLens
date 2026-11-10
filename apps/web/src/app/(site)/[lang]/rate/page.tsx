import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { RateForm } from "@/components/site/rate-form";
import { dict, isLang } from "@/lib/i18n";

export const metadata: Metadata = { title: "Rate a trip" };

export default async function RatePage({ params }: PageProps<"/[lang]/rate">) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const t = dict(lang);
  return (
    <div className="mx-auto max-w-3xl px-5 py-14">
      <h1 className="font-display text-5xl font-extrabold tracking-tight text-night">{t.rate.title}</h1>
      <p className="mt-4 max-w-[60ch] text-lg">{t.rate.lead}</p>
      <div className="mt-10">
        <RateForm lang={lang} t={t.rate} contact={t.contact} />
      </div>
    </div>
  );
}
