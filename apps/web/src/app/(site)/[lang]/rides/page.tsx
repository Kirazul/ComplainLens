import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { RequireAccount } from "@/components/site/account";
import { YourRides } from "@/components/site/your-rides";
import { dict, isLang } from "@/lib/i18n";

export const metadata: Metadata = { title: "Your rides", robots: { index: false } };

export default async function RidesPage({ params }: PageProps<"/[lang]/rides">) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const t = dict(lang);
  return (
    <div className="mx-auto max-w-4xl px-5 py-14">
      <h1 className="font-display text-5xl font-extrabold tracking-tight text-night">{t.rides.title}</h1>
      <div className="mt-10">
        <Suspense fallback={<div className="h-80" />}>
          <RequireAccount lang={lang} t={t} title={t.rides.signInTitle}>
            <YourRides lang={lang} t={t} />
          </RequireAccount>
        </Suspense>
      </div>
    </div>
  );
}
