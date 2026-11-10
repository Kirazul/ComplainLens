import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { RateForm } from "@/components/site/rate-form";
import { dict, isLang } from "@/lib/i18n";

export const metadata: Metadata = { title: "Rate a ride" };

export default async function RatePage({ params }: PageProps<"/[lang]/rate">) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const t = dict(lang);
  return (
    <div className="mx-auto max-w-3xl px-5 py-14">
      <h1 className="font-display text-5xl font-extrabold tracking-tight text-night">{t.rate.title}</h1>
      <div className="mt-10">
        <Suspense fallback={<div className="h-96" />}>
          <RateForm lang={lang} t={t.rate} contact={t.contact} />
        </Suspense>
      </div>
    </div>
  );
}
