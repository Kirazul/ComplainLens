"use client";

import { useSearchParams } from "next/navigation";
import { useMemo } from "react";

import { Moon } from "@/components/moon";
import { Messages, ReplyBox, useConversation } from "@/components/site/conversation";
import type { Lang } from "@/lib/api";
import type { Dict } from "@/lib/i18n";

// A customer's conversation as a page: where it stands, every message, and a reply box.
function TrackView({ id, trackKey, lang, t }: { id: number; trackKey: string; lang: Lang; t: Dict }) {
  const ref = useMemo(() => ({ id, key: trackKey, number: "" }), [id, trackKey]);
  const live = useConversation(ref);
  const ticket = live.data;

  if (live.missing) return <p className="text-lg">{t.track.notFound}</p>;
  if (!ticket) return <p className="text-slate">…</p>;

  const done = ticket.phases.filter((p) => p.done).length as 0 | 1 | 2 | 3 | 4;
  const state =
    {
      processing: t.track.waiting,
      escalated: t.track.escalated,
      awaiting_approval: t.track.review,
      no_reply: t.track.noReply,
      closed: t.track.closed,
    }[ticket.status as string] ?? t.phases.answered;
  const date = new Intl.DateTimeFormat(lang === "fr" ? "fr-CA" : "en-CA", { dateStyle: "medium" }).format(
    new Date(ticket.received_at),
  );

  return (
    <div>
      <div className="flex items-center gap-5 rounded-3xl bg-night p-6 text-paper sm:p-7">
        <Moon phase={done} size={72} title={`${done}/4`} />
        <div>
          <p className="text-lilac">
            {t.track.ticket} {ticket.number} · {date}
          </p>
          <p className="mt-1 font-display text-2xl font-bold sm:text-3xl" aria-live="polite">
            {state}
          </p>
        </div>
      </div>

      <div className="mt-8">
        <Messages data={ticket} t={t.conversation} size="page" />
      </div>
      <div className="mt-6">
        <ReplyBox onSend={live.send} sending={live.sending} failed={live.failed} t={t.conversation} />
      </div>
      <p className="mt-8 text-sm text-slate/80">{t.track.keep}</p>
    </div>
  );
}

/** Reads ?id=…&k=… from the URL (static export: no server-side params). */
export function TrackFromQuery({ lang, t }: Readonly<{ lang: Lang; t: Dict }>) {
  const query = useSearchParams();
  const id = Number(query.get("id"));
  const key = query.get("k");
  if (!Number.isInteger(id) || id <= 0 || !key) return <p className="text-lg">{t.track.notFound}</p>;
  return <TrackView id={id} trackKey={key} lang={lang} t={t} />;
}
