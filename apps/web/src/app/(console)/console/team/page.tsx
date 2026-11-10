"use client";

import { useEffect, useState, type FormEvent } from "react";

import { useSession } from "@/components/console/shell";
import { api, type Member } from "@/lib/api";

export default function TeamPage() {
  const current = useSession();
  const [members, setMembers] = useState<Member[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const admin = current?.user.role === "admin";

  useEffect(() => {
    if (!admin) return;
    api.users().then(setMembers).catch((e: Error) => setError(e.message));
  }, [admin, version]);

  if (!admin) return <main className="mx-auto max-w-4xl px-5 py-8 text-muted">Only administrators manage the team.</main>;

  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const d = new FormData(form);
    setError(null);
    try {
      const m = await api.addUser({
        name: String(d.get("name")),
        username: String(d.get("username")),
        password: String(d.get("password")),
        role: d.get("role") === "admin" ? "admin" : "agent",
      });
      form.reset();
      setNotice(`${m.name} can now sign in as “${m.username}”.`);
      setVersion((v) => v + 1);
    } catch (err) {
      setError(capitalize((err as Error).message));
    }
  }

  async function reset(m: Member) {
    const password = window.prompt(`New password for ${m.name} (at least 8 characters)`);
    if (!password) return;
    try {
      await api.resetPassword(m.id, password);
      setNotice(`Password changed for ${m.name}.`);
    } catch (err) {
      setError(capitalize((err as Error).message));
    }
  }

  async function remove(m: Member) {
    if (!window.confirm(`Remove ${m.name}? They are signed out at once.`)) return;
    try {
      await api.removeUser(m.id);
      setVersion((v) => v + 1);
    } catch (err) {
      setError(capitalize((err as Error).message));
    }
  }

  const field = "mt-1 w-full rounded-lg border border-line px-3 py-2";
  return (
    <main className="mx-auto max-w-4xl px-5 py-8">
      <h1 className="text-2xl font-semibold">Team</h1>
      {notice && <p role="status" className="mt-4 rounded-lg bg-teal-50 px-4 py-2.5 text-sm text-sent">{notice}</p>}
      {error && <p role="alert" className="mt-4 rounded-lg bg-red-50 px-4 py-2.5 text-sm text-escalated">{error}</p>}

      <div className="mt-6 overflow-x-auto rounded-xl border border-line bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-line text-muted">
            <tr>
              <th scope="col" className="px-4 py-2.5 font-medium">Name</th>
              <th scope="col" className="px-4 py-2.5 font-medium">Username</th>
              <th scope="col" className="px-4 py-2.5 font-medium">Role</th>
              <th scope="col" className="px-4 py-2.5"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {(members ?? []).map((m) => (
              <tr key={m.id}>
                <td className="px-4 py-3 font-medium">{m.name}</td>
                <td className="px-4 py-3">{m.username}</td>
                <td className="px-4 py-3">{m.role === "admin" ? "Administrator" : "Agent"}</td>
                <td className="whitespace-nowrap px-4 py-3 text-right">
                  <button type="button" onClick={() => reset(m)} className="text-muted hover:text-ink">Reset password</button>
                  {m.id !== current?.user.id && (
                    <button type="button" onClick={() => remove(m)} className="ml-4 text-escalated hover:underline">Remove</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!members && !error && <p className="px-4 py-8 text-center text-muted">Loading…</p>}
      </div>

      <form onSubmit={add} className="mt-8 rounded-xl border border-line bg-white p-5">
        <h2 className="font-semibold">Add a team member</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <label className="text-sm font-medium">
            Name
            <input name="name" required maxLength={60} className={field} placeholder="Rimel Zouari" />
          </label>
          <label className="text-sm font-medium">
            Username
            <input name="username" required pattern="[a-z0-9._\-]{3,32}" autoCapitalize="none" spellCheck={false} className={field} placeholder="rimel" />
          </label>
          <label className="text-sm font-medium">
            Password
            <input name="password" type="text" required minLength={8} autoComplete="off" className={field} placeholder="At least 8 characters" />
          </label>
          <label className="text-sm font-medium">
            Role
            <select name="role" className={field} defaultValue="agent">
              <option value="agent">Agent: answers customers</option>
              <option value="admin">Administrator: also manages the team</option>
            </select>
          </label>
        </div>
        <button type="submit" className="mt-5 rounded-lg bg-ink px-5 py-2 font-semibold text-white">Add</button>
      </form>
    </main>
  );
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1) + (text.endsWith(".") ? "" : ".");
}
