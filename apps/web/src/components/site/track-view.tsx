"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Moon } from "@/components/moon";
import { api, type Lang, type PublicTicket } from "@/lib/api";
import type { Dict } from "@/lib/i18n";

const FINAL = new Set(["auto_send", "answered", "awaiting_approval", "escalated", "no_reply", "closed"]);

export function TrackView({
  id,
  trackKey,
  lang,
  t,
}: {
  id: number;
  trackKey: string;
  lang: Lang;
  t: Dict;
}) {
  const [ticket, setTicket] = useState<PublicTicket | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll(attempt: number) {
      try {
        const data = await api.publicTicket(id, trackKey);
        if (stop) return;
        setTicket(data);
        // Keep polling while processing, and slowly afterwards for an agent's approved reply.
        const delay = FINAL.has(data.status) ? 8000 : 1200;
        if (attempt < 400) timer = setTimeout(() => poll(attempt + 1), delay);
      } catch {
        if (!stop) setMissing(true);
      }
    }
    poll(0);
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [id, trackKey]);

  if (missing) return <p className="text-lg">{t.track.notFound}</p>;
  if (!ticket) return <p className="text-slate">…</p>;

  const done = ticket.phases.filter((p) => p.done).length as 0 | 1 | 2 | 3 | 4;
  const statusLine =
    ticket.status === "processing"
      ? t.track.waiting
      : ticket.status === "escalated"
        ? t.track.escalated
        : ticket.status === "awaiting_approval"
          ? t.track.review
          : ticket.status === "no_reply"
            ? t.track.noReply
            : null;
  const date = new Intl.DateTimeFormat(lang === "fr" ? "fr-CA" : "en-CA", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(ticket.received_at));

  return (
    <div>
      <div className="flex flex-wrap items-center gap-6 rounded-3xl bg-night p-7 text-paper">
        <Moon phase={done} size={88} title={`${done}/4`} />
        <div>
          <p className="text-lilac">
            {t.track.ticket} {ticket.number} · {date}
          </p>
          <p className="mt-1 font-display text-3xl font-bold" aria-live="polite">
            {statusLine ?? t.phases.answered}
          </p>
        </div>
      </div>

      <ol className="mt-6 grid gap-3 sm:grid-cols-4" aria-label={t.home.phasesTitle}>
        {ticket.phases.map((p, i) => (
          <li
            key={p.name}
            className={`flex items-center gap-3 rounded-2xl px-4 py-3 ${
              p.done ? "bg-white text-night ring-1 ring-lilac" : "text-slate/80"
            }`}
          >
            <Moon phase={(p.done ? i + 1 : 0) as 0 | 1 | 2 | 3 | 4} size={28} surface="day" />
            <span className="font-semibold">{t.phases[p.name]}</span>
          </li>
        ))}
      </ol>

      <div className="mt-10 space-y-6">
        {ticket.replies.map((r, i) => (
          <article key={i} className="rounded-3xl bg-white p-7 ring-1 ring-lilac">
            <h2 className="font-display text-lg font-semibold text-night">{t.track.reply}</h2>
            <p className="mt-3 whitespace-pre-line leading-relaxed text-night">{stripCitations(r.body)}</p>
          </article>
        ))}
      </div>
      <p className="mt-8 text-sm text-slate">{t.track.emailNote}</p>
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

// Citations like [HC-FARES#4] are for the console and the verifier, not for customers.
function stripCitations(text: string): string {
  return text.replace(/\s?\[(?:HC-[A-Z]+#\d+|F\d+)\]/g, "");
}
