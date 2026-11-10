"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { Moon } from "@/components/moon";
import { api, ApiError, type Lang, type PublicTicket } from "@/lib/api";
import type { Dict } from "@/lib/i18n";

const FINAL = new Set(["auto_send", "answered", "awaiting_approval", "escalated", "no_reply", "closed"]);
const EMAIL_KEY = "lunago.chat.email"; // remembered in this browser only, for convenience

type Phase = 0 | 1 | 2 | 3 | 4;
interface Conversation {
  text: string;
  ticket?: { id: number; number: string; key: string };
  status?: PublicTicket;
}

function stripCitations(text: string): string {
  return text.replace(/\s?\[(?:HC-[A-Z]+#\d+|F\d+)\]/g, "");
}

// Live chat on the LunaGo site: the message goes through the same pipeline as every other
// channel (channel "chat"), and the moon fills as the request moves from received to answered.
export function ChatWidget({ lang, t, phases }: { lang: Lang; t: Dict["chat"]; phases: Dict["phases"] }) {
  const query = useSearchParams();
  // Opened by the visitor, or from a link anywhere on the site (?chat=open, e.g. the home page or
  // the console). A new ?chat=open request reopens it even after it was closed.
  const requested = query.get("chat") === "open";
  const [lastRequested, setLastRequested] = useState(requested);
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  if (requested !== lastRequested) {
    setLastRequested(requested);
    setUserOpen(null);
  }
  const open = userOpen ?? requested;
  const setOpen = (value: boolean) => setUserOpen(value);
  const [email, setEmail] = useState(() => {
    try {
      return typeof window === "undefined" ? "" : (window.localStorage.getItem(EMAIL_KEY) ?? "");
    } catch {
      return ""; // storage unavailable: the visitor types the email
    }
  });
  const [text, setText] = useState("");
  const [conv, setConv] = useState<Conversation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const panelId = useId();
  const firstField = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null);
  const launcher = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    firstField.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        launcher.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  // Follow the ticket until the pipeline has decided, then once more slowly for an agent's reply.
  useEffect(() => {
    const ticket = conv?.ticket;
    if (!ticket) return;
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async (attempt: number) => {
      try {
        const status = await api.publicTicket(ticket.id, ticket.key);
        if (stop) return;
        setConv((c) => (c ? { ...c, status } : c));
        if (attempt < 300) timer = setTimeout(() => poll(attempt + 1), FINAL.has(status.status) ? 10_000 : 1000);
      } catch {
        if (!stop && attempt < 300) timer = setTimeout(() => poll(attempt + 1), 3000);
      }
    };
    poll(0);
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [conv?.ticket]);

  async function send(e: FormEvent) {
    e.preventDefault();
    const body = text.trim();
    if (!email.trim() || body.length < 2) return;
    setSending(true);
    setError(null);
    try {
      const r = await api.submit({ email: email.trim(), body, channel: "chat" });
      try {
        window.localStorage.setItem(EMAIL_KEY, email.trim());
      } catch {
        // not remembered: fine
      }
      setConv({ text: body, ticket: { id: r.id, number: r.number, key: r.track_key } });
      setText("");
    } catch (err) {
      setError(err instanceof ApiError && err.status === 422 ? t.emailHint : t.error);
    } finally {
      setSending(false);
    }
  }

  const status = conv?.status;
  const done = (status?.phases.filter((p) => p.done).length ?? (conv ? 1 : 0)) as Phase;
  const decided = status && FINAL.has(status.status);
  const current = status?.phases.find((p) => !p.done)?.name;

  return (
    <>
      <button
        ref={launcher}
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls={panelId}
        className="fixed bottom-4 right-4 z-40 flex items-center gap-2.5 rounded-full bg-night p-3 font-semibold text-paper shadow-[0_10px_30px_-10px_rgba(30,27,75,0.7)] ring-1 ring-lilac/30 hover:bg-night-soft sm:bottom-5 sm:right-5 sm:py-2.5 sm:pl-3 sm:pr-5"
      >
        <Moon phase={open ? 4 : 1} size={26} />
        <span className="sr-only sm:not-sr-only">{open ? t.close : t.open}</span>
      </button>

      {open && (
        <section
          id={panelId}
          role="dialog"
          aria-label={t.title}
          className="fixed inset-x-3 bottom-20 z-40 flex max-h-[min(36rem,calc(100dvh-7rem))] flex-col overflow-hidden rounded-3xl bg-paper shadow-[0_24px_60px_-20px_rgba(30,27,75,0.55)] ring-1 ring-night/15 sm:inset-x-auto sm:right-5 sm:w-[25rem]"
        >
          <div className="flex items-center gap-3 bg-night px-5 py-4 text-paper">
            <Moon phase={conv ? done : 1} size={34} />
            <div>
              <h2 className="font-display text-lg font-bold leading-tight">{t.title}</h2>
              <p className="text-sm text-lilac empty:hidden" aria-live="polite">
                {conv ? (decided ? conv.ticket?.number : `${current ? phases[current] : t.working}…`) : null}
              </p>
            </div>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto px-5 py-5">
            <p className="max-w-[92%] rounded-2xl rounded-bl-md bg-white px-4 py-3 text-night ring-1 ring-lilac">
              {t.intro}
            </p>
            {conv && (
              <>
                <p className="ml-auto max-w-[85%] whitespace-pre-line rounded-2xl rounded-br-md bg-night px-4 py-3 text-paper">
                  {conv.text}
                </p>
                {!decided && (
                  <ol className="flex items-center gap-2 text-sm text-slate/80" aria-label={t.working}>
                    {(["received", "understood", "routed", "answered"] as const).map((name, i) => (
                      <li key={name} className="flex items-center gap-1.5">
                        <Moon phase={(i < done ? i + 1 : 0) as Phase} size={18} surface="day" />
                        <span className={i < done ? "text-night" : ""}>{phases[name]}</span>
                      </li>
                    ))}
                  </ol>
                )}
                {status?.replies.map((r, i) => (
                  <p
                    key={i}
                    className="max-w-[92%] whitespace-pre-line rounded-2xl rounded-bl-md bg-white px-4 py-3 text-night ring-1 ring-lilac"
                  >
                    {stripCitations(r.body)}
                  </p>
                ))}
                {decided && conv.ticket && (
                  <div className="flex flex-wrap gap-x-5 gap-y-2 text-sm">
                    <Link
                      href={`/${lang}/track/?id=${conv.ticket.id}&k=${encodeURIComponent(conv.ticket.key)}`}
                      className="font-semibold text-night underline underline-offset-4"
                    >
                      {t.track}
                    </Link>
                    <button
                      type="button"
                      onClick={() => setConv(null)}
                      className="font-semibold text-night underline underline-offset-4"
                    >
                      {t.again}
                    </button>
                  </div>
                )}
              </>
            )}
          </div>

          {!conv && (
            <form onSubmit={send} className="space-y-3 border-t border-lilac/60 bg-white px-5 py-4">
              <label className="block text-sm">
                <span className="font-semibold text-night">{t.email}</span>
                <input
                  ref={(el) => {
                    if (!email) firstField.current = el;
                  }}
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="mt-1 w-full rounded-xl border border-lilac px-3 py-2 text-night focus:border-night"
                />
              </label>
              <label className="block text-sm">
                <span className="sr-only">{t.placeholder}</span>
                <textarea
                  ref={(el) => {
                    if (email) firstField.current = el;
                  }}
                  required
                  rows={3}
                  maxLength={5000}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      e.currentTarget.form?.requestSubmit();
                    }
                  }}
                  placeholder={t.placeholder}
                  className="w-full resize-none rounded-xl border border-lilac px-3 py-2 text-night placeholder:text-slate/50 focus:border-night"
                />
              </label>
              {error && (
                <p role="alert" className="text-sm text-night">
                  {error}
                </p>
              )}
              <button
                type="submit"
                disabled={sending || !email.trim() || text.trim().length < 2}
                className="w-full rounded-full bg-amber px-5 py-2.5 font-semibold text-night hover:bg-night hover:text-paper disabled:opacity-50"
              >
                {sending ? "…" : t.send}
              </button>
            </form>
          )}
        </section>
      )}
    </>
  );
}
