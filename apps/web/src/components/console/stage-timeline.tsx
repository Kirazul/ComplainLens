"use client";

import type { ReactNode } from "react";

import { humanize } from "@/components/console/status";
import type { StageRecord } from "@/lib/api";

const TITLES: Record<string, string> = {
  normalize: "Clean the message",
  pii_masking: "Mask personal data",
  language: "Detect the language",
  understand: "Understand",
  link: "Find the customer and the trip",
  respond: "Retrieve, draft, verify, decide",
};
const EXPECTED = Object.keys(TITLES);

type Out = Record<string, unknown>;

function Chips({ items, tone = "neutral" }: { items: unknown; tone?: "neutral" | "risk" }) {
  const list = Array.isArray(items) ? (items as string[]) : [];
  if (!list.length) return <span className="text-muted">none</span>;
  const cls = tone === "risk" ? "bg-red-50 text-escalated ring-red-200" : "bg-desk text-ink ring-line";
  return (
    <span className="inline-flex flex-wrap gap-1">
      {list.map((x) => (
        <span key={x} className={`rounded px-1.5 py-0.5 text-xs ring-1 ${cls}`}>
          {humanize(String(x))}
        </span>
      ))}
    </span>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[9rem_1fr] gap-3 py-0.5">
      <dt className="text-muted">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function StageBody({ stage }: { stage: StageRecord }) {
  const o = stage.output as Out;
  switch (stage.name) {
    case "normalize":
      return (
        <dl>
          <Row label="Kept">
            {String(o.chars_kept)} of {String(o.chars_received)} characters
          </Row>
          {o.subject ? <Row label="Subject">{String(o.subject)}</Row> : null}
        </dl>
      );
    case "pii_masking":
      return (
        <dl>
          <Row label="Masked">
            {Object.keys((o.masked as Out) ?? {}).length
              ? Object.entries(o.masked as Out).map(([k, v]) => `${v} ${k.toLowerCase()}`).join(", ")
              : "nothing to mask"}
          </Row>
        </dl>
      );
    case "language":
      return (
        <dl>
          <Row label="Language">
            {String(o.language)}
            {stage.confidence != null && <span className="text-muted"> · confidence {stage.confidence.toFixed(2)}</span>}
          </Row>
        </dl>
      );
    case "understand": {
      const classical = (o.classical as Out) ?? {};
      return (
        <dl>
          <Row label="Type">
            {humanize(String(o.message_type))} · {o.response_required ? "needs a reply" : "no reply needed"}
            {o.urgency ? ` · ${o.urgency}` : ""}
          </Row>
          <Row label="Categories"><Chips items={o.categories} /></Row>
          <Row label="Severity">{o.severity ? `${o.severity} of 4` : "n/a"} · {String(o.sentiment)}</Row>
          <Row label="Risk flags"><Chips items={o.risk_flags} tone="risk" /></Row>
          {Array.isArray(o.entities) && o.entities.length > 0 && (
            <Row label="Entities">
              <span className="inline-flex flex-wrap gap-1">
                {(o.entities as { type: string; text: string }[]).map((e) => (
                  <span key={e.type + e.text} className="rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-900 ring-1 ring-blue-200">
                    {e.text} <span className="text-blue-800">{humanize(e.type.toLowerCase())}</span>
                  </span>
                ))}
              </span>
            </Row>
          )}
          <Row label="Summary">{String(o.summary)}</Row>
          <Row label="Goal">{String(o.customer_goal)}</Row>
          <Row label="Sources">
            {o.source === "llm" ? "LLM with annotation guidelines" : "classical models (no LLM configured)"}
            {classical.complaint_probability != null &&
              ` · classical complaint probability ${Number(classical.complaint_probability).toFixed(2)}`}
          </Row>
          {Array.isArray(o.lexicon_flags_added) && o.lexicon_flags_added.length > 0 && (
            <Row label="Safety net"><span className="text-escalated">risk words added <Chips items={o.lexicon_flags_added} tone="risk" /></span></Row>
          )}
        </dl>
      );
    }
    case "link": {
      const customer = (o.customer as Out) ?? {};
      return (
        <dl>
          <Row label="Customer">
            {String(customer.name || "unnamed")}
            {customer.new_demo_profile ? <span className="text-muted"> · new demo profile created</span> : null}
          </Row>
          <Row label="Trip">{o.trip ? String(o.trip) : <span className="text-muted">no confident match: the reply asks</span>}</Row>
          {Array.isArray(o.why) && o.why.length > 0 && (
            <Row label="Why">
              <ul className="list-disc pl-4">{(o.why as string[]).map((w) => <li key={w}>{w}</li>)}</ul>
            </Row>
          )}
        </dl>
      );
    }
    case "respond": {
      const retrieved = (o.retrieved as { id: string; heading: string; score: number }[]) ?? [];
      const decision = (o.decision as Out) ?? {};
      return (
        <dl>
          <Row label="Retrieved">
            {retrieved.length ? (
              <ol className="space-y-0.5">
                {retrieved.map((r) => (
                  <li key={r.id}>
                    <span className="font-medium">{r.id}</span> {r.heading}{" "}
                    <span className="text-muted">score {r.score.toFixed(r.score < 1 ? 3 : 1)}</span>
                  </li>
                ))}
              </ol>
            ) : (
              <span className="text-muted">not needed for this decision</span>
            )}
          </Row>
          {o.retriever ? <Row label="Retriever">{String(o.retriever).replace("dense:", "dense, ")}</Row> : null}
          <Row label="Decision">{humanize(String(decision.action))}</Row>
        </dl>
      );
    }
    default:
      return <pre className="overflow-auto text-xs">{JSON.stringify(o, null, 2)}</pre>;
  }
}

export function StageTimeline({ stages, processing }: { stages: StageRecord[]; processing: boolean }) {
  const maxMs = Math.max(1, ...stages.map((s) => s.ms));
  const pending = processing ? EXPECTED.filter((name) => !stages.some((s) => s.name === name)) : [];
  return (
    <ol className="relative space-y-3 border-l-2 border-line pl-6">
      {stages.map((s) => (
        <li key={s.id} className="stage-in relative rounded-xl border border-line bg-white p-4">
          <span
            aria-hidden
            className={`absolute -left-[33px] top-5 size-4 rounded-full ring-4 ring-desk ${
              s.status === "error" ? "bg-escalated" : "bg-sent"
            }`}
          />
          <div className="flex flex-wrap items-baseline gap-x-3">
            <h3 className="font-semibold">
              {s.seq}. {TITLES[s.name] ?? s.name}
            </h3>
            <span className="ml-auto text-sm text-muted">{formatMs(s.ms)}</span>
          </div>
          <div className="mt-1 h-1 rounded bg-desk" aria-hidden>
            <div className="h-1 rounded bg-ink/70" style={{ width: `${Math.max(2, Math.sqrt(s.ms / maxMs) * 100)}%` }} />
          </div>
          <div className="mt-3 text-sm">
            <StageBody stage={s} />
          </div>
          {s.note && (
            <p className={`mt-2 text-sm ${s.status === "error" ? "text-escalated" : "text-review"}`}>{s.note}</p>
          )}
        </li>
      ))}
      {pending.map((name) => (
        <li key={name} className="relative rounded-xl border border-dashed border-line p-4 text-muted">
          <span aria-hidden className="absolute -left-[33px] top-5 size-4 animate-pulse rounded-full bg-line ring-4 ring-desk" />
          {TITLES[name]}…
        </li>
      ))}
    </ol>
  );
}

export function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${ms.toFixed(ms < 10 ? 2 : 0)} ms`;
}
