// Post-build step for the static export (GitHub Pages).
//
// Next.js writes per-segment prefetch files as nested folders, e.g.
//   out/en/__next.!KHNpdGUp/$d$lang/__PAGE__.txt
// but the browser requests them by their flat name:
//   out/en/__next.!KHNpdGUp.$d$lang.__PAGE__.txt
// A server would rewrite one to the other; a static host cannot, so every page logged 404s and
// client-side navigation lost its prefetch. This copies each nested file to its flat name.
import { copyFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const OUT = fileURLToPath(new URL("../out/", import.meta.url));

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path).map((f) => join(name, f)) : [name];
  });
}

let copied = 0;
function walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (!statSync(path).isDirectory()) continue;
    if (name.startsWith("__next.")) {
      for (const rel of files(path)) {
        const flat = [name, ...rel.split(/[\\/]/)].join(".");
        copyFileSync(join(path, rel), join(dir, flat));
        copied += 1;
      }
    } else {
      walk(path);
    }
  }
}

walk(OUT);
console.log(`flatten-segments: ${copied} prefetch files copied to their flat names`);
