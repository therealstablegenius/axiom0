"""Retrieval: BM25 keyword ranking over current sections.

Plain and deterministic, so the same question over the same library always
returns the same evidence. Embedding search (pgvector) can be added beside it
later; it should widen the candidates, not replace this ranking.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from .truth import Section

STOP = set("""a an and are as at be by for from has have if in into is it its of on or
that the their then there these this to was were will with shall may must any all
what which who whom how when where why does do can""".split())


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower()) if t not in STOP]


def bm25(query: str, sections: list[Section], k: int = 5,
         k1: float = 1.5, b: float = 0.75) -> list[tuple[Section, float]]:
    if not sections:
        return []
    docs = [tokens(s.section_id + " " + s.title + " " + s.text) for s in sections]
    avgdl = sum(len(d) for d in docs) / len(docs)
    df: Counter = Counter()
    for d in docs:
        df.update(set(d))
    n = len(docs)
    q = tokens(query)
    scored = []
    for s, d in zip(sections, docs):
        tf = Counter(d)
        score = 0.0
        for term in q:
            if term not in tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            f = tf[term]
            score += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * len(d) / avgdl))
        if score > 0:
            scored.append((s, score))
    scored.sort(key=lambda x: (-x[1], x[0].cite))
    return scored[:k]


def best_sentences(query: str, text: str, n: int = 2) -> list[str]:
    """Pick the sentences of a section that share the most terms with the query."""
    sents = [s.strip() for s in re.split(r"(?<=[.;:])\s+(?=[A-Z(])", text) if len(s.split()) >= 5]
    q = set(tokens(query))
    ranked = sorted(sents, key=lambda s: -len(q & set(tokens(s))))
    picked = [s for s in ranked if q & set(tokens(s))][:n]
    # Keep the original order so the excerpt reads naturally.
    return sorted(picked, key=sents.index)
