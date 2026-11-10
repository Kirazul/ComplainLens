"use client";

import { Fragment, useState } from "react";

import type { ReplyRecord } from "@/lib/api";

export type Sources = Record<string, { title: string; text: string }>;

const CITATION = /\[((?:HC-[A-Z]+#\d+)|(?:F\d+))\]/g;

// The reply with its citations as buttons: each opens the exact source it claims to rely on.
export function CitedText({ text, sources }: { text: string; sources: Sources }) {
  const [open, setOpen] = useState<string | null>(null);
  const parts = text.split(CITATION);
  return (
    <div>
      <p className="whitespace-pre-line leading-relaxed">
        {parts.map((part, i) =>
          i % 2 === 1 ? (
            <button
              key={i}
              type="button"
              onClick={() => setOpen(open === part ? null : part)}
              aria-expanded={open === part}
              className={`mx-0.5 rounded px-1 text-xs font-semibold ring-1 ${
                sources[part] ? "bg-blue-50 text-blue-800 ring-blue-200" : "bg-red-50 text-escalated ring-red-300"
              }`}
              title={sources[part] ? "Show source" : "Unknown source"}
            >
              {part}
            </button>
          ) : (
            <Fragment key={i}>{part}</Fragment>
          ),
        )}
      </p>
      {open && (
        <div className="mt-3 rounded-lg border border-blue-200 bg-blue-50/60 p-3 text-sm">
          <p className="font-semibold">
            {open} {sources[open] ? `· ${sources[open].title}` : ""}
          </p>
          <p className="mt-1">{sources[open]?.text ?? "This citation does not match any provided source."}</p>
        </div>
      )}
    </div>
  );
}

export function Verification({ v }: { v: Record<string, unknown> }) {
  if (!v || Object.keys(v).length === 0) return null;
  const unsupported = (v.unsupported_numbers as number[]) ?? [];
  const unknown = (v.unknown_citations as string[]) ?? [];
  const checks: [boolean, string][] = [
    [unknown.length === 0, unknown.length ? `Unknown citations: ${unknown.join(", ")}` : "Every citation exists"],
    [
      unsupported.length === 0,
      unsupported.length
        ? `Numbers not found in the cited sources: ${unsupported.join(", ")}`
        : `All ${String(v.numbers_checked ?? 0)} numbers appear in the cited sources`,
    ],
  ];
  if (v.edited_by_agent) checks.push([true, "Edited by an agent before sending"]);
  return (
    <ul className="space-y-1 text-sm">
      {checks.map(([ok, label]) => (
        <li key={label} className={ok ? "text-sent" : "text-escalated"}>
          <span aria-hidden>{ok ? "✓" : "✗"}</span> {label}
        </li>
      ))}
    </ul>
  );
}

export function ReplyCard({ reply, sources }: { reply: ReplyRecord; sources: Sources }) {
  const label = { answer: "Answer", acknowledgement: "Acknowledgement", escalation: "Safety acknowledgement" }[reply.kind];
  const state = {
    sent: `Sent ${reply.sent_at ? new Date(reply.sent_at).toLocaleTimeString() : ""}`,
    queued: "Waiting for the forum relay to post it",
    failed:
      reply.error === "no outbound delivery for this channel"
        ? "Not delivered: the support inbox can only receive"
        : `Not delivered: ${reply.error ?? "unknown error"}`,
    draft: "Draft, not sent",
  }[reply.status];
  return (
    <article className="rounded-xl border border-line bg-white p-4">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="font-semibold">{label}</h3>
        <span className={`text-xs ${reply.status === "failed" ? "text-escalated" : "text-muted"}`}>{state}</span>
      </div>
      <div className="mt-2 text-sm">
        <CitedText text={reply.body} sources={sources} />
      </div>
    </article>
  );
}
