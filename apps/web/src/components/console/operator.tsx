"use client";

import { useEffect, useId, useRef, useState, useSyncExternalStore, type FormEvent } from "react";

import { api, operatorToken } from "@/lib/api";

// One shared answer to "is this browser signed in as a support agent?", verified against the API.
// "unknown" until the saved token has been checked.
type OperatorState = "unknown" | "agent" | "viewer";

let current: OperatorState = "unknown";
const listeners = new Set<() => void>();

function publish(next: OperatorState) {
  current = next;
  listeners.forEach((listener) => listener());
}

let checked = false;
function verifySavedToken() {
  if (checked) return;
  checked = true;
  api
    .operator()
    .then((r) => publish(r.operator ? "agent" : "viewer"))
    .catch(() => publish("viewer"));
}

export function useOperator() {
  const state = useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      verifySavedToken();
      return () => listeners.delete(listener);
    },
    () => current,
    () => "unknown" as OperatorState,
  );
  return {
    state,
    async signIn(token: string): Promise<boolean> {
      const { operator } = await api.operator(token);
      if (operator) {
        operatorToken.set(token);
        publish("agent");
      }
      return operator;
    },
    signOut() {
      operatorToken.set(null);
      publish("viewer");
    },
  };
}

// Header control: shows who you are in the console and lets an agent sign in or out.
export function OperatorControl() {
  const { state, signIn, signOut } = useOperator();
  const [open, setOpen] = useState(false);
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputId = useId();
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !panel.current?.contains(e.target as Node))
        setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (await signIn(token.trim())) {
        setOpen(false);
        setToken("");
      } else setError("This token is not valid.");
    } catch {
      setError("The API is not reachable. Try again in a moment.");
    } finally {
      setBusy(false);
    }
  }

  if (state === "agent")
    return (
      <span className="flex items-center gap-2 text-sm">
        <span className="size-2 rounded-full bg-sent" aria-hidden />
        Agent
        <button type="button" onClick={signOut} className="text-muted underline-offset-2 hover:text-ink hover:underline">
          Sign out
        </button>
      </span>
    );

  return (
    <div className="relative" ref={panel}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="rounded-md px-2.5 py-1 text-sm ring-1 ring-line hover:ring-ink"
      >
        Agent sign-in
      </button>
      {open && (
        <form
          onSubmit={submit}
          className="absolute right-0 z-20 mt-2 w-72 rounded-xl border border-line bg-white p-4 shadow-lg"
        >
          <label htmlFor={inputId} className="text-sm font-medium">
            Operator token
          </label>
          <input
            id={inputId}
            type="password"
            autoComplete="current-password"
            autoFocus
            value={token}
            onChange={(e) => setToken(e.target.value)}
            className="mt-1 w-full rounded-lg border border-line px-3 py-2 text-sm"
          />
          <p className="mt-2 text-xs text-muted">
            Agents can approve replies and see customer contacts. Visitors see the console read-only.
          </p>
          {error && (
            <p role="alert" className="mt-2 text-sm text-escalated">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={busy || token.trim().length === 0}
            className="mt-3 w-full rounded-lg bg-ink px-3 py-2 text-sm font-semibold text-white disabled:opacity-60"
          >
            {busy ? "Checking…" : "Sign in"}
          </button>
        </form>
      )}
    </div>
  );
}
