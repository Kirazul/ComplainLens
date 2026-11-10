"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { TicketView } from "@/components/console/ticket-view";

// Static export: the ticket ID is a query parameter (/console/ticket/?id=42), read in the browser.
function Ticket() {
  const id = Number(useSearchParams().get("id"));
  if (!Number.isInteger(id) || id <= 0) {
    return <main className="mx-auto max-w-7xl px-5 py-8 text-muted">No ticket selected.</main>;
  }
  return <TicketView ticketId={id} />;
}

export default function TicketPage() {
  return (
    <Suspense fallback={<main className="mx-auto max-w-7xl px-5 py-8 text-muted">Loading…</main>}>
      <Ticket />
    </Suspense>
  );
}
