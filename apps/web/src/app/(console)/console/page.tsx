"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { humanize, StatusPill } from "@/components/console/status";
import { useEvents } from "@/components/console/use-events";
import { api, type Health, type Stats, type TicketSummary } from "@/lib/api";

const EXAMPLES = [
  "J'ai été facturé deux fois pour ma course d'hier soir !",
  "My food order was 30 minutes late and the spring rolls were missing.",
  "The driver was texting while driving on the highway and I felt unsafe.",
  "How do cancellation fees work?",
];

export default function InboxPage() {
  const router = useRouter();
  const [tickets, setTickets] = useState<TicketSummary[] | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState(EXAMPLES[0]);
  const [sending, setSending] = useState(false);

  // Bumped by live events; every bump reloads the list (and ignores answers that arrive too late).
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let active = true;
    Promise.all([api.tickets(), api.stats()])
      .then(([t, s]) => {
        if (!active) return;
        setTickets(t);
        setStats(s);
        setError(null);
      })
      .catch((e: Error) => {
        if (active) setError(`The API is not reachable (${e.message}). Start it with: uv run complaintlens serve`);
      });
    return () => {
      active = false;
    };
  }, [version]);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  const connected = useEvents((event) => {
    if (event.type !== "stage") setVersion((v) => v + 1);
  });

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

  return (
    <main className="mx-auto max-w-7xl px-5 py-8">
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
        <h1 className="text-2xl font-semibold">Inbox</h1>
        <span className="text-sm text-muted">
          {connected ? "Live: new messages appear here as they arrive" : "Connecting to live updates…"}
        </span>
        {health && (
          <span className="ml-auto text-sm text-muted">
            Model {health.llm.enabled ? health.llm.model : "not configured (classical fallback)"} · Email{" "}
            {health.email.enabled ? health.email.address : "not configured"}
          </span>
        )}
      </div>

      {error && <p role="alert" className="mt-4 rounded-lg bg-red-50 px-4 py-3 text-escalated">{error}</p>}

      {stats && (
        <dl className="mt-6 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-5">
          {[
            ["Tickets", stats.tickets],
            ["Sent automatically", stats.by_status.auto_send ?? 0],
            ["Awaiting approval", stats.by_status.awaiting_approval ?? 0],
            ["Escalated", stats.by_status.escalated ?? 0],
            ["Average processing", `${(stats.avg_processing_ms / 1000).toFixed(2)} s`],
          ].map(([label, value]) => (
            <div key={label} className="bg-white px-4 py-3">
              <dt className="text-xs text-muted">{label}</dt>
              <dd className="mt-1 text-2xl font-semibold">{value}</dd>
            </div>
          ))}
        </dl>
      )}

      <div className="mt-8 grid gap-8 lg:grid-cols-[1fr_22rem]">
        <section aria-label="Tickets">
          {tickets && tickets.length === 0 && (
            <p className="rounded-xl border border-dashed border-line bg-white p-8 text-muted">
              No messages yet. Send one from the customer site, by email, or with the form on the right.
            </p>
          )}
          <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-white">
            {tickets?.map((t) => (
              <li key={t.id}>
                <Link href={`/console/ticket/?id=${t.id}`} className="block px-4 py-3 hover:bg-desk">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="font-semibold">{t.number}</span>
                    <StatusPill status={t.status} />
                    {t.risk_flags.length > 0 && (
                      <span className="text-xs font-semibold text-escalated">{t.risk_flags.map(humanize).join(", ")}</span>
                    )}
                    <span className="ml-auto text-sm text-muted">
                      {t.team ?? "…"} · priority {t.priority ?? "…"} · {t.channel} · {t.language ?? "…"}
                    </span>
                  </div>
                  <p className="mt-1 truncate text-sm text-muted">
                    {t.summary ?? t.subject ?? t.sender}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        </section>

        <aside>
          <form onSubmit={sendTest} className="rounded-xl border border-line bg-white p-4">
            <h2 className="font-semibold">Send a test message</h2>
            <p className="mt-1 text-sm text-muted">
              Arrives as a customer message from the website, then opens its X-ray.
            </p>
            <label className="mt-3 block text-sm font-medium" htmlFor="test-message">
              Message
            </label>
            <textarea
              id="test-message"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={5}
              className="mt-1 w-full rounded-lg border border-line px-3 py-2 text-sm"
            />
            <div className="mt-2 flex flex-wrap gap-2">
              {EXAMPLES.map((example, i) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => setDraft(example)}
                  className="rounded-full border border-line px-2.5 py-0.5 text-xs hover:border-ink"
                >
                  Example {i + 1}
                </button>
              ))}
            </div>
            <button
              type="submit"
              disabled={sending || draft.trim().length < 2}
              className="mt-4 w-full rounded-lg bg-ink px-4 py-2 font-semibold text-white disabled:opacity-60"
            >
              {sending ? "Sending…" : "Send and watch"}
            </button>
          </form>
        </aside>
      </div>
    </main>
  );
}
