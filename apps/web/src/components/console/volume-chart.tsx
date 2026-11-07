"use client";

import { useState } from "react";

import type { Insights } from "@/lib/api";

// Daily message volume with incident days emphasised (emphasis form: one accent hue, the rest in
// a recessive gray). Palette: accent = reference slot 1 (#2a78d6); gray is de-emphasis, below 3:1
// on the surface, so the incident table under the chart provides the required relief.
const ACCENT = "#2a78d6";
const MUTED = "#c4c8ce";
const W = 960;
const H = 260;
const PAD = { top: 28, right: 12, bottom: 34, left: 44 };

// Days whose strongest incident reaches this z are emphasised (a display choice: incidents are
// detected at a lower threshold almost daily; highlighting all of them would highlight nothing).
const MAJOR_Z = 10;

export function VolumeChart({ timeline }: Readonly<{ timeline: Insights["timeline"] }>) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(...timeline.map((d) => d.messages));
  const yMax = Math.ceil(max / 250) * 250;
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const slot = innerW / timeline.length;
  const barW = Math.max(2, slot - 2); // 2px surface gap between adjacent bars
  const y = (v: number) => PAD.top + innerH - (v / yMax) * innerH;
  const strongest = timeline.reduce(
    (best, d, i) => {
      const z = d.incidents[0]?.z ?? 0;
      return z > best.z ? { i, z } : best;
    },
    { i: -1, z: 0 },
  );
  const ticks = [0, yMax / 2, yMax];
  const fmt = (day: string) =>
    new Date(`${day}T12:00:00Z`).toLocaleDateString("en-CA", { month: "short", day: "numeric" });

  return (
    <figure className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Messages per day, with days that had a detected incident highlighted">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} stroke="#e6e8eb" />
            <text x={PAD.left - 8} y={y(t) + 4} textAnchor="end" fontSize="11" fill="#5b6676">
              {t}
            </text>
          </g>
        ))}
        {timeline.map((d, i) => {
          const x = PAD.left + i * slot + 1;
          const h = (d.messages / yMax) * innerH;
          const isIncident = (d.incidents[0]?.z ?? 0) >= MAJOR_Z;
          const r = Math.min(4, barW / 2, h);
          // Rounded top only: the data end is rounded, the baseline stays square.
          const path = `M${x},${PAD.top + innerH} V${y(d.messages) + r} Q${x},${y(d.messages)} ${x + r},${y(d.messages)} H${x + barW - r} Q${x + barW},${y(d.messages)} ${x + barW},${y(d.messages) + r} V${PAD.top + innerH} Z`;
          return (
            <g key={d.day}>
              <path d={path} fill={isIncident ? ACCENT : MUTED} opacity={hover === null || hover === i ? 1 : 0.55} />
              {/* Hit target: the whole column, larger than the bar. */}
              <rect
                x={PAD.left + i * slot}
                y={PAD.top}
                width={slot}
                height={innerH}
                fill="transparent"
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
              />
              {i % 7 === 0 && (
                <text x={x + barW / 2} y={H - 12} textAnchor="middle" fontSize="11" fill="#5b6676">
                  {fmt(d.day)}
                </text>
              )}
            </g>
          );
        })}
        {strongest.i >= 0 && (
          <text
            x={PAD.left + strongest.i * slot + slot / 2}
            y={y(timeline[strongest.i].messages) - 8}
            textAnchor="end"
            fontSize="12"
            fontWeight="600"
            fill="#172033"
          >
            {fmt(timeline[strongest.i].day)}: {timeline[strongest.i].incidents[0].terms.slice(0, 2).join(" ")}
          </text>
        )}
      </svg>
      {hover !== null && (
        <div
          className="pointer-events-none absolute top-0 z-10 w-64 rounded-lg border border-line bg-white p-3 text-sm shadow-lg"
          style={{ left: `min(calc(${((PAD.left + hover * slot) / W) * 100}% + 8px), calc(100% - 16rem))` }}
        >
          <p className="font-semibold">{fmt(timeline[hover].day)}</p>
          <p className="text-muted">{timeline[hover].messages} messages</p>
          {timeline[hover].incidents.length === 0 ? (
            <p className="mt-1 text-muted">No incident detected</p>
          ) : (
            <ul className="mt-1 space-y-0.5">
              {timeline[hover].incidents.map((inc) => (
                <li key={inc.terms.join()}>
                  {inc.terms.slice(0, 4).join(", ")} <span className="text-muted">({inc.messages} msgs, z {inc.z})</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <figcaption className="mt-2 text-sm text-muted">
        Blue days had a major incident (strongest burst z ≥ {MAJOR_Z}). Hover any day for its detected
        incidents.
      </figcaption>
    </figure>
  );
}
