// Typed client for the ComplaintLens API (FastAPI, see src/complaintlens/api.py).

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Lang = "en" | "fr";
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
  channel: string;
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
  status: "draft" | "sent" | "failed";
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
  email: { enabled: boolean; address?: string; last_poll_ok?: boolean; last_error?: string | null };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${detail ? `: ${detail}` : ""}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/api/health"),
  stats: () => request<Stats>("/api/stats"),
  tickets: () => request<TicketSummary[]>("/api/tickets"),
  ticket: (id: number) => request<TicketDetail>(`/api/tickets/${id}`),
  approve: (id: number, body?: string) =>
    request<{ status: string; error: string | null }>(`/api/tickets/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ body: body ?? null }),
    }),
  submit: (payload: { email: string; name?: string; subject?: string; body: string; channel?: string }) =>
    request<{ id: number; number: string; track_key: string }>("/api/messages", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  publicTicket: (id: number, key: string) =>
    request<PublicTicket>(`/api/public/tickets/${id}?k=${encodeURIComponent(key)}`),
  help: (lang: Lang) => request<HelpArticle[]>(`/api/help?lang=${lang}`),
};
