"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { ChannelMark } from "@/components/console/channel";
import { humanize, StatusPill } from "@/components/console/status";
import { useEvents } from "@/components/console/use-events";
import { api, FORUM_URL, SUPPORT_EMAIL, type Health, type Stats, type TicketSummary } from "@/lib/api";

const EXAMPLES = [
  "J'ai été facturé deux fois pour ma course d'hier soir !",
  "My food order was 30 minutes late and the spring rolls were missing.",
  "The driver was texting while driving on the highway and I felt unsafe.",
  "How do cancellation fees work?",
];

// Filters group the pipeline's decisions the way a support lead thinks about them.
const FILTERS = [
  { id: "all", label: "All", statuses: null },
  { id: "agent", label: "Needs an agent", statuses: ["awaiting_approval"] },
  { id: "escalated", label: "Escalated", statuses: ["escalated"] },
  { id: "answered", label: "Answered", statuses: ["auto_send", "answered"] },
  { id: "quiet", label: "No reply needed", statuses: ["no_reply", "closed"] },
] as const;
type FilterId = (typeof FILTERS)[number]["id"];

const SITE = "/en";

function ago(iso: string, now: number): string {
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto", style: "short" });
  if (Math.abs(seconds) < 60) return "just now";
  if (Math.abs(seconds) < 3600) return rtf.format(Math.round(seconds / 60), "minute");
  if (Math.abs(seconds) < 86400) return rtf.format(Math.round(seconds / 3600), "hour");
  return rtf.format(Math.round(seconds / 86400), "day");
}

function customer(t: TicketSummary): string {
  if (t.sender.startsWith("forum:")) return `@${t.sender.slice(6)}`;
  return t.sender_name ? `${t.sender_name}` : t.sender;
}

function Priority({ value }: { value: number | null }) {
  if (value == null) return <span className="text-muted">…</span>;
  const tone = value >= 70 ? "bg-escalated" : value >= 40 ? "bg-review" : "bg-quiet";
  return (
    <span className="flex items-center gap-2" aria-label={`Priority ${value} of 100`}>
      <span className="h-1.5 w-12 rounded-full bg-desk" aria-hidden>
        <span className={`block h-1.5 rounded-full ${tone}`} style={{ width: `${Math.max(value, 4)}%` }} />
      </span>
      <span className="w-6 text-right">{value}</span>
    </span>
  );
}

export default function InboxPage() {
  const router = useRouter();
  const [tickets, setTickets] = useState<TicketSummary[] | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterId>("all");
  const [composerOpen, setComposerOpen] = useState(false);
  const [draft, setDraft] = useState(EXAMPLES[0]);
  const [sending, setSending] = useState(false);
  const [copied, setCopied] = useState(false);
  const [fresh, setFresh] = useState<Set<number>>(new Set());
  const [now, setNow] = useState(() => Date.now());
  const known = useRef<Set<number> | null>(null);

  // Bumped by live events; every bump reloads the list (and ignores answers that arrive too late).
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let active = true;
    Promise.all([api.tickets(), api.stats()])
      .then(([t, s]) => {
        if (!active) return;
        // Rows that were not there before arrive highlighted (not on the first load).
        if (known.current) {
          const added = t.filter((x) => !known.current!.has(x.id)).map((x) => x.id);
          if (added.length) setFresh(new Set(added));
        }
        known.current = new Set(t.map((x) => x.id));
        setTickets(t);
        setStats(s);
        setError(null);
        setNow(Date.now());
      })
      .catch((e: Error) => {
        if (active) setError(`The API is not reachable right now (${e.message}). It may be waking up: try again in a few seconds.`);
      });
    return () => {
      active = false;
    };
  }, [version]);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    const tick = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(tick);
  }, []);

  useEffect(() => {
    if (fresh.size === 0) return;
    const timer = setTimeout(() => setFresh(new Set()), 4000);
    return () => clearTimeout(timer);
  }, [fresh]);

  const connected = useEvents((event) => {
    if (event.type !== "stage") setVersion((v) => v + 1);
  });

  const counts = useMemo(() => {
    const out: Record<FilterId, number> = { all: 0, agent: 0, escalated: 0, answered: 0, quiet: 0 };
    for (const t of tickets ?? []) {
      out.all += 1;
      for (const f of FILTERS)
        if (f.statuses && (f.statuses as readonly string[]).includes(t.status)) out[f.id] += 1;
    }
    return out;
  }, [tickets]);

  const shown = useMemo(() => {
    const f = FILTERS.find((x) => x.id === filter)!;
    return (tickets ?? []).filter((t) => !f.statuses || (f.statuses as readonly string[]).includes(t.status));
  }, [tickets, filter]);

  async function sendTest(e: FormEvent) {
    e.preventDefault();
    setSending(true);
    try {
      // example.com is reserved for examples (RFC 2606) and accepted by the email validator.
      const t = await api.submit({ email: "console.demo@example.com", body: draft, channel: "web" });
      router.push(`/console/ticket/?id=${t.id}`);
    } catch (err) {
      setError((err as Error).message);
      setSending(false);
    }
  }

  async function copyEmail(address: string) {
    try {
      await navigator.clipboard.writeText(address);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard unavailable: the address stays visible to copy by hand
    }
  }

  const total = stats?.tickets ?? 0;
  const auto = stats?.by_status.auto_send ?? 0;
  // The address is known before the health check answers: showing it at once avoids a layout shift.
  const email = health?.email.enabled === false ? null : (health?.email.address ?? SUPPORT_EMAIL);

  return (
    <main className="mx-auto max-w-7xl px-5 py-8">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <h1 className="text-2xl font-semibold">Inbox</h1>
        <span className="flex items-center gap-2 text-sm text-muted" role="status">
          <span
            className={`size-2 rounded-full ${connected ? "bg-sent" : "bg-quiet"}`}
            aria-hidden
          />
          {connected ? "Live. New messages appear here as they arrive." : "Connecting to live updates…"}
        </span>
        {/* Rendered before the health check answers (empty) so the page does not shift. */}
        <span className="min-h-5 text-sm text-muted md:ml-auto">
          {health &&
            (health.llm.enabled ? `Language model ${health.llm.model}` : "No language model (classical fallback)")}
        </span>
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-lg bg-red-50 px-4 py-3 text-escalated">
          {error}
        </p>
      )}

      <dl className="mt-6 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line md:grid-cols-5">
        {[
          ["Messages", total, null],
          ["Answered automatically", auto, total ? `${Math.round((auto / total) * 100)}% of messages` : null],
          ["Waiting for an agent", stats?.by_status.awaiting_approval ?? 0, "AI draft ready to approve"],
          ["Escalated", stats?.by_status.escalated ?? 0, "Safety or legal risk"],
          [
            "Average processing",
            stats ? `${(stats.avg_processing_ms / 1000).toFixed(1)} s` : "…",
            "From arrival to decision",
          ],
        ].map(([label, value, hint]) => (
          <div key={label as string} className="bg-white px-4 py-3">
            <dt className="text-sm text-muted">{label}</dt>
            <dd className="mt-1 text-2xl font-semibold">{stats ? value : "…"}</dd>
            {/* Always present (a no-break space until the numbers load) so nothing shifts. */}
            <dd className="text-xs text-muted">{(stats && hint) || " "}</dd>
          </div>
        ))}
      </dl>

      <section aria-labelledby="reach" className="mt-6 rounded-xl border border-line bg-white px-4 py-3">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3 text-sm">
          <h2 id="reach" className="font-semibold">
            Send a complaint from anywhere
          </h2>
          {email && (
            <span className="flex items-center gap-2">
              <ChannelMark channel="email" showLabel={false} />
              <a href={`mailto:${email}`} className="underline-offset-2 hover:underline">
                {email}
              </a>
              <button type="button" onClick={() => copyEmail(email)} className="text-xs text-muted hover:text-ink">
                {copied ? "Copied" : "Copy"}
              </button>
            </span>
          )}
          <Link href={`${SITE}/contact`} className="hover:underline">
            <ChannelMark channel="web" />
          </Link>
          <Link href={`${SITE}/?chat=open`} className="hover:underline">
            <ChannelMark channel="chat" />
          </Link>
          <Link href={`${SITE}/rate`} className="hover:underline">
            <ChannelMark channel="review" />
          </Link>
          <a href={FORUM_URL} target="_blank" rel="noreferrer" className="hover:underline">
            <ChannelMark channel="forum" />
          </a>
          <button
            type="button"
            onClick={() => setComposerOpen(!composerOpen)}
            aria-expanded={composerOpen}
            className="rounded-lg bg-ink px-3 py-1.5 font-semibold text-white md:ml-auto"
          >
            {composerOpen ? "Close test message" : "Write a test message"}
          </button>
        </div>
        {composerOpen && (
          <form onSubmit={sendTest} className="mt-4 border-t border-line pt-4">
            <label className="text-sm font-medium" htmlFor="test-message">
              Message, as a customer would write it (English or French)
            </label>
            <textarea
              id="test-message"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={3}
              className="mt-1 w-full rounded-lg border border-line px-3 py-2 text-sm"
            />
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => setDraft(example)}
                  className="max-w-64 truncate rounded-full border border-line px-2.5 py-0.5 text-xs hover:border-ink"
                  title={example}
                >
                  {example}
                </button>
              ))}
              <button
                type="submit"
                disabled={sending || draft.trim().length < 2}
                className="ml-auto rounded-lg bg-sent px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
              >
                {sending ? "Sending…" : "Send and watch the pipeline"}
              </button>
            </div>
          </form>
        )}
      </section>

      <div role="tablist" aria-label="Filter by decision" className="mt-6 flex flex-wrap gap-1 border-b border-line">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            role="tab"
            type="button"
            aria-selected={filter === f.id}
            onClick={() => setFilter(f.id)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${
              filter === f.id ? "border-ink font-semibold" : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {f.label} <span className="ml-1 text-muted">{counts[f.id]}</span>
          </button>
        ))}
      </div>

      <div className="mt-3 overflow-x-auto rounded-xl border border-line bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-line text-muted">
            <tr>
              <th scope="col" className="px-4 py-2.5 font-medium">Ticket</th>
              <th scope="col" className="hidden px-4 py-2.5 font-medium md:table-cell">Received</th>
              <th scope="col" className="hidden px-4 py-2.5 font-medium lg:table-cell">Channel</th>
              <th scope="col" className="hidden px-4 py-2.5 font-medium lg:table-cell">Customer</th>
              <th scope="col" className="px-4 py-2.5 font-medium">Message</th>
              <th scope="col" className="hidden px-4 py-2.5 font-medium md:table-cell">Team</th>
              <th scope="col" className="hidden px-4 py-2.5 font-medium sm:table-cell">Priority</th>
              <th scope="col" className="px-4 py-2.5 font-medium">Decision</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {shown.map((t) => (
              <tr
                key={t.id}
                onClick={() => router.push(`/console/ticket/?id=${t.id}`)}
                className={`cursor-pointer align-top hover:bg-desk ${fresh.has(t.id) ? "row-new" : ""}`}
              >
                <td className="whitespace-nowrap px-4 py-3">
                  <Link
                    href={`/console/ticket/?id=${t.id}`}
                    onClick={(e) => e.stopPropagation()}
                    className="font-semibold underline-offset-2 hover:underline"
                  >
                    {t.number}
                  </Link>
                  {t.language && <span className="ml-2 text-xs uppercase text-muted">{t.language}</span>}
                </td>
                <td className="hidden whitespace-nowrap px-4 py-3 text-muted md:table-cell">
                  <time dateTime={t.received_at} title={new Date(t.received_at).toLocaleString()}>
                    {ago(t.received_at, now)}
                  </time>
                </td>
                <td className="hidden px-4 py-3 lg:table-cell">
                  <ChannelMark channel={t.channel} />
                </td>
                <td className="hidden max-w-44 truncate px-4 py-3 lg:table-cell">{customer(t)}</td>
                <td className="max-w-md px-4 py-3">
                  <p className="line-clamp-2">{t.summary ?? t.subject ?? "Reading the message…"}</p>
                  {t.message_type && (
                    <p className="mt-0.5 text-xs text-muted">
                      {humanize(t.message_type)}
                      {t.categories.length > 0 && `, ${t.categories.map(humanize).join(", ")}`}
                      {t.risk_flags.length > 0 && (
                        <span className="font-semibold text-escalated">, risk: {t.risk_flags.map(humanize).join(", ")}</span>
                      )}
                    </p>
                  )}
                </td>
                <td className="hidden whitespace-nowrap px-4 py-3 md:table-cell">{t.team ?? "…"}</td>
                <td className="hidden px-4 py-3 sm:table-cell">
                  <Priority value={t.priority} />
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <StatusPill status={t.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {tickets && shown.length === 0 && (
          <p className="px-4 py-10 text-center text-muted">
            {tickets.length === 0
              ? "No messages yet. Send one by email, from the website, the chat, a trip rating or the forum, and it appears here within seconds."
              : "Nothing with this decision right now."}
          </p>
        )}
        {!tickets && !error && <p className="px-4 py-10 text-center text-muted">Loading the inbox…</p>}
      </div>
    </main>
  );
}
