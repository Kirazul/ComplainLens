import type { Channel } from "@/lib/api";

// Where a message came from. Icons are drawn on a 16px grid with a 1.5px stroke so they read at
// table size; the label is always shown next to the icon (an icon alone is a guessing game).
const CHANNELS: Record<Channel, { label: string; path: string }> = {
  email: {
    label: "Email",
    path: "M2.5 4.5h11v7h-11z M2.5 4.5 8 9l5.5-4.5",
  },
  web: {
    label: "Contact form",
    path: "M3 2.5h7l3 3v8H3z M10 2.5v3h3 M5.5 8.5h5 M5.5 11h3.5",
  },
  chat: {
    label: "Live chat",
    path: "M2.5 3.5h11v7H7l-3 2.5v-2.5H2.5z",
  },
  review: {
    label: "Trip rating",
    path: "M8 2.5l1.6 3.4 3.7.5-2.7 2.6.7 3.7L8 11l-3.3 1.7.7-3.7-2.7-2.6 3.7-.5z",
  },
  forum: {
    label: "Community forum",
    path: "M2.5 3h7.5v5H5.5L3.5 9.5V8h-1z M10 6h3.5v5h-1v1.5L10.5 11H7V8",
  },
};

export function channelLabel(channel: string): string {
  return CHANNELS[channel as Channel]?.label ?? channel;
}

export function ChannelMark({ channel, showLabel = true }: { channel: string; showLabel?: boolean }) {
  const c = CHANNELS[channel as Channel];
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap" title={c?.label ?? channel}>
      <svg
        viewBox="0 0 16 16"
        className="size-4 shrink-0 text-muted"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
        aria-hidden
      >
        <path d={c?.path ?? "M4 8h8"} />
      </svg>
      {showLabel ? <span>{c?.label ?? channel}</span> : <span className="sr-only">{c?.label ?? channel}</span>}
    </span>
  );
}
