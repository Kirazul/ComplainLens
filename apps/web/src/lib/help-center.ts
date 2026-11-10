// Reads the LunaGo Help Center (company/help_center/<lang>/*.md) at BUILD time, so help pages are
// static HTML. Same format and parsing rules as the Python knowledge base (rag/knowledge.py):
// front matter with id and title, one section per "## " heading, section IDs "<id>#<n>".
import "server-only";

import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import type { HelpArticle, Lang } from "./api";

const ROOT = path.join(process.cwd(), "..", "..", "company", "help_center");

export function loadHelpCenter(lang: Lang): HelpArticle[] {
  const dir = path.join(ROOT, lang);
  return readdirSync(dir)
    .filter((f) => f.endsWith(".md"))
    .sort()
    .map((file) => {
      const raw = readFileSync(path.join(dir, file), "utf8").replace(/\r\n/g, "\n");
      const [, meta, body] = raw.split("---");
      const field = (name: string) => meta.match(new RegExp(`^${name}:\\s*(.+)$`, "m"))?.[1].trim() ?? "";
      const id = field("id");
      const sections = body
        .split(/^## /m)
        .slice(1)
        .map((section, i) => {
          const [heading, ...rest] = section.split("\n");
          return { id: `${id}#${i + 1}`, heading: heading.trim(), text: rest.join("\n").trim() };
        });
      return { id, title: field("title"), sections };
    });
}
