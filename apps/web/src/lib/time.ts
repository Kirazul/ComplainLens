// "just now", "5 min. ago", "2 hr. ago": short relative times for lists and conversations.
export function ago(iso: string, now: number, locale = "en"): string {
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto", style: "short" });
  if (Math.abs(seconds) < 60) return locale === "fr" ? "à l'instant" : "just now";
  if (Math.abs(seconds) < 3600) return rtf.format(Math.round(seconds / 60), "minute");
  if (Math.abs(seconds) < 86400) return rtf.format(Math.round(seconds / 3600), "hour");
  return rtf.format(Math.round(seconds / 86400), "day");
}
