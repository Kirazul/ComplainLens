import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { TrackFromQuery } from "@/components/site/track-view";
import { dict, isLang } from "@/lib/i18n";

export const metadata: Metadata = { title: "Your request", robots: { index: false } };

export default async function TrackPage({ params }: PageProps<"/[lang]/track">) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const t = dict(lang);
  return (
    <div className="mx-auto max-w-3xl px-5 py-14">
      <h1 className="font-display text-5xl font-extrabold tracking-tight text-night">{t.track.title}</h1>
      <div className="mt-10">
        <Suspense fallback={<p className="text-slate/70">…</p>}>
          <TrackFromQuery lang={lang} t={t} />
        </Suspense>
      </div>
    </div>
  );
}
