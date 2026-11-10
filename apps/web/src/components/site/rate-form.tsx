"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { api, ApiError, type Lang } from "@/lib/api";
import type { Dict } from "@/lib/i18n";

// A trip rating, as in the app: stars and a comment. It enters the pipeline as channel "review";
// the rating travels in the subject, so the classifier reads it with the comment.
export function RateForm({ lang, t, contact }: { lang: Lang; t: Dict["rate"]; contact: Dict["contact"] }) {
  const router = useRouter();
  const [stars, setStars] = useState(0);
  const [hover, setHover] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const email = String(data.get("email") ?? "").trim();
    const comment = String(data.get("comment") ?? "").trim();
    if (!stars) return setError(t.pickStars);
    if (!email) return setError(contact.errorEmpty);
    if (stars <= 3 && comment.length < 2) return setError(t.commentNeeded);
    setSending(true);
    setError(null);
    try {
      const ticket = await api.submit({
        email,
        channel: "review",
        subject: t.subject.replace("{n}", String(stars)),
        body: comment || t.star[stars - 1],
      });
      router.push(`/${lang}/track/?id=${ticket.id}&k=${encodeURIComponent(ticket.track_key)}`);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 429 ? contact.errorBusy : contact.errorNetwork);
      setSending(false);
    }
  }

  const shown = hover || stars;
  const field =
    "mt-2 w-full rounded-xl border border-lilac bg-white px-4 py-3 text-night placeholder:text-slate/50 focus:border-night";
  return (
    <form onSubmit={onSubmit} className="space-y-8" noValidate>
      <fieldset>
        <legend className="font-semibold text-night">{t.stars}</legend>
        <div className="mt-3 flex gap-1" onMouseLeave={() => setHover(0)}>
          {[1, 2, 3, 4, 5].map((n) => (
            <label key={n} className="cursor-pointer" onMouseEnter={() => setHover(n)}>
              <input
                type="radio"
                name="stars"
                value={n}
                checked={stars === n}
                onChange={() => setStars(n)}
                className="peer sr-only"
              />
              <span className="sr-only">{t.star[n - 1]}</span>
              <svg
                viewBox="0 0 24 24"
                className={`size-12 rounded-lg peer-focus-visible:outline peer-focus-visible:outline-3 peer-focus-visible:outline-amber ${
                  n <= shown ? "text-amber" : "text-lilac"
                }`}
                aria-hidden
              >
                <path
                  fill="currentColor"
                  d="M12 2.8l2.8 5.8 6.3.9-4.6 4.4 1.1 6.3L12 17.2l-5.6 3 1.1-6.3L2.9 9.5l6.3-.9z"
                />
              </svg>
            </label>
          ))}
        </div>
        <p className="mt-2 h-6 text-slate/80" aria-live="polite">
          {shown ? t.star[shown - 1] : ""}
        </p>
      </fieldset>

      <label className="block">
        <span className="font-semibold text-night">{t.comment}</span>
        <textarea
          name="comment"
          rows={5}
          maxLength={5000}
          placeholder={stars >= 4 ? t.commentPlaceholder : ""}
          className={`${field} resize-y`}
        />
      </label>

      <label className="block max-w-md">
        <span className="font-semibold text-night">{contact.email}</span>
        <input name="email" type="email" required autoComplete="email" className={field} />
        <span className="mt-1 block text-sm text-slate">{contact.emailHint}</span>
      </label>

      {error && (
        <p role="alert" className="rounded-xl bg-amber/15 px-4 py-3 text-night">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={sending}
        className="rounded-full bg-night px-7 py-3 font-semibold text-paper hover:bg-night-soft disabled:opacity-60"
      >
        {sending ? contact.sending : t.send}
      </button>
    </form>
  );
}
