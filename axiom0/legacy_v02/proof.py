"""Proof Gate: nothing reaches the user unless the source proves it.

A claim is {"text": ..., "cite": "doc_id:section_id", "quote": "..."}.
It passes only if:
  1. the cited section exists in the current library,
  2. the quote appears word for word in that section (spacing and case ignored),
  3. the quote is at least MIN_QUOTE_WORDS long, so a stray phrase cannot pass.
Claims that fail are dropped and reported, never shown as findings.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .truth import AUTHORITY_RANK, TruthLibrary, normalize

MIN_QUOTE_WORDS = 5


@dataclass
class Verdict:
    proven: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)

    @property
    def ratio(self) -> float:
        total = len(self.proven) + len(self.rejected)
        return len(self.proven) / total if total else 0.0


def check_claims(claims: list[dict], library: TruthLibrary) -> Verdict:
    v = Verdict()
    for c in claims:
        cite = str(c.get("cite", "")).strip()
        quote = normalize(str(c.get("quote", "")))
        sec = library.get(cite)
        if sec is None:
            v.rejected.append({**c, "reason": "cited section not found in current library"})
            continue
        if len(quote.split()) < MIN_QUOTE_WORDS:
            v.rejected.append({**c, "reason": f"quote shorter than {MIN_QUOTE_WORDS} words"})
            continue
        if quote.lower() not in normalize(sec.text).lower():
            v.rejected.append({**c, "reason": "quote does not appear in the cited section"})
            continue
        v.proven.append({
            "text": str(c.get("text", "")).strip() or quote,
            "cite": sec.cite_full,
            "quote": quote,
            "authority": sec.authority,
            "authority_rank": AUTHORITY_RANK[sec.authority],
            "effective": sec.effective,
            "source_url": sec.source_url,
        })
    v.proven.sort(key=lambda p: (p["authority_rank"], p["cite"]))
    return v
