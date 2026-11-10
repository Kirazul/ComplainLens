// Typed client for the ComplaintLens API (FastAPI, see src/complaintlens/api.py).

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

export interface ReplyRecord {
  id: number;
  kind: "answer" | "acknowledgement" | "escalation";
  body: string;
  citations: string[];
  verification: Record<string, unknown>;
  status: "draft" | "queued" | "sent" | "failed";
  created_at: string;
  sent_at: string | null;
  error: string | null;
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
  replies: ReplyRecord[];
  customer: { id: number; name: string; contact: string } | null;
  trip: Record<string, unknown> | null;
}

export interface PublicTicket {
  number: string;
  status: TicketStatus;
  language: string | null;
  received_at: string;
  team: string | null;
  phases: { name: "received" | "understood" | "routed" | "answered"; done: boolean }[];
  replies: { kind: string; body: string; sent_at: string | null }[];
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
  email: {
    enabled: boolean;
    address?: string;
    sends_replies?: boolean;
    last_poll_ok?: boolean;
    last_error?: string | null;
  };
  forum: { enabled: boolean };
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

// Operators (support agents) sign in to the console with a token; it is kept in this browser
// only and sent as a Bearer token. Without it the console is read-only and contacts are masked.
const TOKEN_KEY = "complaintlens.operator";

export const operatorToken = {
  get(): string | null {
    try {
      return typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string | null) {
    try {
      if (token) window.localStorage.setItem(TOKEN_KEY, token);
      else window.localStorage.removeItem(TOKEN_KEY);
    } catch {
      // storage unavailable (private mode): the console stays read-only
    }
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

async function request<T>(path: string, init?: RequestInit, token = operatorToken.get()): Promise<T> {
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
    throw new ApiError(res.status, detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/api/health"),
  operator: (token?: string) =>
    request<{ operator: boolean }>("/api/operator", undefined, token ?? operatorToken.get()),
  stats: () => request<Stats>("/api/stats"),
  tickets: () => request<TicketSummary[]>("/api/tickets"),
  ticket: (id: number) => request<TicketDetail>(`/api/tickets/${id}`),
  approve: (id: number, body?: string) =>
    request<{ status: string; error: string | null }>(`/api/tickets/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ body: body ?? null }),
    }),
  submit: (payload: {
    email: string;
    name?: string;
    subject?: string;
    body: string;
    channel?: "web" | "chat" | "review";
  }) =>
    request<{ id: number; number: string; track_key: string }>("/api/messages", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  publicTicket: (id: number, key: string) =>
    request<PublicTicket>(`/api/public/tickets/${id}?k=${encodeURIComponent(key)}`),
  help: (lang: Lang) => request<HelpArticle[]>(`/api/help?lang=${lang}`),
  insights: () => request<Insights>("/api/insights"),
  annotateNext: (annotator: string, set: string) =>
    request<{ item: AnnotationItem | null; progress: AnnotationProgress }>(
      `/api/annotate/next?annotator=${encodeURIComponent(annotator)}&set=${set}`,
    ),
  annotateSave: (item_id: string, annotator: string, labels: GoldLabels) =>
    request<{ saved: boolean; progress: AnnotationProgress }>("/api/annotate", {
      method: "POST",
      body: JSON.stringify({ item_id, annotator, labels }),
    }),
  annotateAddItem: (text: string, lang: "en" | "fr") =>
    request<AnnotationItem>("/api/annotate/items", { method: "POST", body: JSON.stringify({ text, lang }) }),
  agreement: (set: string) => request<Agreement>(`/api/annotate/agreement?set=${set}`),
  experiments: () => request<ExperimentRow[]>("/api/experiments"),
};
