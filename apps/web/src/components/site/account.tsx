"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useId, useRef, useState, useSyncExternalStore, type FormEvent, type ReactNode } from "react";

import { account, api, ApiError, type Account, type Lang } from "@/lib/api";
import type { Dict } from "@/lib/i18n";

/** The signed-in customer; `undefined` before the browser has read it (first render). */
export function useAccount(): Account | null | undefined {
  return useSyncExternalStore(account.subscribe, account.get, () => undefined);
}

export async function signOut() {
  try {
    await api.signout();
  } catch {
    // already expired or offline: forget it locally anyway
  }
  account.set(null);
}

// Header: "Sign in", or the customer's name with a small menu.
export function AccountButton({ lang, t }: { lang: Lang; t: Dict["nav"] }) {
  const me = useAccount();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  if (me === undefined) return <span className="inline-block h-9 w-24" aria-hidden />;
  if (!me)
    return (
      <Link href={`/${lang}/account`} className="rounded-full bg-paper px-4 py-2 text-sm font-semibold text-night hover:bg-amber">
        {t.signIn}
      </Link>
    );
  const first = me.customer.name.split(/\s+/)[0] || me.customer.email;
  return (
    <div className="relative" ref={box}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls={menuId}
        className="flex items-center gap-2 rounded-full py-1 pl-1 pr-3 text-sm font-semibold ring-1 ring-lilac/40 hover:ring-amber"
      >
        <span aria-hidden className="grid size-7 place-items-center rounded-full bg-amber text-xs font-bold text-night">
          {first.charAt(0).toUpperCase()}
        </span>
        <span className="max-w-28 truncate">{first}</span>
      </button>
      {open && (
        <div id={menuId} className="absolute right-0 z-30 mt-2 w-56 rounded-2xl bg-white p-1.5 text-sm text-night shadow-xl ring-1 ring-night/10">
          <p className="truncate px-3 py-2 text-slate/80">{me.customer.email}</p>
          <Link href={`/${lang}/rides`} onClick={() => setOpen(false)} className="block rounded-xl px-3 py-2 hover:bg-paper">
            {t.rides}
          </Link>
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              signOut();
            }}
            className="block w-full rounded-xl px-3 py-2 text-left hover:bg-paper"
          >
            {t.signOut}
          </button>
        </div>
      )}
    </div>
  );
}

/** Shows `children` to a signed-in customer, the sign-in form otherwise. */
export function RequireAccount({ lang, t, title, children }: { lang: Lang; t: Dict; title: string; children: ReactNode }) {
  const me = useAccount();
  if (me === undefined) return <div className="min-h-64" aria-busy />;
  if (!me)
    return (
      <div className="max-w-md">
        <p className="text-lg text-night">{title}</p>
        <div className="mt-6">
          <AuthForm lang={lang} t={t.account} />
        </div>
      </div>
    );
  return <>{children}</>;
}

// Sign in or create an account. After success, go to ?next= (or stay).
export function AuthForm({ lang, t, initialMode = "signin" }: { lang: Lang; t: Dict["account"]; initialMode?: "signin" | "signup" }) {
  const router = useRouter();
  const next = useSearchParams().get("next");
  const [mode, setMode] = useState(initialMode);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const d = new FormData(e.currentTarget);
    const email = String(d.get("email") ?? "").trim();
    const password = String(d.get("password") ?? "");
    setBusy(true);
    setError(null);
    try {
      const session =
        mode === "signup"
          ? await api.signup(email, String(d.get("name") ?? "").trim(), password, lang)
          : await api.signin(email, password);
      account.set(session);
      if (next?.startsWith(`/${lang}/`)) router.push(next);
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      setError(
        status === 401 ? t.wrong : status === 409 ? t.exists : status === 422 ? t.weak : status === 429 ? t.busy : t.network,
      );
    } finally {
      setBusy(false);
    }
  }

  const field = "mt-1.5 w-full rounded-xl border border-lilac bg-white px-4 py-3 text-night focus:border-night";
  return (
    <form onSubmit={submit} className="space-y-4">
      <h2 className="font-display text-2xl font-bold text-night">{mode === "signup" ? t.signUpTitle : t.signInTitle}</h2>
      {mode === "signup" && (
        <label className="block">
          <span className="font-semibold text-night">{t.name}</span>
          <input name="name" required maxLength={60} autoComplete="name" className={field} />
        </label>
      )}
      <label className="block">
        <span className="font-semibold text-night">{t.email}</span>
        <input name="email" type="email" required autoComplete="email" className={field} />
      </label>
      <label className="block">
        <span className="font-semibold text-night">{t.password}</span>
        <input
          name="password"
          type="password"
          required
          minLength={mode === "signup" ? 8 : undefined}
          autoComplete={mode === "signup" ? "new-password" : "current-password"}
          className={field}
        />
        {mode === "signup" && <span className="mt-1 block text-sm text-slate">{t.passwordHint}</span>}
      </label>
      {error && (
        <p role="alert" className="rounded-xl bg-amber/15 px-4 py-3 text-night">
          {error}
        </p>
      )}
      <button type="submit" disabled={busy} className="w-full rounded-full bg-night py-3 font-semibold text-paper hover:bg-night-soft disabled:opacity-60">
        {busy ? "…" : mode === "signup" ? t.signUp : t.signIn}
      </button>
      <button
        type="button"
        onClick={() => {
          setMode(mode === "signup" ? "signin" : "signup");
          setError(null);
        }}
        className="block text-sm font-semibold text-night underline decoration-lilac decoration-2 underline-offset-4 hover:decoration-amber"
      >
        {mode === "signup" ? t.toSignIn : t.toSignUp}
      </button>
      {mode === "signup" && <p className="text-sm text-slate/80">{t.demo}</p>}
    </form>
  );
}
