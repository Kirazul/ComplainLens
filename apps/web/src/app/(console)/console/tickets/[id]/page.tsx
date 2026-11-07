import type { Metadata } from "next";
import { Suspense } from "react";

import { TicketView } from "@/components/console/ticket-view";

export const metadata: Metadata = { title: "Ticket" };

async function Ticket({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <TicketView ticketId={Number(id)} />;
}

export default function TicketPage({ params }: PageProps<"/console/tickets/[id]">) {
  return (
    <Suspense fallback={<main className="mx-auto max-w-7xl px-5 py-8 text-muted">Loading…</main>}>
      <Ticket params={params} />
    </Suspense>
  );
}
