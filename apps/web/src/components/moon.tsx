// A moon phase drawn as SVG: 0 = new moon (dark), 1 = crescent, 2 = half, 3 = gibbous, 4 = full.
// LunaGo uses it as the progress mark of a support request.

interface MoonProps {
  phase: 0 | 1 | 2 | 3 | 4;
  size?: number;
  className?: string;
  title?: string;
  /** "night" on the indigo background (light moon), "day" on paper or white (indigo moon). */
  surface?: "night" | "day";
}

export function Moon({ phase, size = 40, className, title, surface = "night" }: MoonProps) {
  const r = 18;
  // The lit part is the right half plus an ellipse that grows from the left as the phase advances.
  // Ellipse x-radius: +r at new moon (covers lit half -> dark), 0 at half, -r at full (adds the other half).
  const rx = r * (1 - phase / 2);
  const lit = surface === "night" ? "var(--color-paper)" : "var(--color-night)";
  const dark = surface === "night" ? "var(--color-night-soft)" : "#e9e6fb";
  return (
    <svg
      viewBox="0 0 40 40"
      width={size}
      height={size}
      className={`shrink-0 ${className ?? ""}`}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      <circle cx="20" cy="20" r={r} fill={dark} stroke="var(--color-lilac)" strokeOpacity="0.35" />
      {phase > 0 && (
        <>
          <path d={`M20 2 A18 18 0 0 1 20 38 Z`} fill={lit} />
          <ellipse
            cx="20"
            cy="20"
            rx={Math.abs(rx)}
            ry={r}
            fill={rx > 0 ? dark : lit}
          />
        </>
      )}
    </svg>
  );
}
