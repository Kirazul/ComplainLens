"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState, useSyncExternalStore, type FormEvent, type ReactNode } from "react";

import { api, ApiError, session, type Session } from "@/lib/api";

/** The signed-in session; `undefined` before the browser has read it (first render). */
export function useSession(): Session | null | undefined {
  return useSyncExternalStore(session.subscribe, session.get, () => undefined);
}

export async function signOut() {
  try {
    await api.logout();
  } catch {
    // already expired or offline: forget it locally anyway
  }
  session.set(null);
}

// The console is for LunaGo staff only: without a session, every page shows the sign-in screen.
export function ConsoleShell({ children }: { children: ReactNode }) {
  const current = useSession();
  const checked = useRef(false);

  // Once per visit, refresh the account (name or role may have changed; a revoked session
  // signs out, see api.ts).
  useEffect(() => {
    if (!current || checked.current) return;
    checked.current = true;
    api
      .me()
      .then((user) => {
        const s = session.get();
        if (s && (s.user.name !== user.name || s.user.role !== user.role)) session.set({ ...s, user });
      })
      .catch(() => undefined);
  }, [current]);

  if (current === undefined) return <div className="min-h-screen" aria-busy />;
  if (current === null) return <SignIn />;
  return (
    <>
      <Header session={current} />
      {children}
    </>
  );
}

const NAV = [
  { href: "/console", label: "Inbox" },
  { href: "/console/insights", label: "Insights" },
  { href: "/console/annotate", label: "Annotate" },
] as const;

function Header({ session: s }: { session: Session }) {
  const path = usePathname().replace(/\/$/, "") || "/console";
  const links = s.user.role === "admin" ? [...NAV, { href: "/console/team", label: "Team" }] : NAV;
  const active = (href: string) => (href === "/console" ? path === "/console" || path.startsWith("/console/ticket") : path.startsWith(href));
  return (
    <header className="border-b border-line bg-white">
      <nav aria-label="Console" className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4 sm:gap-6 sm:px-5">
        <Link href="/console" className="flex items-center gap-2 font-semibold tracking-tight">
          <Crescent />
          <span className="hidden sm:inline">ComplaintLens</span>
        </Link>
        <div className="flex h-full gap-0.5 overflow-x-auto text-sm sm:gap-1">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              aria-current={active(l.href) ? "page" : undefined}
              className={`flex items-center whitespace-nowrap border-b-2 px-2 sm:px-2.5 ${
                active(l.href) ? "border-ink font-semibold" : "border-transparent text-muted hover:text-ink"
              }`}
            >
              {l.label}
            </Link>
          ))}
        </div>
        <div className="ml-auto shrink-0">
          <UserMenu session={s} />
        </div>
      </nav>
    </header>
  );
}

function UserMenu({ session: s }: { session: Session }) {
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

  const initials = s.user.name
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="relative" ref={box}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls={menuId}
        aria-label={`Account: ${s.user.name}`}
        className="flex items-center gap-2 rounded-full p-1 text-sm hover:bg-desk sm:pr-3"
      >
        <span aria-hidden className="grid size-7 place-items-center rounded-full bg-ink text-xs font-semibold text-white">
          {initials}
        </span>
        <span className="hidden max-w-32 truncate sm:inline">{s.user.name}</span>
      </button>
      {open && (
        <div id={menuId} className="absolute right-0 z-30 mt-2 w-56 rounded-xl border border-line bg-white p-1.5 text-sm shadow-lg">
          <p className="px-3 py-2 text-muted">
            Signed in as <span className="font-medium text-ink">{s.user.username}</span>
            <br />
            {s.user.role === "admin" ? "Administrator" : "Agent"}
          </p>
          <Link href="/console/account" onClick={() => setOpen(false)} className="block rounded-lg px-3 py-2 hover:bg-desk">
            Change password
          </Link>
          <Link href="/en" className="block rounded-lg px-3 py-2 hover:bg-desk">
            Open the LunaGo website
          </Link>
          <button type="button" onClick={signOut} className="block w-full rounded-lg px-3 py-2 text-left hover:bg-desk">
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function SignIn() {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      session.set(await api.login(String(data.get("username")), String(data.get("password"))));
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Wrong username or password."
          : err instanceof ApiError && err.status === 429
            ? "Too many attempts. Wait 15 minutes and try again."
            : "The server is not reachable. It may be waking up: try again in a few seconds.",
      );
      setBusy(false);
    }
  }

  const field = "mt-1 w-full rounded-lg border border-line bg-white px-3 py-2.5 focus:border-ink";
  return (
    <main className="grid min-h-screen place-items-center px-5 py-10">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-2.5 text-lg font-semibold">
          <Crescent size={28} />
          ComplaintLens
        </div>
        <h1 className="mt-8 text-2xl font-semibold">Sign in to the support console</h1>
        <p className="mt-1 text-muted">For LunaGo staff.</p>
        <form onSubmit={submit} className="mt-6 space-y-4 rounded-2xl border border-line bg-white p-6">
          <label className="block text-sm font-medium">
            Username
            <input name="username" required autoComplete="username" autoCapitalize="none" spellCheck={false} className={field} />
          </label>
          <label className="block text-sm font-medium">
            Password
            <input name="password" type="password" required autoComplete="current-password" className={field} />
          </label>
          {error && (
            <p role="alert" className="text-sm text-escalated">
              {error}
            </p>
          )}
          <button type="submit" disabled={busy} className="w-full rounded-lg bg-ink py-2.5 font-semibold text-white disabled:opacity-60">
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <Link href="/en" className="mt-6 inline-block text-sm text-muted hover:text-ink">
          Go to the LunaGo website
        </Link>
      </div>
    </main>
  );
}

function Crescent({ size = 22 }: { size?: number }) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden>
      <rect width="32" height="32" rx="8" fill="#172033" />
      <path d="M20.5 7.5a9 9 0 1 0 4 16.6A10 10 0 0 1 20.5 7.5Z" fill="#f2a33a" />
    </svg>
  );
}
