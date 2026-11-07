"""The Help Center knowledge base and BM25 retrieval (plan §7).

Chunking: one chunk per ``##`` section, indexed with the article title prepended ("contextual chunk
header"): a section such as "Refunds take 5 to 10 business days" is meaningless without knowing it
belongs to "Refunds, credits and promotions". Chunk IDs are stable (``HC-FARES#4``) so replies can
cite them and the verifier can check them.

BM25 (Robertson & Zaragoza, 2009) is implemented here in a few lines rather than imported, so every
part of the ranking can be explained:
    score(q, d) = sum over query terms t of
        IDF(t) * tf(t, d) * (k1 + 1) / (tf(t, d) + k1 * (1 - b + b * |d| / avgdl))
    IDF(t) = ln(1 + (N - df(t) + 0.5) / (df(t) + 0.5))
k1 controls term-frequency saturation, b controls length normalisation.

Tokenisation for this *sparse* retriever lower-cases and folds accents ("débité" = "debite") so that
spelling variants match; this is only for retrieval: the text sent to models is never altered.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_TOKEN = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "has",
        "have",
        "i",
        "in",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "so",
        "that",
        "the",
        "their",
        "there",
        "this",
        "to",
        "was",
        "we",
        "were",
        "what",
        "when",
        "which",
        "who",
        "will",
        "with",
        "you",
        "your",
        "au",
        "aux",
        "avec",
        "ce",
        "ces",
        "dans",
        "de",
        "des",
        "du",
        "elle",
        "en",
        "et",
        "il",
        "ils",
        "je",
        "la",
        "le",
        "les",
        "leur",
        "lui",
        "ma",
        "mais",
        "me",
        "mes",
        "mon",
        "ne",
        "nos",
        "notre",
        "nous",
        "on",
        "ou",
        "par",
        "pas",
        "pour",
        "qu",
        "que",
        "qui",
        "sa",
        "se",
        "ses",
        "son",
        "sur",
        "ta",
        "te",
        "tes",
        "toi",
        "ton",
        "tu",
        "un",
        "une",
        "vos",
        "votre",
        "vous",
        "y",
        "ete",
        "est",
        "sont",
    ]
)


def tokenize(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return [t for t in _TOKEN.findall(folded) if t not in STOPWORDS]


@dataclass(frozen=True)
class Chunk:
    id: str  # e.g. "HC-FARES#4"
    lang: str
    article_id: str
    title: str
    heading: str
    text: str

    @property
    def indexed_text(self) -> str:
        return f"{self.title}. {self.heading}. {self.text}"


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float


def parse_article(path: Path, lang: str) -> list[Chunk]:
    raw = path.read_text(encoding="utf-8")
    meta_block, body = raw.split("---", 2)[1:]
    meta = dict(line.split(":", 1) for line in meta_block.strip().splitlines() if ":" in line)
    article_id, title = meta["id"].strip(), meta["title"].strip()
    chunks = []
    for n, section in enumerate(re.split(r"^## ", body, flags=re.MULTILINE)[1:], start=1):
        heading, _, text = section.partition("\n")
        chunks.append(
            Chunk(f"{article_id}#{n}", lang, article_id, title, heading.strip(), text.strip())
        )
    return chunks


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.tfs = [Counter(d) for d in docs]
        self.lens = [len(d) for d in docs]
        self.avgdl = sum(self.lens) / max(len(docs), 1)
        df = Counter(t for d in docs for t in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: list[str]) -> list[float]:
        out = []
        for tf, length in zip(self.tfs, self.lens, strict=True):
            s = 0.0
            for t in query:
                if t in tf:
                    f = tf[t]
                    norm = f + self.k1 * (1 - self.b + self.b * length / self.avgdl)
                    s += self.idf[t] * f * (self.k1 + 1) / norm
            out.append(s)
        return out


class KnowledgeBase:
    """All Help Center chunks, with one BM25 index per language."""

    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self.by_id = {c.id + "@" + c.lang: c for c in chunks}
        self._index: dict[str, tuple[list[Chunk], BM25]] = {}
        for lang in {c.lang for c in chunks}:
            lc = [c for c in chunks if c.lang == lang]
            self._index[lang] = (lc, BM25([tokenize(c.indexed_text) for c in lc]))

    @classmethod
    def load(cls, root: Path) -> KnowledgeBase:
        chunks = [
            chunk
            for lang_dir in sorted(p for p in root.iterdir() if p.is_dir())
            for path in sorted(lang_dir.glob("*.md"))
            for chunk in parse_article(path, lang_dir.name)
        ]
        return cls(chunks)

    def get(self, chunk_id: str, lang: str) -> Chunk | None:
        return self.by_id.get(chunk_id + "@" + lang)

    def search(self, query: str, lang: str, k: int = 4) -> list[Hit]:
        chunks, bm25 = self._index.get(lang) or self._index["en"]
        scored = sorted(zip(chunks, bm25.scores(tokenize(query)), strict=True), key=lambda x: -x[1])
        return [Hit(c, round(s, 3)) for c, s in scored[:k] if s > 0]
