"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { useAccount } from "@/components/site/account";
import { api, type Lang, type Quote } from "@/lib/api";
import { money } from "@/lib/format";
import type { Dict } from "@/lib/i18n";

// Local "YYYY-MM-DDTHH:mm" for <input type="datetime-local">.
function localInput(date: Date): string {
  const d = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return d.toISOString().slice(0, 16);
}

// Choose two places and a time, see the upfront price, book (signed in).
export function BookingForm({ lang, t, tone = "light" }: { lang: Lang; t: Dict["book"]; tone?: "light" | "dark" }) {
  const router = useRouter();
  const me = useAccount();
  const [places, setPlaces] = useState<string[]>([]);
  const [pickup, setPickup] = useState("");
  const [dropoff, setDropoff] = useState("");
  const [later, setLater] = useState(false);
  const [at, setAt] = useState(() => localInput(new Date(Date.now() + 60 * 60_000)));
  const [quote, setQuote] = useState<{ key: string; value: Quote } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.places().then(setPlaces).catch(() => setPlaces([]));
  }, []);

  const key = `${pickup}>${dropoff}`;
  const ready = Boolean(pickup && dropoff && pickup !== dropoff);
  useEffect(() => {
    if (!ready) return;
    let active = true;
    api
      .quote(pickup, dropoff)
      .then((value) => active && setQuote({ key, value }))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [ready, pickup, dropoff, key]);
  const shown = ready && quote?.key === key ? quote.value : null;

  async function book(e: FormEvent) {
    e.preventDefault();
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      const when = later ? new Date(at).toISOString() : new Date().toISOString();
      await api.book(pickup, dropoff, when);
      router.push(`/${lang}/rides?booked=1`);
    } catch {
      setError(t.error);
      setBusy(false);
    }
  }

  const dark = tone === "dark";
  const label = `text-sm font-semibold ${dark ? "text-lilac" : "text-night"}`;
  const field = "mt-1.5 w-full rounded-xl border border-lilac bg-white px-4 py-3 text-night focus:border-amber";
  const now = new Date();
  return (
    <form onSubmit={book} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className={label}>{t.from}</span>
          <select value={pickup} onChange={(e) => setPickup(e.target.value)} required className={field}>
            <option value="">{t.pick}</option>
            {places.map((p) => (
              <option key={p} value={p} disabled={p === dropoff}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className={label}>{t.to}</span>
          <select value={dropoff} onChange={(e) => setDropoff(e.target.value)} required className={field}>
            <option value="">{t.pick}</option>
            {places.map((p) => (
              <option key={p} value={p} disabled={p === pickup}>
                {p}
              </option>
            ))}
          </select>
        </label>
      </div>

      <fieldset>
        <legend className={label}>{t.when}</legend>
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          {[false, true].map((isLater) => (
            <label
              key={String(isLater)}
              className={`cursor-pointer rounded-full px-4 py-2 text-sm font-semibold ring-1 has-[:checked]:bg-amber has-[:checked]:text-night has-[:checked]:ring-amber ${
                dark ? "text-paper ring-lilac/40" : "bg-white text-night ring-lilac"
              }`}
            >
              <input type="radio" name="when" className="sr-only" checked={later === isLater} onChange={() => setLater(isLater)} />
              {isLater ? t.later : t.now}
            </label>
          ))}
          {later && (
            <input
              type="datetime-local"
              aria-label={t.when}
              value={at}
              min={localInput(now)}
              max={localInput(new Date(now.getTime() + 7 * 86_400_000))}
              onChange={(e) => setAt(e.target.value)}
              className="rounded-xl border border-lilac bg-white px-3 py-2 text-night focus:border-amber"
            />
          )}
        </div>
      </fieldset>

      <div className={`flex flex-wrap items-end justify-between gap-4 rounded-2xl px-5 py-4 ${dark ? "bg-night-soft/80 ring-1 ring-lilac/20" : "bg-white ring-1 ring-lilac"}`}>
        <div aria-live="polite">
          <p className={`text-sm ${dark ? "text-lilac" : "text-slate"}`}>{t.price}</p>
          <p className={`font-display text-3xl font-bold ${dark ? "text-paper" : "text-night"}`}>
            {shown ? money(shown.price, lang) : "–"}
          </p>
          <p className={`text-sm ${dark ? "text-lilac" : "text-slate"}`}>
            {shown ? `${shown.distance_km} ${t.km} · ${shown.duration_min} ${t.minutes}` : " "}
          </p>
        </div>
        {me === null ? (
          <Link
            href={`/${lang}/account?next=/${lang}/book`}
            className="rounded-full bg-amber px-6 py-3 font-semibold text-night hover:bg-paper"
          >
            {t.signInFirst}
          </Link>
        ) : (
          <button
            type="submit"
            disabled={!ready || busy || me === undefined}
            className="rounded-full bg-amber px-6 py-3 font-semibold text-night hover:bg-paper disabled:opacity-50"
          >
            {busy ? t.booking : t.confirm}
          </button>
        )}
      </div>
      {error && (
        <p role="alert" className={dark ? "text-amber" : "text-night"}>
          {error}
        </p>
      )}
    </form>
  );
}
