// Typed client for the ComplaintLens API (FastAPI, see src/complaintlens/api/).

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const SUPPORT_EMAIL = process.env.NEXT_PUBLIC_SUPPORT_EMAIL ?? "lunagocare@fldubai.com";
export const FORUM_URL =
  process.env.NEXT_PUBLIC_FORUM_URL ?? "https://github.com/Kirazul/ComplainLens/discussions";

export type Lang = "en" | "fr";
export type Channel = "email" | "web" | "chat" | "review" | "forum";
export type TicketStatus =
  | "processing"
  | "auto_send"
  | "awaiting_approval"
  | "escalated"
  | "no_reply"
  | "answered"
  | "closed";

export interface TicketSummary {
  id: number;
  number: string;
  channel: Channel;
  sender: string;
  sender_name: string | null;
  subject: string | null;
  status: TicketStatus;
  team: string | null;
  priority: number | null;
  language: string | null;
  received_at: string;
  updated_at: string;
  messages: number;
  message_type: string | null;
  categories: string[];
  risk_flags: string[];
  summary: string | null;
  total_ms: number | null;
}

export interface StageRecord {
  id: number;
  seq: number;
  name: string;
  status: "ok" | "skipped" | "error";
  output: Record<string, unknown>;
  confidence: number | null;
  ms: number;
  note: string | null;
}

export type ReplyKind = "answer" | "acknowledgement" | "escalation";

/** One message of a conversation, as the console sees it. */
export interface ThreadItem {
  from: "customer" | "lunago";
  body: string;
  at: string;
  kind?: ReplyKind;
  author?: string | null; // the agent who sent it; null = sent automatically
  id?: number;
  status?: "queued" | "sent" | "failed";
  error?: string | null;
  citations?: string[];
}

export interface Draft {
  id: number;
  body: string;
  citations: string[];
  verification: Record<string, unknown>;
}

export interface Decision {
  action: string;
  reasons: string[];
  team: string;
  priority: number;
  priority_parts: Record<string, number>;
}

export interface TicketDetail extends TicketSummary {
  body: string;
  analysis: Record<string, unknown> | null;
  decision: Decision | null;
  stages: StageRecord[];
  thread: ThreadItem[];
  draft: Draft | null;
  customer: { id: number; name: string; contact: string } | null;
  trip: Record<string, unknown> | null;
}

export interface PublicTicket {
  number: string;
  status: TicketStatus;
  language: string | null;
  received_at: string;
  phases: { name: "received" | "understood" | "routed" | "answered"; done: boolean }[];
  messages: { from: "customer" | "lunago"; body: string; at: string; kind?: ReplyKind; author?: string | null }[];
}

export interface HelpArticle {
  id: string;
  title: string;
  sections: { id: string; heading: string; text: string }[];
}

export interface Stats {
  tickets: number;
  by_status: Record<string, number>;
  by_team: Record<string, number>;
  by_language: Record<string, number>;
  avg_processing_ms: number;
}

export interface Health {
  ok: boolean;
  company: string;
  llm: { enabled: boolean; model: string | null };
  retriever: string;
  email: { enabled: boolean; address?: string; sends_replies?: boolean; last_poll_ok?: boolean; last_error?: string | null };
  forum: { enabled: boolean };
}

export interface User {
  id: number;
  username: string;
  name: string;
  role: "agent" | "admin";
}

export interface Member extends User {
  created_at: string;
}

export interface Incident {
  terms: string[];
  messages: number;
  z: number;
}

export interface Insights {
  source: string;
  zscore_threshold: number;
  timeline: { day: string; messages: number; incidents: Incident[] }[];
  clusters: { id: number; size: number; words: string[]; examples: string[] }[];
}

export interface ExperimentRow {
  question: string;
  claim: string;
  value: string;
  source: string;
}

export interface AnnotationItem {
  id: string;
  set: string;
  lang: string;
  text: string;
  meta: Record<string, unknown>;
}

export interface GoldLabels {
  message_type: string;
  response_required: boolean;
  urgency: string | null;
  categories: string[];
  severity: number | null;
  risk_flags: string[];
  note?: string | null;
}

export interface AnnotationProgress {
  items: Record<string, number>;
  labelled: Record<string, Record<string, number>>;
}

export interface Agreement {
  set: string;
  double_labelled_items: number;
  fields: Record<string, { kappa?: number | null; kappa_quadratic?: number | null; agreement: number }>;
}

// --- console session: the sign-in token, kept in this browser only ---------------------------

export interface Session {
  token: string;
  user: User;
}

const SESSION_KEY = "complaintlens.session";
const listeners = new Set<() => void>();
let cached: Session | null | undefined; // undefined: not read from storage yet

export const session = {
  get(): Session | null {
    if (cached === undefined) {
      try {
        const raw = typeof window === "undefined" ? null : window.localStorage.getItem(SESSION_KEY);
        cached = raw ? (JSON.parse(raw) as Session) : null;
      } catch {
        cached = null; // storage unavailable (private mode): sign in again each visit
      }
    }
    return cached;
  },
  set(next: Session | null) {
    cached = next;
    try {
      if (next) window.localStorage.setItem(SESSION_KEY, JSON.stringify(next));
      else window.localStorage.removeItem(SESSION_KEY);
    } catch {
      // not persisted: the session lasts until the tab is closed
    }
    listeners.forEach((listener) => listener());
  },
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = session.get()?.token;
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (!res.ok) {
    let detail = "";
    try {
      const body = (await res.json()) as { detail?: unknown };
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? "");
    } catch {
      // not JSON
    }
    // An expired or revoked session: back to the sign-in screen.
    if (res.status === 401 && token && !path.startsWith("/api/auth/login")) session.set(null);
    throw new ApiError(res.status, detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  // public
  health: () => request<Health>("/api/health"),
  help: (lang: Lang) => request<HelpArticle[]>(`/api/help?lang=${lang}`),
  submit: (payload: { email: string; name?: string; subject?: string; body: string; channel?: "web" | "chat" | "review" }) =>
    post<{ id: number; number: string; track_key: string }>("/api/messages", payload),
  publicTicket: (id: number, key: string) =>
    request<PublicTicket>(`/api/public/tickets/${id}?k=${encodeURIComponent(key)}`),
  followUp: (id: number, key: string, body: string) =>
    post<{ accepted: boolean }>(`/api/public/tickets/${id}/messages`, { k: key, body }),

  // sign-in
  login: (username: string, password: string) => post<Session>("/api/auth/login", { username, password }),
  logout: () => post<{ signed_out: boolean }>("/api/auth/logout", {}),
  me: () => request<User>("/api/auth/me"),
  changePassword: (current: string, next: string) =>
    post<{ token: string }>("/api/auth/password", { current, new: next }),

  // team (administrators)
  users: () => request<Member[]>("/api/users"),
  addUser: (user: { username: string; name: string; password: string; role: "agent" | "admin" }) =>
    post<Member>("/api/users", user),
  resetPassword: (id: number, password: string) => post<{ reset: boolean }>(`/api/users/${id}/password`, { password }),
  removeUser: (id: number) => request<{ removed: boolean }>(`/api/users/${id}`, { method: "DELETE" }),

  // inbox and conversations
  stats: () => request<Stats>("/api/stats"),
  tickets: () => request<TicketSummary[]>("/api/tickets"),
  ticket: (id: number) => request<TicketDetail>(`/api/tickets/${id}`),
  reply: (id: number, body: string) => post<{ status: string; error: string | null }>(`/api/tickets/${id}/reply`, { body }),
  setResolved: (id: number, resolved: boolean) => post<{ status: string }>(`/api/tickets/${id}/status`, { resolved }),

  // research
  insights: () => request<Insights>("/api/insights"),
  experiments: () => request<ExperimentRow[]>("/api/experiments"),
  annotateNext: (set: string) =>
    request<{ item: AnnotationItem | null; progress: AnnotationProgress }>(`/api/annotate/next?set=${set}`),
  annotateSave: (item_id: string, labels: GoldLabels) =>
    post<{ saved: boolean; progress: AnnotationProgress }>("/api/annotate", { item_id, labels }),
  annotateAddItem: (text: string, lang: "en" | "fr") => post<AnnotationItem>("/api/annotate/items", { text, lang }),
  agreement: (set: string) => request<Agreement>(`/api/annotate/agreement?set=${set}`),
};

/**
 * Live events (Server-Sent Events) read with fetch, so the session token goes in a header and
 * never in a URL. Resolves when the stream ends or `signal` aborts; throws on HTTP errors.
 */
export async function readEvents(
  onEvent: (event: Record<string, unknown>) => void,
  onOpen: () => void,
  signal: AbortSignal,
): Promise<void> {
  const token = session.get()?.token;
  const res = await fetch(`${API_URL}/api/events`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    signal,
  });
  if (!res.ok || !res.body) {
    if (res.status === 401 && token) session.set(null);
    throw new ApiError(res.status, res.statusText);
  }
  onOpen();
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += value;
    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const data = block
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("\n");
      if (!data) continue; // a comment (keep-alive)
      try {
        onEvent(JSON.parse(data) as Record<string, unknown>);
      } catch {
        // ignore a malformed event
      }
    }
  }
}
