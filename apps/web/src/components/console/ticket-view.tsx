"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { ChannelMark } from "@/components/console/channel";
import { CitedText, Verification, type Sources } from "@/components/console/reply-panel";
import { formatMs, StageTimeline } from "@/components/console/stage-timeline";
import { humanize, STATUS, StatusPill, statusLabel } from "@/components/console/status";
import { useEvents } from "@/components/console/use-events";
import { api, type TicketDetail, type ThreadItem } from "@/lib/api";
import { ago } from "@/lib/time";

type Fact = { id: string; text: string };
const NEEDS_YOU = new Set(["awaiting_approval", "escalated"]);

export function TicketView({ ticketId }: Readonly<{ ticketId: number }>) {
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [help, setHelp] = useState<Sources>({});
  const [version, setVersion] = useState(0); // bumped by live events for this ticket: reload
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    let active = true;
    api
      .ticket(ticketId)
      .then((t) => {
        if (!active) return;
        setTicket(t);
        setError(null);
        setNow(Date.now());
      })
      .catch((e: Error) => active && setError(e.message === "ticket not found" ? "This conversation does not exist." : e.message));
    return () => {
      active = false;
    };
  }, [ticketId, version]);

  useEffect(() => {
    Promise.all([api.knowledge("en"), api.knowledge("fr")])
      .then(([en, fr]) => {
        const map: Sources = {};
        for (const [lang, articles] of [["en", en], ["fr", fr]] as const)
          for (const a of articles)
            for (const s of a.sections) map[`${lang}:${s.id}`] = { title: `${a.title} > ${s.heading}`, text: s.text };
        setHelp(map);
      })
      .catch(() => undefined);
  }, []);

  useEvents((event) => {
    if (event.ticket_id === ticketId) setVersion((v) => v + 1);
  });

  const facts = useMemo<Fact[]>(
    () => (ticket?.stages.find((s) => s.name === "link")?.output.facts as Fact[] | undefined) ?? [],
    [ticket],
  );

  const sources = useMemo<Sources>(() => {
    const lang = ticket?.language === "fr" ? "fr" : "en";
    const out: Sources = {};
    for (const [key, value] of Object.entries(help)) if (key.startsWith(`${lang}:`)) out[key.slice(3)] = value;
    for (const f of facts) out[f.id] = { title: "Fact from the customer's record (computed by code)", text: f.text };
    return out;
  }, [help, ticket?.language, facts]);

  if (error) {
    return (
      <main className="mx-auto max-w-7xl px-5 py-8">
        <Link href="/console" className="text-sm text-muted hover:text-ink">Inbox</Link>
        <p role="alert" className="mt-4 text-escalated">{error}</p>
      </main>
    );
  }
  if (!ticket) return <main className="mx-auto max-w-7xl px-5 py-8 text-muted">Loading…</main>;

  const reload = () => setVersion((v) => v + 1);
  const name = ticket.sender.startsWith("forum:") ? `@${ticket.sender.slice(6)}` : ticket.customer?.name || ticket.sender_name || ticket.sender;
  const resolved = ticket.status === "closed" || ticket.status === "no_reply";

  return (
    <main className="mx-auto max-w-7xl px-5 py-8">
      <Link href="/console" className="text-sm text-muted hover:text-ink">
        <span aria-hidden>‹ </span>Inbox
      </Link>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
        <h1 className="text-2xl font-semibold">{name}</h1>
        <StatusPill status={ticket.status} />
        <span className="text-sm text-muted">{ticket.number}</span>
        <StatusButton ticket={ticket} resolved={resolved} onDone={reload} />
      </div>
      <p className="mt-1 text-sm text-muted">{STATUS[ticket.status]?.help}</p>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <section aria-label="Conversation" className="space-y-4">
          <div className="space-y-4 rounded-xl border border-line bg-white p-4 sm:p-5">
            {ticket.subject && <p className="font-semibold">{ticket.subject}</p>}
            {ticket.thread.map((m, i) => (
              <Bubble key={i} item={m} customer={name} now={now} sources={sources} />
            ))}
            {ticket.status === "processing" && (
              <p className="flex items-center gap-2 text-sm text-muted" role="status">
                <span className="size-2 animate-pulse rounded-full bg-blue-500" aria-hidden />
                The AI is reading the latest message…
              </p>
            )}
          </div>
          <Composer key={ticket.draft?.id ?? "none"} ticket={ticket} sources={sources} onSent={reload} />
        </section>

        <aside className="space-y-4">
          <Decision ticket={ticket} />
          <RideCheck ticket={ticket} facts={facts} />
          <Card title="Customer">
            <dl className="space-y-1.5 text-sm">
              <Row label="Name">{ticket.customer?.name || ticket.sender_name || "Not given"}</Row>
              <Row label="Contact"><span className="break-all">{ticket.sender}</span></Row>
              <Row label="Channel"><ChannelMark channel={ticket.channel} /></Row>
              <Row label="Language">{ticket.language === "fr" ? "French" : ticket.language === "en" ? "English" : "…"}</Row>
              <Row label="Team">{ticket.team ?? "…"}</Row>
              <Row label="Priority">{ticket.priority != null ? `${ticket.priority} of 100` : "…"}</Row>
            </dl>
          </Card>
          <Understanding ticket={ticket} />
          <details className="group rounded-xl border border-line bg-white">
            <summary className="cursor-pointer list-none px-4 py-3 font-semibold">
              <span className="mr-1 inline-block transition-transform group-open:rotate-90" aria-hidden>›</span>
              How the AI processed it
              {ticket.total_ms != null && <span className="ml-2 text-sm font-normal text-muted">6 steps, {formatMs(ticket.total_ms)}</span>}
            </summary>
            <div className="border-t border-line p-4">
              <StageTimeline stages={ticket.stages} processing={ticket.status === "processing"} />
            </div>
          </details>
        </aside>
      </div>
    </main>
  );
}

function Bubble({ item, customer, now, sources }: { item: ThreadItem; customer: string; now: number; sources: Sources }) {
  const mine = item.from === "lunago";
  const who = !mine ? customer : item.author ? `${item.author} (agent)` : "AI assistant";
  const kind =
    item.kind === "acknowledgement"
      ? "automatic acknowledgement"
      : item.kind === "escalation"
        ? "safety message"
        : item.kind === "question"
          ? "asked for the ride ID"
          : null;
  const delivery =
    item.status === "queued"
      ? "waiting to be posted on the forum"
      : item.status === "failed"
        ? item.error === "no outbound delivery for this channel"
          ? "not delivered: no way to reach the customer on this channel"
          : `not delivered: ${item.error ?? "unknown error"}`
        : null;
  return (
    <article className={`flex flex-col ${mine ? "items-end" : "items-start"}`}>
      <p className="mb-1 px-1 text-xs text-muted">
        <span className="font-medium text-ink">{who}</span>
        {kind && ` · ${kind}`} · <time dateTime={item.at} title={new Date(item.at).toLocaleString()}>{ago(item.at, now)}</time>
      </p>
      <div
        className={`max-w-[92%] rounded-2xl px-4 py-3 text-sm ${
          mine ? "rounded-tr-md bg-teal-50/70 ring-1 ring-teal-200" : "rounded-tl-md bg-desk"
        }`}
      >
        {mine ? <CitedText text={item.body} sources={sources} /> : <p className="whitespace-pre-line leading-relaxed">{item.body}</p>}
      </div>
      {delivery && <p className={`mt-1 px-1 text-xs ${item.status === "failed" ? "text-escalated" : "text-muted"}`}>{delivery}</p>}
    </article>
  );
}

// The reply box: the AI suggestion when there is one (edit it or not), or the agent's own words.
function Composer({ ticket, sources, onSent }: { ticket: TicketDetail; sources: Sources; onSent: () => void }) {
  const draft = ticket.draft;
  const [text, setText] = useState(draft?.body ?? "");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState(false);
  const box = useRef<HTMLTextAreaElement>(null);
  const edited = draft && text.trim() !== draft.body.trim();

  async function send() {
    setSending(true);
    setError(null);
    try {
      const r = await api.reply(ticket.id, text.trim());
      if (r.status === "failed") setError("Saved, but not delivered. Check the email settings.");
      setText("");
      setPreview(false);
      onSent();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  }

  const where =
    ticket.channel === "forum"
      ? "Posted as a comment in the forum thread."
      : ticket.channel === "email"
        ? "Sent by email, in the customer's thread."
        : "The customer sees it in the chat and on their ticket page.";

  return (
    <div className={`rounded-xl border bg-white p-4 sm:p-5 ${draft && NEEDS_YOU.has(ticket.status) ? "border-review/50 ring-2 ring-amber-100" : "border-line"}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-semibold">{draft ? (edited ? "Your reply (edited from the AI suggestion)" : "AI suggestion") : "Reply"}</h2>
        {draft && (
          <button type="button" onClick={() => setPreview(!preview)} className="text-sm text-muted hover:text-ink">
            {preview ? "Edit" : "Check the sources"}
          </button>
        )}
      </div>
      {draft && !edited && (
        <div className="mt-1">
          <Verification v={draft.verification} />
        </div>
      )}
      {preview ? (
        <div className="mt-3 rounded-lg border border-line p-3 text-sm">
          <CitedText text={text} sources={sources} />
        </div>
      ) : (
        <textarea
          ref={box}
          aria-label="Reply to the customer"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && text.trim()) send();
          }}
          rows={draft ? 8 : 4}
          placeholder="Write a reply…"
          className="mt-3 w-full rounded-lg border border-line p-3 text-sm leading-relaxed focus:border-ink"
        />
      )}
      {error && <p role="alert" className="mt-2 text-sm text-escalated">{error}</p>}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={send}
          disabled={sending || !text.trim()}
          className="rounded-lg bg-ink px-5 py-2 font-semibold text-white disabled:opacity-50"
        >
          {sending ? "Sending…" : "Send reply"}
        </button>
        {draft && text && (
          <button
            type="button"
            onClick={() => {
              setText("");
              setPreview(false);
              setTimeout(() => box.current?.focus(), 0);
            }}
            className="text-sm text-muted hover:text-ink"
          >
            Write my own instead
          </button>
        )}
        <p className="text-xs text-muted sm:ml-auto">{where}</p>
      </div>
    </div>
  );
}

function StatusButton({ ticket, resolved, onDone }: { ticket: TicketDetail; resolved: boolean; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  if (ticket.status === "processing") return null;
  async function toggle() {
    setBusy(true);
    try {
      await api.setResolved(ticket.id, !resolved);
      onDone();
    } finally {
      setBusy(false);
    }
  }
  return (
    <button
      type="button"
      onClick={toggle}
      disabled={busy}
      className="rounded-lg border border-line bg-white px-3.5 py-1.5 text-sm font-semibold hover:border-ink disabled:opacity-60 sm:ml-auto"
    >
      {resolved ? "Reopen" : "Mark as resolved"}
    </button>
  );
}

function Decision({ ticket }: { ticket: TicketDetail }) {
  const d = ticket.decision;
  if (!d) return null;
  return (
    <Card title="Why the AI decided this">
      <p className="text-sm">
        Decision: <span className="font-semibold">{statusLabel(d.action)}</span>
      </p>
      <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm">
        {d.reasons.map((r) => (
          <li key={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</li>
        ))}
      </ul>
    </Card>
  );
}

// How a ride problem is checked: the ride is found only by its ID, on the customer's own account;
// what the customer says is then checked against the record, and the facts the reply may use are
// computed by code.
function RideCheck({ ticket, facts }: { ticket: TicketDetail; facts: Fact[] }) {
  const link = ticket.stages.find((s) => s.name === "link");
  if (!link) return null;
  const out = link.output as {
    about_ride?: boolean;
    ride_ids_quoted?: string[];
    checks?: { ok: boolean; text: string }[];
    customer?: { has_account?: boolean; rides?: number };
  };
  const trip = ticket.trip;
  const account = out.customer?.has_account ? "Has an account" : "Guest (no account)";
  return (
    <Card title="Ride check">
      {!out.about_ride ? (
        <p className="text-sm text-muted">Not about a specific ride: no ride needed.</p>
      ) : trip ? (
        <>
          <p className="text-sm">
            Ride <span className="font-semibold">{String(trip.id)}</span>, on this customer&apos;s account.
          </p>
          {(out.checks ?? []).length > 0 && (
            <ul className="mt-2 space-y-0.5 text-sm">
              {(out.checks ?? []).map((c) => (
                <li key={c.text} className={c.ok ? "" : "text-review"}>
                  <span aria-hidden>{c.ok ? "✓ " : "✗ "}</span>
                  {c.text.charAt(0).toUpperCase() + c.text.slice(1)}
                </li>
              ))}
            </ul>
          )}
          <h3 className="mt-3 text-sm font-semibold">What the record says</h3>
          <ul className="mt-1 space-y-1 text-sm">
            {facts.map((f) => (
              <li key={f.id} className={f.text.startsWith("The customer mentions") ? "text-review" : ""}>
                <span className="font-semibold">{f.id}</span> {f.text}
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-muted">Replies may only use these facts. Every number is checked.</p>
        </>
      ) : (
        <p className="text-sm">
          {out.ride_ids_quoted?.length
            ? `${out.ride_ids_quoted.join(", ")} is not on this customer's account, so the AI asked again.`
            : "No ride ID yet, so the AI asked the customer for it."}
          <span className="mt-1 block text-muted">
            {account}, {out.customer?.rides ?? 0} rides.
          </span>
        </p>
      )}
    </Card>
  );
}

function Understanding({ ticket }: { ticket: TicketDetail }) {
  const a = ticket.analysis as Record<string, unknown> | null;
  if (!a) return null;
  const list = (v: unknown) => ((v as string[]) ?? []).map(humanize).join(", ") || "none";
  return (
    <Card title="What the AI understood">
      <p className="text-sm">{String(a.summary ?? "")}</p>
      <dl className="mt-3 space-y-1.5 text-sm">
        <Row label="Goal">{String(a.customer_goal ?? "")}</Row>
        <Row label="Type">{humanize(String(a.message_type ?? ""))}</Row>
        <Row label="Topics">{list(a.categories)}</Row>
        <Row label="Risk"><span className={(a.risk_flags as string[])?.length ? "font-semibold text-escalated" : ""}>{list(a.risk_flags)}</span></Row>
      </dl>
    </Card>
  );
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-line bg-white p-4">
      <h2 className="mb-2 font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[5.5rem_1fr] gap-2">
      <dt className="text-muted">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}
