"""Truth Library: official sources, split into sections, hashed and versioned.

Source files are plain text or markdown with a header block:

    ---
    doc_id: kcmo-code-ch2
    title: Code of Ordinances, Chapter 2
    authority: ordinance        # charter | ordinance | policy | procedure
    effective: 2026-01-01
    source_url: https://...      # optional, where the official copy lives
    ---
    Sec. 2-13. Title of the section.
    Text of the section...

Section headings recognized: "Sec. 2-13.", "Section 101.", "§ 2-13", or a
markdown heading "## <id> <title>". Text before the first heading is ignored.

Nothing is overwritten. A changed section gets a new version; the old one is
kept and marked superseded, so any past answer can still be checked against
the exact text it cited.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

# Lower number = higher authority. The Charter governs local conflicts;
# conflicts with state or federal law are flagged for legal review, never resolved here.
AUTHORITY_RANK = {"charter": 1, "ordinance": 2, "policy": 3, "procedure": 4}

HEADING = re.compile(
    r"^\s*(?:(?:Sec\.|Section|§)\s*(?P<id>[0-9A-Za-z][0-9A-Za-z\-\.]*?)\.?\s+(?P<title>.*)"
    r"|#{2,3}\s+(?P<mid>[0-9A-Za-z][0-9A-Za-z\-\.]*)\s+(?P<mtitle>.*))\s*$"
)


@dataclass
class Section:
    doc_id: str
    section_id: str
    title: str
    text: str
    sha256: str
    version: int
    authority: str
    effective: str | None
    source_url: str | None

    @property
    def cite(self) -> str:
        return f"{self.doc_id}:{self.section_id}"

    @property
    def cite_full(self) -> str:
        return f"{self.doc_id}:{self.section_id}@v{self.version}#{self.sha256[:12]}"


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def section_hash(title: str, text: str) -> str:
    return hashlib.sha256(normalize(title + "\n" + text).encode("utf-8")).hexdigest()


def parse_source(raw: str) -> tuple[dict, list[tuple[str, str, str]]]:
    meta: dict = {}
    body = raw
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.split("#", 1)[0].strip() if k.strip() != "source_url" else v.strip()
        body = raw[m.end():]
    if "doc_id" not in meta:
        raise ValueError("source file is missing 'doc_id' in its header")
    meta.setdefault("authority", "ordinance")
    if meta["authority"] not in AUTHORITY_RANK:
        raise ValueError(f"unknown authority '{meta['authority']}'")

    sections: list[tuple[str, str, str]] = []
    cur_id = cur_title = None
    buf: list[str] = []
    for line in body.splitlines():
        h = HEADING.match(line)
        if h:
            if cur_id is not None:
                sections.append((cur_id, cur_title, "\n".join(buf).strip()))
            cur_id = (h.group("id") or h.group("mid")).rstrip(".")
            cur_title = (h.group("title") or h.group("mtitle") or "").strip()
            buf = []
        elif cur_id is not None:
            buf.append(line)
    if cur_id is not None:
        sections.append((cur_id, cur_title, "\n".join(buf).strip()))
    return meta, sections


class TruthLibrary:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        db.execute(
            """CREATE TABLE IF NOT EXISTS sections (
                doc_id TEXT NOT NULL, section_id TEXT NOT NULL, version INTEGER NOT NULL,
                title TEXT NOT NULL, text TEXT NOT NULL, sha256 TEXT NOT NULL,
                authority TEXT NOT NULL, effective TEXT, source_url TEXT,
                ingested_at TEXT NOT NULL, superseded_at TEXT,
                PRIMARY KEY (doc_id, section_id, version))"""
        )
        db.commit()

    # ---- ingest -------------------------------------------------------------
    def ingest_text(self, raw: str) -> dict:
        """Load one source file. Returns what was added, changed, removed, unchanged."""
        meta, parsed = parse_source(raw)
        doc_id = meta["doc_id"]
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        current = {s.section_id: s for s in self.current(doc_id=doc_id)}
        seen = set()
        report = {"doc_id": doc_id, "added": [], "changed": [], "removed": [], "unchanged": 0}

        for sid, title, text in parsed:
            if sid in seen:
                raise ValueError(f"{doc_id}: section '{sid}' appears twice")
            seen.add(sid)
            h = section_hash(title, text)
            old = current.get(sid)
            if old and old.sha256 == h:
                report["unchanged"] += 1
                continue
            version = 1
            if old:
                version = old.version + 1
                self.db.execute(
                    "UPDATE sections SET superseded_at=? WHERE doc_id=? AND section_id=? AND version=?",
                    (now, doc_id, sid, old.version))
                report["changed"].append({"section": sid, "from": old.sha256[:12], "to": h[:12]})
            else:
                report["added"].append(sid)
            self.db.execute(
                "INSERT INTO sections VALUES (?,?,?,?,?,?,?,?,?,?,NULL)",
                (doc_id, sid, version, title, text, h, meta["authority"],
                 meta.get("effective"), meta.get("source_url"), now))

        for sid in current:
            if sid not in seen:
                self.db.execute(
                    "UPDATE sections SET superseded_at=? WHERE doc_id=? AND section_id=? AND superseded_at IS NULL",
                    (now, doc_id, sid))
                report["removed"].append(sid)
        self.db.commit()
        return report

    def ingest_file(self, path: str) -> dict:
        with open(path, encoding="utf-8") as f:
            return self.ingest_text(f.read())

    # ---- read ---------------------------------------------------------------
    def _rows(self, where: str, args: tuple) -> list[Section]:
        rows = self.db.execute(
            "SELECT doc_id, section_id, title, text, sha256, version, authority, effective, source_url "
            f"FROM sections WHERE {where} ORDER BY doc_id, section_id", args).fetchall()
        return [Section(*r) for r in rows]

    def current(self, doc_id: str | None = None) -> list[Section]:
        if doc_id:
            return self._rows("superseded_at IS NULL AND doc_id=?", (doc_id,))
        return self._rows("superseded_at IS NULL", ())

    def get(self, cite: str, version: int | None = None) -> Section | None:
        """Look up 'doc_id:section_id'. Without a version, returns the current text."""
        if ":" not in cite:
            return None
        doc_id, sid = cite.split(":", 1)
        sid = sid.split("@", 1)[0]
        if version is None:
            rows = self._rows("superseded_at IS NULL AND doc_id=? AND section_id=?", (doc_id, sid))
        else:
            rows = self._rows("doc_id=? AND section_id=? AND version=?", (doc_id, sid, version))
        return rows[0] if rows else None
