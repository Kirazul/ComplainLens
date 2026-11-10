import type { Lang } from "./api";

const locale = (lang: Lang) => (lang === "fr" ? "fr-CA" : "en-CA");

export function money(amount: number, lang: Lang): string {
  return new Intl.NumberFormat(locale(lang), { style: "currency", currency: "CAD" }).format(amount);
}

export function dateTime(iso: string, lang: Lang): string {
  return new Intl.DateTimeFormat(locale(lang), { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso));
}
