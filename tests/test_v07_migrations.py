"""v0.7: versioned schema migrations, recorded in the signed ledger."""
import sqlite3

import pytest

from axiom0 import store as store_mod
from axiom0.engine import LivingCity
from axiom0.store import IntegrityError, Store


def _make_v06_database(path, monkeypatch):
    """Create a database exactly as v0.6 left it: baseline schema, no schema_version, some history."""
    monkeypatch.setattr(store_mod, 'SCHEMA_VERSION', 1)
    s = Store(path)
    with s.write() as conn:
        conn.execute("INSERT INTO mind_history VALUES('e1','llama3.2:3b','howard','initial model','2026-11-01T00:00:00+00:00')")
        s.append(conn, 'mind_replaced', {'model': 'llama3.2:3b'})
    monkeypatch.undo()


def test_v06_database_upgrades_with_signed_migration_events(tmp_path, monkeypatch):
    _make_v06_database(tmp_path, monkeypatch)
    s = Store(tmp_path)
    assert s.schema_version() == store_mod.SCHEMA_VERSION
    with s.connect() as conn:
        cols = [r['name'] for r in conn.execute('PRAGMA table_info(mind_history)')]
        old = conn.execute('SELECT reason FROM mind_history').fetchone()
        events = [r['event_type'] for r in conn.execute('SELECT event_type FROM events ORDER BY seq')]
    assert 'reason' in cols and 'purpose' not in cols
    assert old['reason'] == 'initial model'                       # existing data preserved
    assert events == ['mind_replaced'] + ['schema_migrated'] * (store_mod.SCHEMA_VERSION - 1)
    assert s.verify_ledger()['verified_events'] == store_mod.SCHEMA_VERSION


def test_swap_mind_writes_reason_column(tmp_path):
    city = LivingCity(tmp_path)
    city.swap_mind('llama3.2:1b', 'howard', 'smaller model for a 4 GB board')
    with city.store.connect() as conn:
        row = conn.execute('SELECT reason FROM mind_history').fetchone()
    assert row['reason'] == 'smaller model for a 4 GB board'


def test_migration_is_idempotent(tmp_path):
    Store(tmp_path)
    s = Store(tmp_path)
    assert s.migrate() == []
    assert s.verify_ledger()['verified_events'] == 0           # fresh ledger: no noise events


def test_refuses_newer_database(tmp_path):
    Store(tmp_path)
    con = sqlite3.connect(tmp_path / 'living_city.sqlite3')
    con.execute("UPDATE metadata SET value='99' WHERE key='schema_version'")
    con.commit()
    con.close()
    with pytest.raises(IntegrityError, match='newer'):
        Store(tmp_path)
