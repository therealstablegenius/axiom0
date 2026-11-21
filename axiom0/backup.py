"""Backup, restore and audit export.

backup   One .tar.gz holding a consistent online copy of the database (SQLite backup
         API, safe while the service runs), the identity key, and a manifest with
         SHA-256 of each file plus the ledger head at backup time. The archive
         contains the private signing key: store it like a password (the file is
         created owner-only).
restore  Into an EMPTY data directory only. Checks the manifest hashes, opens the
         ledger, verifies every signature and confirms the head matches the
         manifest before returning.
export   Audit export (JSON Lines) of every ledger event with its hash and
         signature, plus the public key. An auditor can verify it independently
         with tools/axiom0_audit_verify.py, which needs only Python and the
         `cryptography` package, not AXIOM0.
"""
from __future__ import annotations
import hashlib
import io
import json
import os
import sqlite3
import tarfile
import tempfile
from pathlib import Path
from . import __version__
from .store import Store, now

BACKUP_FORMAT = 'axiom0-backup-v1'
AUDIT_FORMAT = 'axiom0-audit-v1'
_MEMBERS = ('living_city.sqlite3', 'identity.ed25519', 'manifest.json')


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def create_backup(store: Store, dest_dir: str | Path, *, actor: str) -> dict:
    head = store.verify_ledger()                     # never back up a ledger that fails verification
    dest_dir = Path(dest_dir).expanduser().resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = now().replace(':', '').replace('-', '')
    archive = dest_dir / f'axiom0-backup-{store.identity.id[:12]}-{stamp}.tar.gz'
    with tempfile.TemporaryDirectory() as tmp:
        db_copy = Path(tmp) / 'living_city.sqlite3'
        src = sqlite3.connect(str(store.db_path))
        dst = sqlite3.connect(str(db_copy))
        try:
            src.backup(dst)                          # transactionally consistent, even while serving
        finally:
            dst.close(); src.close()
        files = {'living_city.sqlite3': db_copy.read_bytes(),
                 'identity.ed25519': (store.path / 'identity.ed25519').read_bytes()}
        manifest = {'format': BACKUP_FORMAT, 'created_at': now(), 'axiom0_version': __version__,
                    'identity_id': store.identity.id, 'schema_version': store.schema_version(),
                    'ledger_events': head['verified_events'], 'ledger_head': head['head'],
                    'sha256': {name: _sha(data) for name, data in files.items()}}
        files['manifest.json'] = json.dumps(manifest, indent=2, sort_keys=True).encode('utf-8')
        fd = os.open(archive, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'wb') as raw, tarfile.open(fileobj=raw, mode='w:gz') as tar:
            for name in _MEMBERS:
                info = tarfile.TarInfo(name)
                info.size = len(files[name]); info.mode = 0o600; info.mtime = 0
                tar.addfile(info, io.BytesIO(files[name]))
    with store.write() as conn:
        store.append(conn, 'backup_created', {'actor': actor, 'archive_sha256': _sha(archive.read_bytes()),
                                              'ledger_events': manifest['ledger_events'],
                                              'ledger_head': manifest['ledger_head']})
    return {'archive': str(archive), 'ledger_events': manifest['ledger_events'], 'ledger_head': manifest['ledger_head'],
            'warning': 'Contains the private identity key. Keep it offline or encrypted, owner-only.'}


def restore_backup(archive: str | Path, data_dir: str | Path) -> dict:
    archive = Path(archive).expanduser().resolve()
    data_dir = Path(data_dir).expanduser().resolve()
    if data_dir.exists() and any(data_dir.iterdir()):
        raise FileExistsError(f'{data_dir} is not empty; restore only into a new, empty data directory')
    with tarfile.open(archive, 'r:gz') as tar:
        names = tar.getnames()
        if sorted(names) != sorted(_MEMBERS):
            raise ValueError('Not an AXIOM0 backup (unexpected archive contents)')
        blobs = {}
        for name in _MEMBERS:                       # read members by exact name; never extract paths
            member = tar.getmember(name)
            if not member.isfile() or member.size > 2_000_000_000:
                raise ValueError(f'Invalid archive member {name}')
            blobs[name] = tar.extractfile(member).read()
    manifest = json.loads(blobs['manifest.json'])
    if manifest.get('format') != BACKUP_FORMAT:
        raise ValueError('Unsupported backup format')
    for name in ('living_city.sqlite3', 'identity.ed25519'):
        if _sha(blobs[name]) != manifest['sha256'][name]:
            raise ValueError(f'{name} does not match its manifest hash: archive is damaged or altered')
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == 'posix':
        data_dir.chmod(0o700)
    for name in ('living_city.sqlite3', 'identity.ed25519'):
        fd = os.open(data_dir / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'wb') as f:
            f.write(blobs[name]); f.flush(); os.fsync(f.fileno())
    store = Store(data_dir)                          # verifies every signature; applies newer migrations
    with store.connect() as conn:
        row = conn.execute('SELECT event_hash FROM events WHERE seq=?', (manifest['ledger_events'],)).fetchone() \
            if manifest['ledger_events'] else None
    if manifest['ledger_events'] and (not row or row['event_hash'] != manifest['ledger_head']):
        raise ValueError('Restored ledger head does not match the backup manifest')
    return {'restored_to': str(data_dir), 'identity_id': store.identity.id,
            'ledger_events_at_backup': manifest['ledger_events'], 'ledger_head_at_backup': manifest['ledger_head'],
            'next_step': 'Run anchor-verify against your published receipts to confirm nothing older was lost.'}


def export_audit(store: Store, out_path: str | Path) -> dict:
    head = store.verify_ledger()
    out_path = Path(out_path).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with store.connect() as conn:
        rows = conn.execute('SELECT * FROM events ORDER BY seq').fetchall()
    with out_path.open('w', encoding='utf-8') as f:
        f.write(json.dumps({'format': AUDIT_FORMAT, 'identity_id': store.identity.id,
                            'public_key': store.identity.public_raw.hex(), 'exported_at': now(),
                            'events': len(rows), 'head': head['head'], 'axiom0_version': __version__}) + '\n')
        for r in rows:
            f.write(json.dumps({'seq': r['seq'], 'event_at': r['event_at'], 'event_type': r['event_type'],
                                'payload': json.loads(r['payload_json']), 'prev_hash': r['prev_hash'],
                                'event_hash': r['event_hash'], 'signature': r['signature']},
                               ensure_ascii=False) + '\n')
    return {'file': str(out_path), 'events': len(rows), 'head': head['head'],
            'note': 'Contains operational records (questions, actors, recommendations). Share with auditors only.'}
