"use client";

import { useEffect, useState } from "react";

import { VolumeChart } from "@/components/console/volume-chart";
import { api, type ExperimentRow, type Insights } from "@/lib/api";

export default function InsightsPage() {
  const [data, setData] = useState<Insights | null>(null);
  const [rows, setRows] = useState<ExperimentRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([api.insights(), api.experiments()])
      .then(([insights, experiments]) => {
        if (!active) return;
        setData(insights);
        setRows(experiments);
      })
      .catch((e: Error) => {
        if (active) setError(`The insights could not be loaded (${e.message}).`);
      });
    return () => {
      active = false;
    };
  }, []);

  if (error) return <main className="mx-auto max-w-7xl px-5 py-8"><p role="alert" className="text-escalated">{error}</p></main>;
  if (!data) return <main className="mx-auto max-w-7xl px-5 py-8 text-muted">Loading…</main>;

  const incidents = data.timeline
    .flatMap((d) => d.incidents.map((i) => ({ day: d.day, ...i })))
    .sort((a, b) => b.z - a.z)
    .slice(0, 12);

  return (
    <main className="mx-auto max-w-7xl space-y-10 px-5 py-8">
      <section>
        <h1 className="text-2xl font-semibold">Insights</h1>
        <p className="mt-1 text-sm text-muted">
          Real customer messages: {data.source}. October to December 2017.
        </p>
      </section>

      <section className="rounded-xl border border-line bg-white p-5" aria-labelledby="volume">
        <h2 id="volume" className="font-semibold">Messages per day and emerging incidents</h2>
        <div className="mt-4">
          <VolumeChart timeline={data.timeline} />
        </div>
        <h3 className="mt-6 text-sm font-semibold">Strongest incidents</h3>
        <table className="mt-2 w-full text-left text-sm">
          <thead className="text-muted">
            <tr>
              <th className="py-1 pr-4 font-medium">Day</th>
              <th className="py-1 pr-4 font-medium">What customers wrote about</th>
              <th className="py-1 pr-4 text-right font-medium">Messages</th>
              <th className="py-1 text-right font-medium">Burst z</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {incidents.map((i) => (
              <tr key={i.day + i.terms.join()}>
                <td className="py-1.5 pr-4 whitespace-nowrap">{i.day}</td>
                <td className="py-1.5 pr-4">{i.terms.join(", ")}</td>
                <td className="py-1.5 pr-4 text-right">{i.messages}</td>
                <td className="py-1.5 text-right">{i.z}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section aria-labelledby="clusters">
        <h2 id="clusters" className="font-semibold">Recurring problems found automatically</h2>
        <p className="mt-1 text-sm text-muted">
          30 groups from multilingual sentence embeddings; each is named by its most distinctive words.
        </p>
        <ul className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data.clusters.slice(0, 12).map((c) => (
            <li key={c.id} className="rounded-xl border border-line bg-white p-4">
              <div className="flex items-baseline justify-between gap-3">
                <p className="font-semibold">{c.words.slice(0, 4).join(" · ")}</p>
                <span className="text-sm text-muted">{c.size}</span>
              </div>
              <ul className="mt-2 space-y-1 text-sm text-muted">
                {c.examples.slice(0, 2).map((e) => (
                  <li key={e} className="line-clamp-2">“{e}”</li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="experiments" className="rounded-xl border border-line bg-white p-5">
        <h2 id="experiments" className="font-semibold">Experiments behind the system</h2>
        <p className="mt-1 text-sm text-muted">Every number below is read from the results file that produced it.</p>
        <table className="mt-3 w-full text-left text-sm">
          <thead className="text-muted">
            <tr>
              <th className="py-1 pr-4 font-medium">Question</th>
              <th className="py-1 pr-4 font-medium">Measured</th>
              <th className="py-1 pr-4 font-medium">Result</th>
              <th className="py-1 font-medium">Source</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((r) => (
              <tr key={r.claim}>
                <td className="py-1.5 pr-4 font-semibold">{r.question}</td>
                <td className="py-1.5 pr-4">{r.claim}</td>
                <td className="py-1.5 pr-4 whitespace-nowrap">{r.value}</td>
                <td className="py-1.5 text-muted">reports/results/{r.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}
