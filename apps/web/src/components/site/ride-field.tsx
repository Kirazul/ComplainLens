"use client";

import { useEffect, useState } from "react";

import { api, type Account, type Lang, type Ride } from "@/lib/api";
import { dateTime } from "@/lib/format";
import type { Dict } from "@/lib/i18n";

export const RIDE_ID = /^LG-\d{4,6}$/;

/** Normalise what a customer types ("lg 12345", "LG12345") to "LG-12345". */
export function normaliseRideId(value: string): string {
  const digits = value.replace(/^\s*lg[\s-]*/i, "").trim();
  return value.trim() ? `LG-${digits}` : "";
}

// Which ride a message is about: a list of the customer's rides when signed in, an optional ride
// ID box otherwise. The value is submitted as the form field "ride".
export function RideField({ me, lang, t, field }: { me: Account | null | undefined; lang: Lang; t: Dict["contact"]; field: string }) {
  const [rides, setRides] = useState<Ride[]>([]);
  useEffect(() => {
    if (me) api.myRides().then(setRides).catch(() => setRides([]));
  }, [me]);

  if (me)
    return (
      <label className="block">
        <span className="font-semibold text-night">{t.ride}</span>
        <select name="ride" defaultValue="" className={field}>
          <option value="">{t.rideNone}</option>
          {rides.map((r) => (
            <option key={r.id} value={r.id}>
              {r.id} · {r.pickup} → {r.dropoff} · {dateTime(r.started_at, lang)}
            </option>
          ))}
        </select>
      </label>
    );
  return (
    <label className="block">
      <span className="font-semibold text-night">{t.rideId}</span>
      <input name="ride" placeholder={t.rideIdPlaceholder} autoCapitalize="characters" className={field} />
    </label>
  );
}
