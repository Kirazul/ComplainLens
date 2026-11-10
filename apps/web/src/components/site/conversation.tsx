"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";

import { api, ApiError, type PublicTicket } from "@/lib/api";
import type { Dict } from "@/lib/i18n";

/** What a browser needs to follow a conversation: its ID and secret tracking key. */
export interface ConversationRef {
  id: number;
  key: string;
  number: string;
}

const FAST = 1500; // while LunaGo is writing
const SLOW = 5000; // waiting for an agent
const IDLE_LIMIT = 30 * 60_000; // stop polling after 30 quiet minutes (the server can sleep)

/** Follows a conversation while `active`, and sends the customer's next messages. */
export function useConversation(ref: ConversationRef | null, active = true) {
  const [data, setData] = useState<PublicTicket | null>(null);
  const [missing, setMissing] = useState(false);
  const [sending, setSending] = useState(false);
  const [failed, setFailed] = useState<"busy" | "network" | null>(null);
  const [nudge, setNudge] = useState(0); // bumped after sending: poll fast again at once
  const lastActivity = useRef(0);

  useEffect(() => {
    if (!ref || !active) return;
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    lastActivity.current = Date.now();
    const poll = async () => {
      try {
        const next = await api.publicTicket(ref.id, ref.key);
        if (stop) return;
        setData(next);
        setMissing(false);
        const writing = next.status === "processing";
        if (writing) lastActivity.current = Date.now();
        if (Date.now() - lastActivity.current < IDLE_LIMIT) timer = setTimeout(poll, writing ? FAST : SLOW);
      } catch (err) {
        if (stop) return;
        if (err instanceof ApiError && err.status === 404) setMissing(true);
        else timer = setTimeout(poll, SLOW);
      }
    };
    poll();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [ref, active, nudge]);

  async function send(body: string): Promise<boolean> {
    if (!ref) return false;
    setSending(true);
    setFailed(null);
    try {
      await api.followUp(ref.id, ref.key, body);
      // Shown at once; the next poll brings the server's copy.
      setData((d) => (d ? { ...d, status: "processing", messages: [...d.messages, { from: "customer", body, at: new Date().toISOString() }] } : d));
      setNudge((n) => n + 1);
      return true;
    } catch (err) {
      setFailed(err instanceof ApiError && err.status === 429 ? "busy" : "network");
      return false;
    } finally {
      setSending(false);
    }
  }

  return { data, missing, sending, failed, send };
}

type Size = "compact" | "page";

export function Messages({ data, t, size = "compact" }: { data: PublicTicket; t: Dict["conversation"]; size?: Size }) {
  const end = useRef<HTMLDivElement>(null);
  const count = data.messages.length;
  const writing = data.status === "processing";
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" });
  }, [count, writing]);
  const bubble = size === "page" ? "px-5 py-4" : "px-4 py-3";
  return (
    <div className="space-y-4">
      {data.messages.map((m, i) =>
        m.from === "customer" ? (
          <p key={i} className={`ml-auto w-fit max-w-[85%] whitespace-pre-line rounded-2xl rounded-br-md bg-night text-paper ${bubble}`}>
            {m.body}
          </p>
        ) : (
          <div key={i} className="max-w-[92%]">
            <p className="mb-1 px-1 text-xs text-slate/80">{m.author ? `${m.author}, ${t.team}` : t.assistant}</p>
            <p className={`whitespace-pre-line rounded-2xl rounded-bl-md bg-white leading-relaxed text-night ring-1 ring-lilac ${bubble}`}>
              {m.body}
            </p>
          </div>
        ),
      )}
      {writing && (
        <p className="flex items-center gap-2 px-1 text-sm text-slate/80" role="status">
          <span className="flex gap-1" aria-hidden>
            {[0, 150, 300].map((delay) => (
              <span key={delay} className="size-1.5 animate-bounce rounded-full bg-slate/60" style={{ animationDelay: `${delay}ms` }} />
            ))}
          </span>
          {t.writing}
        </p>
      )}
      <div ref={end} />
    </div>
  );
}

export function ReplyBox({
  onSend,
  sending,
  failed,
  t,
  autoFocus = false,
}: {
  onSend: (body: string) => Promise<boolean>;
  sending: boolean;
  failed: "busy" | "network" | null;
  t: Dict["conversation"];
  autoFocus?: boolean;
}) {
  const [text, setText] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    const body = text.trim();
    if (!body || sending) return;
    if (await onSend(body)) setText("");
  }
  return (
    <form onSubmit={submit}>
      <div className="flex items-end gap-2">
        <label className="flex-1">
          <span className="sr-only">{t.placeholder}</span>
          <textarea
            autoFocus={autoFocus}
            rows={1}
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
            className="field-sizing-content max-h-40 min-h-11 w-full resize-none rounded-2xl border border-lilac bg-white px-4 py-2.5 text-night placeholder:text-slate/50 focus:border-night"
          />
        </label>
        <button
          type="submit"
          disabled={sending || !text.trim()}
          className="h-11 rounded-full bg-amber px-5 font-semibold text-night hover:bg-night hover:text-paper disabled:opacity-50"
        >
          {t.send}
        </button>
      </div>
      {failed && (
        <p role="alert" className="mt-2 text-sm text-night">
          {failed === "busy" ? t.busy : t.error}
        </p>
      )}
    </form>
  );
}
