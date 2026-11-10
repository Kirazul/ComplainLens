"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { Moon } from "@/components/moon";
import { useAccount } from "@/components/site/account";
import { Messages, ReplyBox, useConversation, type ConversationRef } from "@/components/site/conversation";
import { api, ApiError, type Account, type Lang, type Ride } from "@/lib/api";
import { dateTime } from "@/lib/format";
import type { Dict } from "@/lib/i18n";
import { remember, useRemembered } from "@/lib/storage";

// Remembered in this browser only, so a conversation continues after a reload or on another page.
const EMAIL_KEY = "lunago.chat.email";
const CONVERSATION_KEY = "lunago.chat.conversation";

// Live chat: every message goes through the same pipeline as the other channels (channel "chat").
export function ChatWidget({ lang, t }: { lang: Lang; t: Dict }) {
  const c = t.chat;
  const query = useSearchParams();
  // Opened by the visitor, or by a link anywhere on the site (?chat=open).
  const requested = query.get("chat") === "open";
  const [lastRequested, setLastRequested] = useState(requested);
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  if (requested !== lastRequested) {
    setLastRequested(requested);
    setUserOpen(null);
  }
  const open = userOpen ?? requested;
  // "Get help with this ride" (Your rides) opens a new conversation about that ride.
  const ride = query.get("ride");
  const me = useAccount();
  useEffect(() => {
    if (ride) remember(CONVERSATION_KEY, null);
  }, [ride]);

  const email = useRemembered<string>(EMAIL_KEY) ?? "";
  const conv = useRemembered<ConversationRef>(CONVERSATION_KEY);
  const live = useConversation(conv, open);
  const panelId = useId();
  const launcher = useRef<HTMLButtonElement>(null);

  // The saved conversation no longer exists (e.g. demo data reset): start fresh.
  useEffect(() => {
    if (live.missing) remember(CONVERSATION_KEY, null);
  }, [live.missing]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setUserOpen(false);
        launcher.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  function started(next: ConversationRef, address: string) {
    remember(EMAIL_KEY, address);
    remember(CONVERSATION_KEY, next);
  }

  const restart = () => remember(CONVERSATION_KEY, null);

  const done = (live.data?.phases.filter((p) => p.done).length ?? 1) as 0 | 1 | 2 | 3 | 4;

  return (
    <>
      <button
        ref={launcher}
        type="button"
        onClick={() => setUserOpen(!open)}
        aria-expanded={open}
        aria-controls={panelId}
        className="fixed bottom-4 right-4 z-40 flex items-center gap-2.5 rounded-full bg-night p-3 font-semibold text-paper shadow-[0_10px_30px_-10px_rgba(30,27,75,0.7)] ring-1 ring-lilac/30 hover:bg-night-soft sm:bottom-5 sm:right-5 sm:py-2.5 sm:pl-3 sm:pr-5"
      >
        <Moon phase={open ? 4 : 1} size={26} />
        <span className="sr-only sm:not-sr-only">{open ? c.close : c.open}</span>
      </button>

      {open && (
        <section
          id={panelId}
          role="dialog"
          aria-label={c.title}
          className="fixed inset-x-3 bottom-20 z-40 flex h-[min(38rem,calc(100dvh-7rem))] flex-col overflow-hidden rounded-3xl bg-paper shadow-[0_24px_60px_-20px_rgba(30,27,75,0.55)] ring-1 ring-night/15 sm:inset-x-auto sm:right-5 sm:w-[25rem]"
        >
          <div className="flex items-center gap-3 bg-night px-5 py-4 text-paper">
            <Moon phase={conv ? done : 1} size={34} />
            <div className="min-w-0 flex-1">
              <h2 className="font-display text-lg font-bold leading-tight">{c.title}</h2>
              {conv && <p className="text-sm text-lilac">{conv.number}</p>}
            </div>
            {conv && (
              <button type="button" onClick={restart} className="rounded-full px-3 py-1 text-sm text-lilac ring-1 ring-lilac/40 hover:text-paper hover:ring-paper">
                {c.newChat}
              </button>
            )}
          </div>

          <div className="flex-1 overflow-y-auto px-5 py-5">
            <p className="mb-4 max-w-[92%] rounded-2xl rounded-bl-md bg-white px-4 py-3 text-night ring-1 ring-lilac">{c.intro}</p>
            {conv && live.data && <Messages data={live.data} t={t.conversation} />}
          </div>

          <div className="border-t border-lilac/60 bg-white px-4 py-3">
            {conv ? (
              <>
                <ReplyBox onSend={live.send} sending={live.sending} failed={live.failed} t={t.conversation} autoFocus />
                <Link
                  href={`/${lang}/track/?id=${conv.id}&k=${encodeURIComponent(conv.key)}`}
                  className="mt-2 inline-block text-xs text-slate/80 underline underline-offset-2 hover:text-night"
                >
                  {c.fullPage}
                </Link>
              </>
            ) : (
              <StartForm
                key={`${email}|${me?.customer.email ?? ""}|${ride ?? ""}`}
                email={email}
                me={me ?? null}
                ride={ride}
                lang={lang}
                t={t}
                onStarted={started}
              />
            )}
          </div>
        </section>
      )}
    </>
  );
}

interface StartProps {
  email: string;
  me: Account | null;
  ride: string | null;
  lang: Lang;
  t: Dict;
  onStarted: (ref: ConversationRef, email: string) => void;
}

// The first message. Signed in: the account's email, and the ride to attach (its ID links the
// complaint to the exact ride). Otherwise: an email address; ride problems are then asked their ID.
function StartForm({ email, me, ride, lang, t, onStarted }: StartProps) {
  const c = t.chat;
  const [address, setAddress] = useState(me?.customer.email ?? email);
  const [rides, setRides] = useState<Ride[]>([]);
  const [chosen, setChosen] = useState(ride ?? "");
  useEffect(() => {
    if (me) api.myRides().then(setRides).catch(() => setRides([]));
  }, [me]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(e: FormEvent) {
    e.preventDefault();
    const body = text.trim();
    if (!address.trim() || body.length < 2) return;
    setSending(true);
    setError(null);
    try {
      const r = await api.submit({ email: address.trim(), body, channel: "chat", ride: chosen || undefined });
      onStarted({ id: r.id, key: r.track_key, number: r.number }, address.trim());
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 422
          ? c.emailHint
          : err instanceof ApiError && err.status === 429
            ? t.conversation.busy
            : t.conversation.error,
      );
      setSending(false);
    }
  }

  return (
    <form onSubmit={send} className="space-y-2.5">
      {me ? (
        <>
          <p className="truncate text-sm text-slate/80">
            {c.signedInAs} {me.customer.email}
          </p>
          <label className="block text-sm">
            <span className="font-semibold text-night">{c.ride}</span>
            <select
              value={chosen}
              onChange={(e) => setChosen(e.target.value)}
              className="mt-1 w-full rounded-xl border border-lilac bg-white px-3 py-2 text-night focus:border-night"
            >
              <option value="">{t.contact.rideNone}</option>
              {ride && !rides.some((r) => r.id === ride) && <option value={ride}>{ride}</option>}
              {rides.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.id} · {r.pickup} → {r.dropoff} · {dateTime(r.started_at, lang)}
                </option>
              ))}
            </select>
          </label>
        </>
      ) : (
        <label className="block text-sm">
          <span className="font-semibold text-night">{c.email}</span>
          <input
            type="email"
            required
            autoComplete="email"
            autoFocus={!address}
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            className="mt-1 w-full rounded-xl border border-lilac px-3 py-2 text-night focus:border-night"
          />
        </label>
      )}
      <label className="block">
        <span className="sr-only">{t.conversation.placeholder}</span>
        <textarea
          required
          autoFocus={Boolean(address)}
          rows={2}
          maxLength={5000}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
          placeholder={c.placeholder}
          className="w-full resize-none rounded-xl border border-lilac px-3 py-2 text-night placeholder:text-slate/50 focus:border-night"
        />
      </label>
      {error && <p role="alert" className="text-sm text-night">{error}</p>}
      <button
        type="submit"
        disabled={sending || !address.trim() || text.trim().length < 2}
        className="w-full rounded-full bg-amber px-5 py-2.5 font-semibold text-night hover:bg-night hover:text-paper disabled:opacity-50"
      >
        {sending ? "…" : t.conversation.send}
      </button>
    </form>
  );
}
