"use client";

import { useState, type FormEvent } from "react";

import { api, ApiError, session } from "@/lib/api";

export default function AccountPage() {
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const d = new FormData(form);
    if (d.get("new") !== d.get("again")) return setMessage({ ok: false, text: "The two new passwords are different." });
    setBusy(true);
    try {
      const { token } = await api.changePassword(String(d.get("current")), String(d.get("new")));
      const s = session.get();
      if (s) session.set({ ...s, token });
      form.reset();
      setMessage({ ok: true, text: "Password changed. Other devices were signed out." });
    } catch (err) {
      const text =
        err instanceof ApiError && err.status === 403
          ? "Your current password is wrong."
          : err instanceof ApiError && err.status === 422
            ? "The new password needs at least 8 characters."
            : "The password could not be changed. Try again.";
      setMessage({ ok: false, text });
    } finally {
      setBusy(false);
    }
  }

  const field = "mt-1 w-full rounded-lg border border-line px-3 py-2";
  return (
    <main className="mx-auto max-w-md px-5 py-8">
      <h1 className="text-2xl font-semibold">Change password</h1>
      <form onSubmit={submit} className="mt-6 space-y-4 rounded-xl border border-line bg-white p-5">
        <label className="block text-sm font-medium">
          Current password
          <input name="current" type="password" required autoComplete="current-password" className={field} />
        </label>
        <label className="block text-sm font-medium">
          New password
          <input name="new" type="password" required minLength={8} autoComplete="new-password" className={field} />
        </label>
        <label className="block text-sm font-medium">
          New password again
          <input name="again" type="password" required minLength={8} autoComplete="new-password" className={field} />
        </label>
        {message && (
          <p role={message.ok ? "status" : "alert"} className={`text-sm ${message.ok ? "text-sent" : "text-escalated"}`}>
            {message.text}
          </p>
        )}
        <button type="submit" disabled={busy} className="rounded-lg bg-ink px-5 py-2 font-semibold text-white disabled:opacity-60">
          {busy ? "Saving…" : "Change password"}
        </button>
      </form>
    </main>
  );
}
