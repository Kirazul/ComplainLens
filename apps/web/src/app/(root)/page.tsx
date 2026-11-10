"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

// "/" forwards to /fr for French-speaking browsers and /en otherwise (static hosting has no
// server-side redirect). The links stay visible in case scripts are disabled.
export default function Root() {
  const router = useRouter();
  useEffect(() => {
    const prefersFrench = navigator.languages?.some((l) => l.toLowerCase().startsWith("fr"));
    router.replace(prefersFrench ? "/fr" : "/en");
  }, [router]);
  return (
    <main className="flex min-h-screen items-center justify-center gap-6 text-paper">
      <Link href="/en">English</Link>
      <Link href="/fr">Français</Link>
    </main>
  );
}
