import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { TrackView } from "@/components/site/track-view";
import { dict, isLang } from "@/lib/i18n";

export const metadata: Metadata = { title: "Your request", robots: { index: false } };

// The ticket ID and tracking key are only known at request time, so everything that reads them
// sits inside <Suspense> (Cache Components streams it after the static shell).
async function Tracker({
  params,
  searchParams,
}: {
  params: Promise<{ lang: string; id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [{ lang, id }, { k }] = await Promise.all([params, searchParams]);
  if (!isLang(lang)) notFound();
  const t = dict(lang);
  const ticketId = Number(id);
  return (
    <>
      <h1 className="font-display text-5xl font-extrabold tracking-tight text-night">{t.track.title}</h1>
      <div className="mt-10">
        {Number.isInteger(ticketId) && typeof k === "string" ? (
          <TrackView id={ticketId} trackKey={k} lang={lang} t={t} />
        ) : (
          <p className="text-lg">{t.track.notFound}</p>
        )}
      </div>
    </>
  );
}

export default function TrackPage({ params, searchParams }: PageProps<"/[lang]/track/[id]">) {
  return (
    <div className="mx-auto max-w-3xl px-5 py-14">
      <Suspense fallback={<p className="text-slate/70">…</p>}>
        <Tracker params={params} searchParams={searchParams} />
      </Suspense>
    </div>
  );
}
