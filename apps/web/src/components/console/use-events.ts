"use client";

import { useEffect, useRef, useState } from "react";

import { readEvents } from "@/lib/api";

export interface LiveEvent {
  type: "ticket_created" | "stage" | "ticket_updated" | "reply" | "message";
  ticket_id: number;
  [key: string]: unknown;
}

// Subscribe to the API's live events; reconnects after a drop (the API may be waking up).
export function useEvents(onEvent: (event: LiveEvent) => void): boolean {
  const handler = useRef(onEvent);
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    handler.current = onEvent;
  });
  useEffect(() => {
    const controller = new AbortController();
    let retry: ReturnType<typeof setTimeout>;
    let delay = 2000; // doubles after each failed attempt, up to 30 s; reset once connected
    const connect = () => {
      readEvents(
        (event) => handler.current(event as LiveEvent),
        () => {
          delay = 2000;
          setConnected(true);
        },
        controller.signal,
      )
        .catch(() => undefined)
        .finally(() => {
          if (controller.signal.aborted) return;
          setConnected(false);
          retry = setTimeout(connect, delay);
          delay = Math.min(delay * 2, 30_000);
        });
    };
    connect();
    return () => {
      controller.abort();
      clearTimeout(retry);
    };
  }, []);
  return connected;
}
