// Every conversation is in one of these states. Colour carries the meaning: teal = done,
// amber = waiting for you, red = urgent, grey = nothing to do.

export const STATUS: Record<string, { label: string; help: string; className: string }> = {
  processing: {
    label: "AI is reading",
    help: "The AI is reading the latest message.",
    className: "bg-blue-50 text-blue-800 ring-blue-200",
  },
  auto_send: {
    label: "Solved by AI",
    help: "The AI answered, and its answer passed every check.",
    className: "bg-teal-50 text-sent ring-teal-200",
  },
  awaiting_approval: {
    label: "Needs reply",
    help: "An agent must reply. The AI has prepared a suggestion when it could.",
    className: "bg-amber-50 text-review ring-amber-200",
  },
  escalated: {
    label: "Urgent",
    help: "Safety or legal risk. The customer was told our Safety team will contact them.",
    className: "bg-red-50 text-escalated ring-red-200",
  },
  answered: {
    label: "Answered",
    help: "An agent replied. It comes back here if the customer writes again.",
    className: "bg-teal-50 text-sent ring-teal-200",
  },
  no_reply: {
    label: "No reply needed",
    help: "Spam, or nothing to answer.",
    className: "bg-gray-100 text-quiet ring-gray-200",
  },
  closed: {
    label: "Resolved",
    help: "Closed by an agent. It reopens if the customer writes again.",
    className: "bg-gray-100 text-quiet ring-gray-200",
  },
};

export function StatusPill({ status }: { status: string }) {
  const s = STATUS[status] ?? { label: humanize(status), help: "", className: "bg-gray-100 text-quiet ring-gray-200" };
  return (
    <span title={s.help} className={`inline-flex whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ${s.className}`}>
      {s.label}
    </span>
  );
}

export function statusLabel(status: string): string {
  return STATUS[status]?.label ?? humanize(status);
}

export function humanize(value: string): string {
  return value.replaceAll("_", " ");
}
