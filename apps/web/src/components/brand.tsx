// The two marks, drawn on a 32-unit grid.
// LunaGo: a crescent moon (two circles, r 10 and r 8.2, intersecting at 14.07,6.54 and
// 24.67,19.04) with a destination pin in its opening: night rides that take you home.
// ComplaintLens: a lens ring whose tail makes it a speech bubble: a lens on what customers say.

const CRESCENT = "M14.07 6.54A10 10 0 1 0 24.67 19.04A8.2 8.2 0 0 1 14.07 6.54Z";
const PIN = "M22.4 16.4c-1.9-2.2-2.9-3.7-2.9-5.1a2.9 2.9 0 0 1 5.8 0c0 1.4-1 2.9-2.9 5.1Z";

/** The LunaGo mark. `tile` draws it on its night-blue square (app icon); otherwise it sits on
 * the page's own dark background. */
export function LunaGoMark({ size = 32, tile = false }: { size?: number; tile?: boolean }) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden>
      {tile && <rect width="32" height="32" rx="9" fill="#1e1b4b" />}
      <path d={CRESCENT} fill="#f2a33a" />
      <path d={PIN} fill="#f5f3ff" />
      <circle cx="22.4" cy="11.3" r="1.05" fill="#1e1b4b" />
    </svg>
  );
}

/** Mark and wordmark. `tone` is the background it sits on. */
export function LunaGoLogo({ tone = "dark", size = 30 }: { tone?: "dark" | "light"; size?: number }) {
  return (
    <span className="inline-flex items-center gap-2 font-display font-extrabold tracking-tight" style={{ fontSize: size * 0.8 }}>
      <LunaGoMark size={size} tile={tone === "light"} />
      <span className={tone === "dark" ? "text-paper" : "text-night"}>
        Luna<span className={tone === "dark" ? "text-amber" : "text-amber-deep"}>Go</span>
      </span>
    </span>
  );
}

export function ComplaintLensMark({ size = 26 }: { size?: number }) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden>
      <rect width="32" height="32" rx="9" fill="#172033" />
      <path
        d="M16 7.5a8 8 0 1 1-5.66 13.66L7 24.5l.9-5.2A8 8 0 0 1 16 7.5Z"
        fill="none"
        stroke="#f2a33a"
        strokeWidth="2.6"
        strokeLinejoin="round"
      />
      <circle cx="16" cy="15.5" r="2.4" fill="#f4f6f8" />
    </svg>
  );
}
