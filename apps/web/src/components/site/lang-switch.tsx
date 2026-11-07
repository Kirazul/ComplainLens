"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import type { Lang } from "@/lib/api";

// Switch language while staying on the same page (and keeping a tracking key, if any).
export function LangSwitch({ current, label }: { current: Lang; label: string }) {
  const pathname = usePathname();
  const search = useSearchParams();
  const other: Lang = current === "en" ? "fr" : "en";
  const target = pathname.replace(/^\/(en|fr)(?=\/|$)/, `/${other}`);
  const query = search.toString();
  return (
    <Link
      href={query ? `${target}?${query}` : target}
      hrefLang={other}
      lang={other}
      className="rounded-full border border-lilac/50 px-3 py-1 text-sm hover:border-amber hover:text-amber"
    >
      {label}
    </Link>
  );
}
