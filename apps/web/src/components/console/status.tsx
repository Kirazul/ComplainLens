// Status colours carry meaning in the console: teal = sent automatically, amber = waiting for a
// human, red = escalated, grey = no reply needed.

const STATUS: Record<string, { label: string; className: string }> = {
  processing: { label: "Processing", className: "bg-blue-50 text-blue-800 ring-blue-200" },
  auto_send: { label: "Sent automatically", className: "bg-teal-50 text-sent ring-teal-200" },
  answered: { label: "Answered by agent", className: "bg-teal-50 text-sent ring-teal-200" },
  awaiting_approval: { label: "Awaiting approval", className: "bg-amber-50 text-review ring-amber-200" },
  escalated: { label: "Escalated", className: "bg-red-50 text-escalated ring-red-200" },
  no_reply: { label: "No reply needed", className: "bg-gray-100 text-quiet ring-gray-200" },
  closed: { label: "Closed", className: "bg-gray-100 text-quiet ring-gray-200" },
};

export function StatusPill({ status }: { status: string }) {
  const s = STATUS[status] ?? { label: status, className: "bg-gray-100 text-quiet ring-gray-200" };
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ${s.className}`}>
      {s.label}
    </span>
  );
}

export function humanize(value: string): string {
  return value.replaceAll("_", " ");
}
