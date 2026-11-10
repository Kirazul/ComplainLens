"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { ChannelMark } from "@/components/console/channel";
import { useOperator } from "@/components/console/operator";
import { CitedText, ReplyCard, Verification, type Sources } from "@/components/console/reply-panel";
import { formatMs, StageTimeline } from "@/components/console/stage-timeline";
import { humanize, StatusPill } from "@/components/console/status";
import { useEvents } from "@/components/console/use-events";
import { api, type TicketDetail } from "@/lib/api";

export function TicketView({ ticketId }: Readonly<{ ticketId: number }>) {
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [help, setHelp] = useState<Sources>({});
  const [editing, setEditing] = useState(false);
  const [edited, setEdited] = useState("");
  const [sending, setSending] = useState(false);
  const { state: operator } = useOperator();

  // Bumped by live events for this ticket and after an approval; each bump reloads the ticket.
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let active = true;
    api
      .ticket(ticketId)
      .then((t) => {
        if (!active) return;
        setTicket(t);
        setError(null);
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [ticketId, version]);

  useEffect(() => {
    Promise.all([api.help("en"), api.help("fr")])
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

  const sources = useMemo<Sources>(() => {
    const lang = ticket?.language === "fr" ? "fr" : "en";
    const out: Sources = {};
    for (const [key, value] of Object.entries(help)) {
      if (key.startsWith(`${lang}:`)) out[key.slice(3)] = value;
    }
    const link = ticket?.stages.find((s) => s.name === "link");
    for (const f of (link?.output.facts as { id: string; text: string }[] | undefined) ?? []) {
      out[f.id] = { title: "Customer record fact (computed by code)", text: f.text };
    }
    return out;
  }, [help, ticket]);

  if (error) {
    return <main className="mx-auto max-w-7xl px-5 py-8"><p role="alert" className="text-escalated">{error}</p></main>;
  }
  if (!ticket) return <main className="mx-auto max-w-7xl px-5 py-8 text-muted">Loading…</main>;

  const processing = ticket.status === "processing";
  const draft = ticket.replies.find((r) => r.kind === "answer" && r.status === "draft");
  const decision = ticket.decision;
  const trip = ticket.trip as Record<string, unknown> | null;

  async function approve() {
    setSending(true);
    try {
      await api.approve(ticketId, editing ? edited : undefined);
      setEditing(false);
      setVersion((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  }

  return (
    <main className="mx-auto max-w-7xl px-5 py-8">
      <Link href="/console" className="text-sm text-muted hover:text-ink">
        Back to inbox
      </Link>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-2xl font-semibold">{ticket.number}</h1>
        <StatusPill status={ticket.status} />
        <span className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
          <ChannelMark channel={ticket.channel} />
          <span>{ticket.language === "fr" ? "French" : ticket.language === "en" ? "English" : "Language …"}</span>
          <span>{ticket.team ?? "Team …"}</span>
          {ticket.total_ms != null && <span>Processed in {formatMs(ticket.total_ms)}</span>}
        </span>
      </div>

      <div className="mt-6 grid gap-8 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <section aria-label="Message and pipeline">
          <article className="rounded-xl border border-line bg-white p-4">
            <p className="text-sm text-muted">
              From {ticket.sender_name ? `${ticket.sender_name} · ` : ""}
              {ticket.sender} · {new Date(ticket.received_at).toLocaleString()}
            </p>
            {ticket.subject && <p className="mt-2 font-semibold">{ticket.subject}</p>}
            <p className="mt-2 whitespace-pre-line">{ticket.body}</p>
          </article>
          <h2 className="mb-3 mt-8 font-semibold">Pipeline</h2>
          <StageTimeline stages={ticket.stages} processing={processing} />
        </section>

        <section aria-label="Decision and reply" className="space-y-6">
          {decision && (
            <div className="rounded-xl border border-line bg-white p-4">
              <h2 className="font-semibold">Decision: {humanize(decision.action)}</h2>
              <ul className="mt-2 list-disc pl-5 text-sm">
                {decision.reasons.map((r) => <li key={r}>{r}</li>)}
              </ul>
              <h3 className="mt-4 text-sm font-semibold">Priority {decision.priority} of 100</h3>
              <dl className="mt-2 space-y-1 text-sm">
                {Object.entries(decision.priority_parts).map(([part, value]) => (
                  <div key={part} className="grid grid-cols-[9rem_1fr_2.5rem] items-center gap-2">
                    <dt className="text-muted">{part}</dt>
                    <dd className="h-2 rounded bg-desk">
                      <div className="h-2 rounded bg-review" style={{ width: `${value}%` }} />
                    </dd>
                    <dd className="text-right">{value}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}

          {trip && (
            <div className="rounded-xl border border-line bg-white p-4 text-sm">
              <h2 className="font-semibold">Linked record: {String(trip.id)}</h2>
              <p className="mt-1 text-muted">Synthetic LunaGo data, used to verify facts.</p>
              <ul className="mt-2 space-y-1">
                {(((ticket.stages.find((s) => s.name === "link")?.output.facts) as { id: string; text: string }[]) ?? []).map((f) => (
                  <li key={f.id}><span className="font-semibold">{f.id}</span> {f.text}</li>
                ))}
              </ul>
            </div>
          )}

          {draft && (
            <div className="rounded-xl border-2 border-review/40 bg-white p-4">
              <div className="flex items-baseline justify-between">
                <h2 className="font-semibold">AI draft, waiting for approval</h2>
                <button type="button" onClick={() => { setEditing(!editing); setEdited(draft.body); }} className="text-sm text-muted hover:text-ink">
                  {editing ? "Cancel editing" : "Edit"}
                </button>
              </div>
              <div className="mt-3 text-sm">
                {editing ? (
                  <textarea
                    aria-label="Edited reply"
                    value={edited}
                    onChange={(e) => setEdited(e.target.value)}
                    rows={10}
                    className="w-full rounded-lg border border-line p-3"
                  />
                ) : (
                  <CitedText text={draft.body} sources={sources} />
                )}
              </div>
              <div className="mt-4 border-t border-line pt-3">
                <h3 className="text-sm font-semibold">Verification</h3>
                <div className="mt-1"><Verification v={draft.verification} /></div>
              </div>
              {operator === "agent" ? (
                <button
                  type="button"
                  onClick={approve}
                  disabled={sending}
                  className="mt-4 rounded-lg bg-sent px-4 py-2 font-semibold text-white disabled:opacity-60"
                >
                  {sending ? "Sending…" : editing ? "Send edited reply" : "Approve and send"}
                </button>
              ) : (
                <p className="mt-4 rounded-lg bg-desk px-3 py-2 text-sm text-muted">
                  An agent approves or edits this draft before it reaches the customer. Sign in as an
                  agent (top right) to do it.
                </p>
              )}
            </div>
          )}

          <div className="space-y-3">
            <h2 className="font-semibold">Messages to the customer</h2>
            {ticket.replies.filter((r) => r !== draft).length === 0 && (
              <p className="text-sm text-muted">{processing ? "Not decided yet." : "Nothing sent."}</p>
            )}
            {ticket.replies.filter((r) => r !== draft).map((r) => <ReplyCard key={r.id} reply={r} sources={sources} />)}
          </div>
        </section>
      </div>
    </main>
  );
}
