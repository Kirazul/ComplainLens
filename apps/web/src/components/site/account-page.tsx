"use client";

import Link from "next/link";

import { AuthForm, signOut, useAccount } from "@/components/site/account";
import type { Lang } from "@/lib/api";
import type { Dict } from "@/lib/i18n";

export function AccountPage({ lang, t }: { lang: Lang; t: Dict }) {
  const me = useAccount();
  if (me === undefined) return <div className="h-80" aria-busy />;
  if (!me) return <AuthForm lang={lang} t={t.account} />;
  return (
    <div>
      <h1 className="font-display text-4xl font-extrabold tracking-tight text-night">{me.customer.name}</h1>
      <p className="mt-2 text-slate">{me.customer.email}</p>
      <div className="mt-8 flex flex-wrap gap-3">
        <Link href={`/${lang}/rides`} className="rounded-full bg-night px-6 py-3 font-semibold text-paper hover:bg-night-soft">
          {t.nav.rides}
        </Link>
        <Link href={`/${lang}/book`} className="rounded-full bg-amber px-6 py-3 font-semibold text-night hover:bg-night hover:text-paper">
          {t.nav.book}
        </Link>
        <button type="button" onClick={signOut} className="rounded-full px-6 py-3 font-semibold text-night ring-1 ring-lilac hover:ring-night">
          {t.nav.signOut}
        </button>
      </div>
    </div>
  );
}
