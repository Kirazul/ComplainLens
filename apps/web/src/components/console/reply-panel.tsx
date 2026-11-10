"use client";

import { Fragment, useState } from "react";

export type Sources = Record<string, { title: string; text: string }>;

const CITATION = /\[((?:HC-[A-Z]+#\d+)|(?:F\d+))\]/g;

// A reply with its citations as buttons: each opens the exact source it relies on.
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
              title={sources[part] ? "Show the source" : "Unknown source"}
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
          <p className="mt-1">{sources[open]?.text ?? "This citation matches no source."}</p>
        </div>
      )}
    </div>
  );
}

// The automatic checks run on an AI reply before anyone sends it.
export function Verification({ v }: { v: Record<string, unknown> }) {
  if (!v || Object.keys(v).length === 0) return null;
  const unsupported = (v.unsupported_numbers as number[]) ?? [];
  const unknown = (v.unknown_citations as string[]) ?? [];
  const checks: [boolean, string][] = [
    [unknown.length === 0, unknown.length ? `Unknown sources: ${unknown.join(", ")}` : "Every source exists"],
    [
      unsupported.length === 0,
      unsupported.length
        ? `Numbers not found in its sources: ${unsupported.join(", ")}`
        : `${String(v.numbers_checked ?? 0)} numbers checked against the sources`,
    ],
  ];
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
      {checks.map(([ok, label]) => (
        <li key={label} className={ok ? "text-sent" : "font-semibold text-escalated"}>
          <span aria-hidden>{ok ? "✓" : "✗"}</span> {label}
        </li>
      ))}
    </ul>
  );
}
