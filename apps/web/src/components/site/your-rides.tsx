"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useAccount } from "@/components/site/account";
import { api, type Lang, type MyConversation, type Ride } from "@/lib/api";
import { dateTime, money } from "@/lib/format";
import type { Dict } from "@/lib/i18n";

const STATE_STYLE: Record<Ride["state"], string> = {
  scheduled: "bg-lilac/40 text-night",
  in_progress: "bg-amber text-night",
  completed: "bg-night text-paper",
  cancelled: "bg-white text-slate ring-1 ring-lilac",
};

export function YourRides({ lang, t }: { lang: Lang; t: Dict }) {
  const me = useAccount();
  const path = usePathname();
  const booked = useSearchParams().get("booked") === "1";
  const [tab, setTab] = useState<"rides" | "messages">("rides");
  const [rides, setRides] = useState<Ride[] | null>(null);
  const [messages, setMessages] = useState<MyConversation[] | null>(null);
  const [version, setVersion] = useState(0);

  // Rides change state with the clock (scheduled, on the way, completed): refresh every 30 s.
  useEffect(() => {
    if (!me) return;
    let active = true;
    api.myRides().then((r) => active && setRides(r)).catch(() => undefined);
    api.myConversations().then((m) => active && setMessages(m)).catch(() => undefined);
    const timer = setTimeout(() => setVersion((v) => v + 1), 30_000);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [me, version]);

  async function cancel(id: string) {
    await api.cancelRide(id).catch(() => undefined);
    setVersion((v) => v + 1);
  }

  const tabs = [
    ["rides", t.rides.tabRides, rides?.length],
    ["messages", t.rides.tabMessages, messages?.length],
  ] as const;
  return (
    <div>
      {booked && (
        <p role="status" className="mb-6 rounded-2xl bg-amber/20 px-5 py-3 font-semibold text-night">
          {t.book.booked}
        </p>
      )}
      <div role="tablist" className="flex gap-2">
        {tabs.map(([id, label, count]) => (
          <button
            key={id}
            role="tab"
            type="button"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={`rounded-full px-5 py-2 font-semibold ${tab === id ? "bg-night text-paper" : "bg-white text-night ring-1 ring-lilac hover:ring-night"}`}
          >
            {label}
            {count != null && <span className="ml-2 opacity-70">{count}</span>}
          </button>
        ))}
        <Link href={`/${lang}/book`} className="ml-auto rounded-full bg-amber px-5 py-2 font-semibold text-night hover:bg-night hover:text-paper">
          {t.nav.book}
        </Link>
      </div>

      {tab === "rides" ? (
        <ul className="mt-6 space-y-4">
          {rides?.length === 0 && <li className="text-slate">{t.rides.empty}</li>}
          {!rides && <li className="text-slate">…</li>}
          {rides?.map((r) => (
            <li key={r.id} className="rounded-3xl bg-white p-5 ring-1 ring-lilac sm:p-6">
              <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
                <div className="min-w-0 flex-1">
                  <p className="font-display text-xl font-bold text-night">
                    {r.pickup} <span aria-hidden className="text-amber-deep">→</span>
                    <span className="sr-only"> to </span> {r.dropoff}
                  </p>
                  <p className="mt-1 text-slate">{dateTime(r.started_at, lang)}</p>
                </div>
                <span className={`rounded-full px-3 py-1 text-sm font-semibold ${STATE_STYLE[r.state]}`}>{t.rides.state[r.state]}</span>
              </div>

              <dl className="mt-4 grid gap-x-8 gap-y-2 text-sm sm:grid-cols-3">
                <div>
                  <dt className="text-slate/80">{t.rides.rideId}</dt>
                  <dd className="font-mono font-semibold text-night">{r.id}</dd>
                </div>
                <div>
                  <dt className="text-slate/80">{t.rides.driver}</dt>
                  <dd className="text-night">
                    {r.driver}, {r.vehicle}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate/80">{r.total == null ? t.rides.upfront : t.rides.paid}</dt>
                  <dd className="text-night">
                    {r.total == null
                      ? money(r.upfront_price, lang)
                      : r.charges.length === 0
                        ? money(0, lang)
                        : r.charges.map((c, i) => (
                            <span key={i} className="block">
                              {money(c.amount, lang)}
                              {c.pending && <span className="text-slate/80"> ({t.rides.pending})</span>}
                              {i === 0 && ` · •••• ${r.card}`}
                            </span>
                          ))}
                  </dd>
                </div>
              </dl>

              <div className="mt-5 flex flex-wrap gap-3">
                <Link
                  href={`${path}?chat=open&ride=${r.id}`}
                  scroll={false}
                  className="rounded-full bg-night px-5 py-2 text-sm font-semibold text-paper hover:bg-night-soft"
                >
                  {t.rides.getHelp}
                </Link>
                {r.state === "scheduled" && (
                  <button
                    type="button"
                    onClick={() => cancel(r.id)}
                    className="rounded-full px-5 py-2 text-sm font-semibold text-night ring-1 ring-lilac hover:ring-night"
                  >
                    {t.rides.cancel}
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <ul className="mt-6 divide-y divide-lilac/60 overflow-hidden rounded-3xl bg-white ring-1 ring-lilac">
          {messages?.length === 0 && <li className="px-6 py-5 text-slate">{t.rides.noMessages}</li>}
          {messages?.map((m) => (
            <li key={m.id}>
              <Link
                href={`/${lang}/track/?id=${m.id}&k=${encodeURIComponent(m.key)}`}
                className="flex items-center gap-4 px-6 py-4 hover:bg-paper"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-night">{m.preview}</span>
                  <span className="text-sm text-slate/80">
                    {m.number} · {dateTime(m.received_at, lang)}
                  </span>
                </span>
                <span className="text-sm font-semibold text-night">{t.rides.open}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
