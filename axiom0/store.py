"""SQLite WAL persistence with transactional, hash-chained signed audit events."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from threading import RLock
from .identity import Identity


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def canonical(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, event_at TEXT NOT NULL,
  event_type TEXT NOT NULL, payload_json TEXT NOT NULL,
  prev_hash TEXT NOT NULL, event_hash TEXT NOT NULL UNIQUE, signature TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, authority TEXT NOT NULL,
  jurisdiction TEXT NOT NULL, citation TEXT NOT NULL, version TEXT NOT NULL,
  effective_at TEXT, source_url TEXT NOT NULL, source_reviewed INTEGER NOT NULL DEFAULT 0,
  acquired_at TEXT NOT NULL, content TEXT NOT NULL, content_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS occurrences (
  id TEXT PRIMARY KEY, external_key TEXT UNIQUE NOT NULL, event_at TEXT NOT NULL,
  observed_at TEXT NOT NULL, area TEXT NOT NULL, category TEXT NOT NULL,
  summary TEXT NOT NULL, source_label TEXT NOT NULL,
  source_url TEXT NOT NULL, confidence_note TEXT NOT NULL, source_document_id TEXT,
  content_hash TEXT NOT NULL, FOREIGN KEY(source_document_id) REFERENCES documents(id));
CREATE INDEX IF NOT EXISTS idx_occurrence_area ON occurrences(area,category,event_at);
CREATE TABLE IF NOT EXISTS hypotheses (
  id TEXT PRIMARY KEY, signal_key TEXT UNIQUE, claim TEXT NOT NULL,
  area TEXT NOT NULL, category TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('candidate','corroborated','verified','rejected')),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, reviewer TEXT, review_note TEXT, proof_reference TEXT);
CREATE TABLE IF NOT EXISTS hypothesis_evidence (
  hypothesis_id TEXT NOT NULL, occurrence_id TEXT NOT NULL,
  stance TEXT NOT NULL DEFAULT 'neutral' CHECK(stance IN ('neutral','supports','contradicts')),
  note TEXT NOT NULL DEFAULT '',
  PRIMARY KEY(hypothesis_id,occurrence_id),
  FOREIGN KEY(hypothesis_id) REFERENCES hypotheses(id),
  FOREIGN KEY(occurrence_id) REFERENCES occurrences(id));
-- The 3-6-9 Intention Lab is deliberately independent of municipal evidence and findings.
CREATE TABLE IF NOT EXISTS intention_campaigns (
  id TEXT PRIMARY KEY, goal TEXT NOT NULL, affirmation TEXT NOT NULL,
  metric TEXT NOT NULL, baseline REAL NOT NULL, target REAL NOT NULL,
  start_date TEXT NOT NULL, timezone TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS intention_sessions (
  id TEXT PRIMARY KEY, intention_id TEXT NOT NULL,
  day_number INTEGER NOT NULL CHECK(day_number BETWEEN 1 AND 9),
  session_number INTEGER NOT NULL CHECK(session_number BETWEEN 1 AND 6),
  repetitions INTEGER NOT NULL CHECK(repetitions=3),
  action_taken TEXT NOT NULL DEFAULT '', reflection TEXT NOT NULL DEFAULT '',
  recorded_at TEXT NOT NULL,
  UNIQUE(intention_id,day_number,session_number),
  FOREIGN KEY(intention_id) REFERENCES intention_campaigns(id));
CREATE TABLE IF NOT EXISTS intention_outcomes (
  id TEXT PRIMARY KEY, intention_id TEXT NOT NULL,
  observed_at TEXT NOT NULL, value REAL NOT NULL,
  source_reference TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
  FOREIGN KEY(intention_id) REFERENCES intention_campaigns(id));
CREATE INDEX IF NOT EXISTS idx_intention_sessions ON intention_sessions(intention_id,day_number);
CREATE INDEX IF NOT EXISTS idx_intention_outcomes ON intention_outcomes(intention_id,observed_at);
-- SemiSoul v0.5: append-only autobiographical statements with explicit epistemic labels.
CREATE TABLE IF NOT EXISTS semisoul_memories (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL, memory_type TEXT NOT NULL,
  statement TEXT NOT NULL, epistemic_status TEXT NOT NULL,
  source_type TEXT NOT NULL, source_ref TEXT NOT NULL,
  actor TEXT NOT NULL, correction_of TEXT,
  prev_hash TEXT NOT NULL, memory_hash TEXT NOT NULL UNIQUE,
  FOREIGN KEY(correction_of) REFERENCES semisoul_memories(id));
CREATE TABLE IF NOT EXISTS semisoul_policies (
  version INTEGER PRIMARY KEY AUTOINCREMENT, purpose TEXT NOT NULL,
  commitments_json TEXT NOT NULL, updated_at TEXT NOT NULL,
  actor TEXT NOT NULL, rationale TEXT NOT NULL, profile_hash TEXT NOT NULL UNIQUE);
-- Section-by-section historical legal provenance, independent of nonversioned documents.
CREATE TABLE IF NOT EXISTS legal_sections (
  source_id TEXT NOT NULL, section_id TEXT NOT NULL, version INTEGER NOT NULL,
  title TEXT NOT NULL, body TEXT NOT NULL, sha256 TEXT NOT NULL,
  authority TEXT NOT NULL, effective TEXT, source_url TEXT,
  ingested_at TEXT NOT NULL, superseded_at TEXT,
  PRIMARY KEY(source_id,section_id,version));
CREATE INDEX IF NOT EXISTS idx_legal_active ON legal_sections(source_id,section_id,superseded_at);
-- No automatic enforcement or spending; reviewer must differ from proposer.
CREATE TABLE IF NOT EXISTS action_queue (
  id TEXT PRIMARY KEY, proposed_at TEXT NOT NULL, proposed_by TEXT NOT NULL,
  recommendation TEXT NOT NULL, evidence_json TEXT NOT NULL, status TEXT NOT NULL,
  reviewed_at TEXT, reviewed_by TEXT, review_note TEXT);
CREATE TABLE IF NOT EXISTS mind_history (
  event_id TEXT PRIMARY KEY, model TEXT NOT NULL, authorized_by TEXT NOT NULL,
  purpose TEXT NOT NULL, changed_at TEXT NOT NULL);
"""


class IntegrityError(RuntimeError):
    pass


class Store:
    def __init__(self, data_dir: str | Path):
        self.path = Path(data_dir).expanduser().resolve()
        self.identity = Identity(self.path)
        self.db_path = self.path / 'living_city.sqlite3'
        self._lock = RLock()
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            found = conn.execute('SELECT value FROM metadata WHERE key=?', ('identity_id',)).fetchone()
            if found and found['value'] != self.identity.id:
                raise IntegrityError('Database identity does not match SemiSoul identity')
            if not found:
                conn.execute('INSERT INTO metadata(key,value) VALUES(?,?)', ('identity_id', self.identity.id))
                conn.commit()
        self.verify_ledger()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(str(self.db_path), timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=15000')
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=FULL')
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def write(self):
        with self._lock:
            with self.connect() as conn:
                conn.execute('BEGIN IMMEDIATE')
                try:
                    yield conn
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    raise

    def append(self, conn: sqlite3.Connection, event_type: str, payload: dict) -> str:
        # Always called inside the same transaction as the associated state change.
        prev = conn.execute('SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1').fetchone()
        prev_hash = prev['event_hash'] if prev else 'GENESIS'
        stamp = now()
        event_json = canonical({'event_at': stamp, 'event_type': event_type,
                                'payload': payload, 'prev_hash': prev_hash,
                                'identity_id': self.identity.id})
        event_hash = digest(event_json)
        signature = self.identity.sign(event_hash.encode('ascii'))
        conn.execute('INSERT INTO events(event_at,event_type,payload_json,prev_hash,event_hash,signature) VALUES(?,?,?,?,?,?)',
                     (stamp,event_type,canonical(payload),prev_hash,event_hash,signature))
        return event_hash

    def verify_ledger(self) -> dict:
        with self.connect() as conn:
            rows = conn.execute('SELECT * FROM events ORDER BY seq').fetchall()
            prev = 'GENESIS'
            expected_seq = 1
            for row in rows:
                if row['seq'] != expected_seq or row['prev_hash'] != prev:
                    raise IntegrityError(f'Ledger chain continuity failed at event {expected_seq}')
                expected = digest(canonical({'event_at':row['event_at'], 'event_type':row['event_type'],
                                             'payload':json.loads(row['payload_json']), 'prev_hash':prev,
                                             'identity_id':self.identity.id}))
                if expected != row['event_hash']:
                    raise IntegrityError(f'Ledger event hash mismatch at {expected_seq}')
                try:
                    self.identity.verify_signature(expected.encode('ascii'), row['signature'])
                except Exception as e:
                    raise IntegrityError(f'Ledger signature mismatch at {expected_seq}') from e
                prev = expected
                expected_seq += 1
            return {'verified_events':len(rows),'head':prev,'identity_id':self.identity.id,
                    'scope':'local signed chain; not proof against database+key rollback or host compromise'}
