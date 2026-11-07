"use client";

import { useEffect, useRef, useState } from "react";

import { API_URL } from "@/lib/api";

export interface LiveEvent {
  type: "ticket_created" | "stage" | "ticket_updated" | "reply";
  ticket_id: number;
  [key: string]: unknown;
}

// Subscribe to the API's Server-Sent Events stream; reconnects automatically (EventSource).
export function useEvents(onEvent: (event: LiveEvent) => void): boolean {
  const handler = useRef(onEvent);
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    handler.current = onEvent;
  });
  useEffect(() => {
    const source = new EventSource(`${API_URL}/api/events`);
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.onmessage = (message) => {
      try {
        handler.current(JSON.parse(message.data) as LiveEvent);
      } catch {
        // ignore malformed events
      }
    };
    return () => source.close();
  }, []);
  return connected;
}
